"""Real SDK / native Web harness, every outbound HTTP intercepted by MockTransport.
No provider configuration is read; only fresh disposable roots are accepted.
"""
import argparse,asyncio,json,os
from dataclasses import replace
from pathlib import Path
import httpx
from openai import AsyncOpenAI
from mybot.workspace import init_workspace
from scripts.streaming_fixtures import chunk
from .plan import MESSAGE,config_for,plan_hash
from .budget import Ledger,private_directory
from .server import owned_app
USAGE=dict(prompt_tokens=10,completion_tokens=20,total_tokens=30)
class Bytes(httpx.AsyncByteStream):
 def __init__(self,packets,delay=.03,interrupt=False):self.packets=packets;self.delay=delay;self.interrupt=interrupt;self.closed=False
 async def __aiter__(self):
  for p in self.packets:
   await asyncio.sleep(self.delay)
   yield ('data: '+json.dumps(dict(id='mock',object='chat.completion.chunk',created=1,model='mock',**p))+'\n\n').encode()
  if self.interrupt:raise httpx.ReadError('synthetic interruption')
  yield b'data: [DONE]\n\n'
 async def aclose(self):self.closed=True

def client_builder(mode,counter):
 async def handler(request):
  counter.append(json.loads(request.content))
  if mode=='before':return httpx.Response(503,json={'error':{'message':'synthetic','type':'server_error'}})
  packets=[chunk('合成第一段。\n'),chunk('合成第二段。\n')]
  if mode!='after':packets.append(chunk(finish='stop'))
  if mode=='duplicate':packets.append(chunk(finish='stop'))
  if mode not in ('missing','after'):packets.append(dict(choices=[],usage=USAGE))
  return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(packets,.15,mode=='after'))
 def build(cfg):return AsyncOpenAI(api_key='synthetic-only',base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
 return build

def make_mock(root,port,mode='standard'):
 root=Path(root).resolve();private_directory(root)
 if (root/'private').exists():raise RuntimeError('fresh_mock_root_required')
 private_directory(root/'private');(root/'workspace').mkdir(mode=0o700);init_workspace(root/'workspace')
 cfg=config_for(root,dict(model='deepseek-v4.1-flash',base_url='http://mock.invalid/v1',api_key='synthetic-only'))
 backup=replace(cfg,provider='coco2',model='glm-5.3-flash');ledger=Ledger(root/'private/requests.sqlite',plan_hash());counter=[]
 app=owned_app(root,cfg,backup,ledger,client_builder(mode,counter),lambda allow_halt:None,port);app.mock_requests=counter
 return app

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args();os.umask(0o077)
 mode=(a.root/'mode.txt').read_text().strip() if (a.root/'mode.txt').exists() else 'standard'
 if mode not in ('standard','duplicate','missing','before','after'):raise ValueError('unknown_mock')
 import uvicorn
 uvicorn.run(make_mock(a.root,a.port,mode),host='127.0.0.1',port=a.port,access_log=False,log_level='warning')
if __name__=='__main__':main()
