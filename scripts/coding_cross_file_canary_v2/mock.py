"""Scripted MockTransport proposes calls; only native tools change candidate bytes."""
import argparse,json
from pathlib import Path
from dataclasses import replace
import httpx
from openai import AsyncOpenAI
from scripts.streaming_fixtures import chunk,tool
from scripts.stream_legacy_canary.mock import Bytes
from scripts.uat_operator.ports import serve
from mybot.evaluation.coding_agent import decode_result
from .plan import *
from .fixture import create,REFERENCES
from .integrity import IntegrityGate
from .budget import Ledger,private_directory
from .server import owned_app

def builder(mode,counter):
 results=[];source={};seen=set();reads=[]
 async def handle(request):
  body=json.loads(request.content);counter.append(body)
  calls={c['id']:c['function'] for m in body['messages'] for c in m.get('tool_calls') or []}
  # These policies stop after the requested operation even if a bounded context
  # clipped its result. They assert no success; host/native evidence judges it.
  terminal_operations=[f for f in calls.values() if f['name']=='apply_patch' and json.loads(f['arguments']).get('dry_run') is False] if mode=='stale_after_test' else [f for f in calls.values() if f['name']=='record_task_contract']
  if (mode=='stale_after_test' or mode=='contract_illegal') and len(terminal_operations)>=2:
   frames=[chunk('Synthetic final statement; host evidence decides.\n',finish='stop'),dict(choices=[],usage=dict(prompt_tokens=10,completion_tokens=10,total_tokens=20))]
   return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes(frames,.01,False))
  for m in body['messages']:
   if m['role']=='tool' and m['tool_call_id'] not in seen:
    ident=m['tool_call_id'];function=calls[ident];name=function['name']
    text,meta=decode_result(m['content']);results.append((name,text,meta));seen.add(ident)
    if name=='read_file_range':
     args=json.loads(function['arguments']);reads.append(args['path'])
     source[args['path']]=(''.join(line.split(' | ',1)[1]+'\n' for line in text.splitlines() if ' | ' in line),meta.get('file_sha256'))
  def call(name,args):
   raw=json.dumps(args,ensure_ascii=False);half=len(raw)//2
   return [chunk(tools=[tool(0,'mock-'+str(len(counter)),name,raw[:half])]),chunk(tools=[tool(0,args=raw[half:])],finish='tool_calls')]
  def final():return [chunk('Synthetic completion.\n',finish='stop')]
  patches=[m for n,t,m in results if n=='apply_patch' and m.get('applied')]
  commands=[m for n,t,m in results if n=='run_command']
  contracts=[m for n,t,m in results if n=='record_task_contract']
  order=['tests/test_csvmini.py',*ALLOWED]
  if mode=='budget':frames=call('read_file_range',dict(path=ALLOWED[0],start_line=1,end_line=100+len(counter)))
  elif mode=='no_patch':frames=final()
  elif mode in ('contract_legal','contract_illegal') and not contracts:
   frames=call('record_task_contract',dict(requirements=[dict(requirement_id='R1',requirement_text=MESSAGE[:MESSAGE.index('，')],source_type='user_explicit',source_reference='current-user',category='functional')]))
  elif len(reads)<len(order):frames=call('read_file_range',dict(path=order[len(reads)],start_line=1,end_line=200))
  elif results[-1][0]=='apply_patch' and results[-1][2].get('receipt_created'):
   frames=final() if mode=='preview_only' else call('apply_patch',dict(dry_run=False,preview_receipt='invalid') if mode=='invalid_receipt' else results[-1][2]['commit_arguments'])
  elif not patches or mode=='sequential' and len(patches)==1:
   paths=[ALLOWED[len(patches)]] if mode=='sequential' else [ALLOWED[0]] if mode=='parser_only' else [ALLOWED[1]] if mode=='report_only' else list(ALLOWED)
   changes=[]
   for path in paths:
    old,sha=source[path];new=REFERENCES[path]
    if mode=='bad_fix' and path==ALLOWED[1]:new='def category_totals(csv_text):\n    return []\n'
    changes.append(dict(op='update',path='README.md' if mode=='scope' else path,expected_sha256='0'*64 if mode=='wrong_sha' and path==ALLOWED[1] else sha,edits=[dict(old_text=old,new_text=new)]))
   # A failed preview or commit ends this proposal; no automatic repair of negatives.
   frames=final() if results[-1][0]=='apply_patch' and not results[-1][2].get('applied') else call('apply_patch',dict(dry_run=True,changes=changes))
  elif not commands:frames=final() if mode=='no_test' else call('run_command',dict(argv=COMMAND))
  elif mode=='stale_after_test' and len(patches)==1:
   path=ALLOWED[1];old="    records = parser.parse_records(csv_text)\n"
   frames=call('apply_patch',dict(dry_run=True,changes=[dict(op='update',path=path,expected_sha256=patches[-1]['after_sha256'][path],edits=[dict(old_text=old,new_text=old+'    # New revision requires a fresh test.\n')])]))
  elif mode=='contract_illegal' and len(contracts)==1:frames=call('record_task_contract',dict(evidence_links=[dict(requirement_id='R1',evidence_ref='unobserved-test')]))
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
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--status-file',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--mode',default='normal');a=p.parse_args();serve(lambda port:make_mock(a.root,port,a.mode),a.port,a.status_file)
if __name__=='__main__':main()
