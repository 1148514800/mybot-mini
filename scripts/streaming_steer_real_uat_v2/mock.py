"""SDK MockTransport + native Web, no real provider configuration read."""
import argparse,asyncio,json,os
from dataclasses import replace
from pathlib import Path
import httpx
from openai import AsyncOpenAI
from mybot.workspace import init_workspace
from scripts.streaming_fixtures import chunk,tool
from .plan import config_for,plan_hash,FIXTURES,IDENTIFIER,BARRIER
from .budget import Ledger,private_directory
from .server import owned_app
from scripts.stream_legacy_canary.mock import Bytes
USAGE=dict(prompt_tokens=10,completion_tokens=20,total_tokens=30)
def build_mock(case,mode,counter,delay=.14):
 async def handler(request):
  body=json.loads(request.content);counter.append(body);n=len(counter)
  if mode=='before' and n==1:return httpx.Response(503,json={'error':{'message':'Synthetic unavailable','type':'server_error'}})
  users=[m.get('content','') for m in body['messages'] if m['role']=='user'];steered=any('用户在本Turn补充' in x for x in users)
  read=any(m.get('role')=='tool' and IDENTIFIER in m.get('content','') for m in body['messages'])
  if case=='T01' and mode not in ('direct','duplicate','after'):
   if not steered:frames=[chunk('Synthetic first genuine chunk.\n'),chunk(tools=[tool(0,'old-call','list_', '{"path":')]),chunk(tools=[tool(0,name='files',args='"."}')],finish='tool_calls')]
   elif not read:
    frames=[chunk('Synthetic next boundary.\n'),chunk(tools=[tool(0,'new-call','read_', '{"path":')]),chunk(tools=[tool(0,name='file',args='"README.md"}')],finish='tool_calls')]
    if mode=='incomplete':frames=[chunk('Synthetic next boundary.\n'),chunk(tools=[tool(0,'new-call','read_file','{')],finish='tool_calls')]
   else:frames=[chunk('本项目是纯本地的Markdown搜索工具，不使用外部网络。\n'),chunk('它只读取本地Markdown文档，项目标识为'+IDENTIFIER+'。',finish='stop')]
  elif case=='T03':frames=[chunk('Synthetic output line %d.\n'%i) for i in range(150)]+[chunk(finish='stop')]
  else:frames=[chunk('合成列表推导式说明第一句。\n'),chunk('第二句。\n'),chunk('第三句。\n'),chunk('第四句。',finish='stop')]
  if mode=='terminal_first':frames=[chunk('Synthetic terminal first.',finish='stop')]
  if mode=='duplicate':frames=[chunk('Synthetic.',finish='stop'),chunk(finish='stop')]
  if mode=='after':frames=[chunk('Synthetic partial.\n')]
  if mode not in ('missing','after'):frames.append(dict(choices=[],usage=USAGE))
  return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(frames,delay,mode=='after'))
 def builder(cfg):return AsyncOpenAI(api_key='synthetic-only',base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
 return builder

def make_mock(root,port,case,mode='normal',*,barriers=BARRIER,delay=.14):
 root=Path(root).resolve();private_directory(root);private_directory(root/'private')
 if (root/'private'/f'{case}-settled.json').exists():raise RuntimeError('no_mock_case_reruns')
 cfg=config_for(root,dict(model='deepseek-v4.1-flash',base_url='http://mock.invalid/v1',api_key='synthetic-only'))
 if not cfg.workspace.exists():
  cfg.workspace.mkdir(mode=0o700);init_workspace(cfg.workspace)
  for name,text in FIXTURES.items():
   p=cfg.workspace/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
 ledger=Ledger(root/'private/requests.sqlite',plan_hash());counter=[];backup=replace(cfg,provider='coco2',model='glm-5.3-flash')
 app=owned_app(case,root,cfg,backup,ledger,build_mock(case,mode,counter,delay),lambda allow_halt:None,port,barriers=barriers);app.mock_requests=counter;return app

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args();os.umask(0o077)
 setting=json.loads((a.root/'mock-control.json').read_text());case=setting['case'];mode=setting.get('mode','normal')
 import uvicorn
 uvicorn.run(make_mock(a.root,a.port,case,mode),host='127.0.0.1',port=a.port,access_log=False,log_level='warning')
if __name__=='__main__':main()
