"""Reactive synthetic frames use actual observed native read/receipt results."""
import json,argparse
from pathlib import Path
from dataclasses import replace
import httpx
from openai import AsyncOpenAI
from scripts.streaming_fixtures import chunk,tool
from scripts.stream_legacy_canary.mock import Bytes
from scripts.uat_operator.ports import serve
from mybot.evaluation.coding_agent import decode_result
from .plan import *
from .fixture import create,REFERENCE
from .integrity import IntegrityGate
from .budget import Ledger,private_directory
from .server import owned_app

def builder(mode,counter):
 async def handle(request):
  body=json.loads(request.content);counter.append(body);results=[]
  names={c['id']:c['function']['name'] for m in body['messages'] for c in m.get('tool_calls') or []}
  for m in body['messages']:
   if m['role']=='tool':
    text,meta=decode_result(m['content']);results.append((names[m['tool_call_id']],text,meta))
  def call(name,args):
   raw=json.dumps(args,ensure_ascii=False);half=len(raw)//2
   return [chunk(tools=[tool(0,'mock-'+str(len(counter)),name,raw[:half])]),chunk(tools=[tool(0,args=raw[half:])],finish='tool_calls')]
  def final():return [chunk('Synthetic completion.\n',finish='stop')]
  if mode=='budget':frames=call('read_file_range',dict(path=ALLOWED,start_line=1,end_line=100+len(counter)))
  elif mode=='no_patch':frames=final()
  elif not results:frames=call('read_file_range',dict(path='tests/test_search.py',start_line=1,end_line=100))
  elif results[-1][0]=='read_file_range' and not any(m.get('file_sha256') and 'def search_notes' in t for _,t,m in results):frames=call('read_file_range',dict(path=ALLOWED,start_line=1,end_line=100))
  elif results[-1][0]=='read_file_range':
   _,text,meta=results[-1];source='\n'.join(line.split(' | ',1)[1] for line in text.splitlines())+'\n'
   args=dict(dry_run=True,changes=[dict(op='update',path='README.md' if mode=='scope' else ALLOWED,expected_sha256='0'*64 if mode=='wrong_sha' else meta['file_sha256'],edits=[dict(old_text=source,new_text=(REFERENCE+'# Second revision.\n' if mode=='stale_after_test' and any(n=='run_command' for n,_,m in results) else REFERENCE) if mode!='bad_fix' else source.replace('sorted(', 'list('))])])
   frames=call('apply_patch',dict(dry_run=False,preview_receipt='invalid') if mode=='invalid_receipt' else args)
  elif results[-1][0]=='apply_patch' and results[-1][2].get('receipt_created'):
   frames=final() if mode=='preview_only' else call('apply_patch',results[-1][2]['commit_arguments'])
  elif results[-1][0]=='apply_patch' and results[-1][2].get('applied'):
   frames=final() if mode=='no_test' or (mode=='stale_after_test' and sum(m.get('applied') is True for _,_,m in results)>1) else call('run_command',dict(argv=COMMAND))
  elif mode=='stale_after_test' and results[-1][0]=='run_command':frames=call('read_file_range',dict(path=ALLOWED,start_line=1,end_line=100))
  else:frames=final()
  if mode=='incomplete':frames=[chunk(tools=[tool(0,'broken','apply_patch','{')],finish='tool_calls')]
  if mode=='broken_stream':frames=[chunk('Synthetic prefix\n')]
  else:frames.append(dict(choices=[],usage=dict(prompt_tokens=10,completion_tokens=10,total_tokens=20)))
  return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(frames,.01,mode=='broken_stream'))
 return lambda cfg:AsyncOpenAI(api_key='synthetic-only',base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
def make_mock(batch,port,mode='normal',approval_timeout=90):
 batch=Path(batch).resolve();private_directory(batch);private_directory(batch/'private')
 if not (batch/'workspace').exists():create(batch/'workspace');IntegrityGate(batch/'workspace',batch/'private/integrity.json').initialize()
 cfg=config_for(batch,dict(model='deepseek-v4.1-flash',base_url='http://mock.invalid/v1',api_key='synthetic-only'));counter=[]
 app=owned_app(batch,cfg,replace(cfg,provider='coco2',model='glm-5.3-flash'),Ledger(batch/'private/requests.sqlite',plan_hash()),builder(mode,counter),lambda allow:None,port,approval_timeout=approval_timeout);app.mock_requests=counter;return app

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--status-file',type=Path,required=True);p.add_argument('--port',type=int,required=True);a=p.parse_args();serve(lambda port:make_mock(a.root,port),a.port,a.status_file)
if __name__=='__main__':main()
