"""Disposable offline Chrome/shutdown fixture: all SDK HTTP uses MockTransport.

No provider configuration is loaded. Every external request is intercepted.
"""
import argparse,asyncio,json,os,sqlite3
from pathlib import Path
import httpx
from openai import AsyncOpenAI
from mybot.web.server import create_app
from scripts.eventstore_fixtures import configuration
from scripts.streaming_fixtures import chunk,tool


def make_app(root,port):
 root=Path(root).resolve()
 if not root.is_dir() or root.is_symlink() or root.stat().st_mode&0o077:raise ValueError('private_fixture_required')
 cfg=configuration(root,web_streaming=True,web_steer=True,context_max_chars=60000,context_token_budget={'mode':'estimate','input_limit':30000},coding_enabled=False,context_recent_turns=6)
 public=cfg.workspace/'public.txt'
 if not public.exists():public.write_text('SYNTHETIC-LOCAL-42\n')
 ledger=root/'synthetic-ledger.sqlite'
 with sqlite3.connect(ledger) as d:d.execute('create table if not exists meta(key text primary key,value text)')
 def halted():
  with sqlite3.connect(ledger) as d:return d.execute("select 1 from meta where key='halt'").fetchone() is not None
 class Bytes(httpx.AsyncByteStream):
  def __init__(self,packets,delay):self.packets=packets;self.delay=delay
  async def __aiter__(self):
   for p in self.packets:
    await asyncio.sleep(self.delay)
    yield ('data: '+json.dumps(dict(id='mock',object='chat.completion.chunk',created=1,model='mock',**p))+'\n\n').encode()
   yield b'data: [DONE]\n\n'
  async def aclose(self):
   with (root/'stream-closes.jsonl').open('a') as f:f.write('{"closed":true}\n')
 async def handler(request):
  assert not halted(),'synthetic_halt_guard'
  body=json.loads(request.content);assert body['stream'] and body['stream_options']=={'include_usage':True}
  with (root/'sdk-requests.jsonl').open('a') as f:f.write(json.dumps(body,ensure_ascii=False)+'\n')
  users=[m['content'] for m in body['messages'] if m['role']=='user'];text=next((v for v in reversed(users) if v.startswith('合成')),'');steered=any('用户在本Turn补充' in v for v in users);has_tool=any(m['role']=='tool' for m in body['messages']);delay=.12
  if text.startswith(('合成B','合成F')):packets=[chunk('已有合成预览。\n'),chunk('下一行。\n'),chunk(finish='stop'),chunk(finish='stop')]
  elif text.startswith('合成C'):packets=[chunk('正在生成第%d行。\n'%i) for i in range(150)]+[chunk(finish='stop')];delay=.15
  elif text.startswith('合成D2'):packets=[chunk(tools=[tool(0,'partial','read_file','{"path":')],finish='tool_calls')]
  elif text.startswith('合成D') and not has_tool:
   packets=[chunk(tools=[tool(0,'read-public','read_','{"path":')]),chunk(tools=[tool(0,name='file',args='"public.txt"}')],finish='tool_calls')]
  elif text.startswith('合成E') and not steered:
   packets=[chunk('即将提交尚未执行的工具。\n'),chunk(tools=[tool(0,'held','list_files','{"path":"."}')],finish='tool_calls')];delay=.65
  elif steered:packets=[chunk('下一安全步骤收到用户补充，工具没有先执行。\n',finish='stop')]
  elif has_tool:packets=[chunk('文件内容为SYNTHETIC-LOCAL-42。\n',finish='stop')]
  else:packets=[chunk('标准流第一行。\n'),chunk('标准流第二行。\n'),chunk('标准流第三行。\n'),chunk(finish='stop')]
  packets.append(dict(choices=[],usage=dict(prompt_tokens=10,completion_tokens=20,total_tokens=30)))
  return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(packets,delay))
 def factory(config):return AsyncOpenAI(api_key='synthetic-only',base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
 app=create_app(cfg,port=port,client_factory=factory);start=app.runtime.start
 async def accepted(c,text):
  if halted():return False
  ok=await start(c,text)
  if ok and text.startswith('合成F'):
   def settle(task):
    if c.status=='provider_error':
     with sqlite3.connect(ledger) as d:d.execute("insert or replace into meta values('halt','synthetic_protocol_failure')")
   c.task.add_done_callback(settle)
  return ok
 app.runtime.start=accepted
 return app


def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args();os.umask(0o077)
 import uvicorn
 # Match the old uv launcher shape and unbounded Uvicorn graceful wait: finite
 # authenticated SSE connections themselves must let shutdown make progress.
 uvicorn.run(make_app(a.root,a.port),host='127.0.0.1',port=a.port,log_level='info',access_log=False)
if __name__=='__main__':main()
