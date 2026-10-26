"""Future Live entry. Authorization checked before config, DB or SDK access."""
import argparse,asyncio,json,time,socket
from pathlib import Path
from dataclasses import replace
from contextlib import asynccontextmanager
from mybot.web.server import create_app
from mybot.provider_failover import ProviderFailoverClient
from mybot.config import build_client
from mybot.tools.registry import ToolRegistry
from scripts.uat.server import credentials,private_json
from .plan import BATCH,PORT,LIMITS,MESSAGES,STEER,AUTHORIZATION,REQUIRED_AUTHORIZATION,config_for,plan_hash
from .budget import Ledger,BudgetStop
from .adapter import BudgetClient
from .prepare import verify_frozen


def require_authorization(value):
 if type(value) is not str or value!=REQUIRED_AUTHORIZATION:raise BudgetStop('new_live_authorization_not_granted')

class ReadRegistry(ToolRegistry):
 def __init__(self,original,allowed):
  super().__init__(mutation_enabled=False);self.allowed=frozenset(allowed)
  for tool in original.iter_tools():self.register(tool)
 def register(self,tool,**kw):
  if tool.name in self.allowed:super().register(tool,**kw)
 def permitted(self,name):return name in self.allowed and super().permitted(name)


def make_app(case,batch,provider_config,*,authorization=AUTHORIZATION,port=PORT):
 require_authorization(authorization)
 if case not in LIMITS or port!=PORT:raise BudgetStop('unregistered_case_or_port')
 frozen=verify_frozen(batch,provider_config)
 if frozen['usage']['unsettled']:raise BudgetStop('unsettled_request')
 batch=Path(batch).resolve();providers=credentials(provider_config);cfg=config_for(batch,providers['coco']);ledger=Ledger(batch/'private/requests.sqlite',plan_hash());box={'streams':[]}
 def verify():
  try:
   verify_frozen(batch,provider_config)
   if 'app' in box and (box['app'].runtime.cleanup_uncertain or not box['app'].runtime.closed and box['app'].runtime.event_store.workspace_uncertain()):raise BudgetStop('uncertain_execution')
  except Exception:ledger.halt('integrity_or_uncertainty');raise
 ledger.verify=verify
 def wrap(settings):return BudgetClient(build_client(settings).with_options(max_retries=0),settings,ledger,case,batch/'private',streams=box['streams'])
 def factory(settings):
  require_authorization(authorization)
  backup=replace(settings,provider='coco2',**{k:providers['coco2'][k] for k in ('model','base_url','api_key')})
  return ProviderFailoverClient(wrap(settings),settings,backup,wrap)
 # Process-local host restriction only. Same native AgentLoop, tools and authority.
 # No other Web process is touched. Restore the factory at lifespan exit.
 import mybot.web.runtime as module
 original_registry=module.build_default_tool_registry
 def restricted(*a,**kw):return ReadRegistry(original_registry(*a,**kw),['read_file','list_files'] if case=='R02' else [])
 try:app=create_app(cfg,port=port,client_factory=factory)
 except BaseException:
  module.build_default_tool_registry=original_registry;raise
 box['app']=app;start=app.runtime.start;steer=app.runtime.steer;stop=app.runtime.stop;lifespan=app.app.router.lifespan_context
 def meta(key,value=None):
  with ledger.connect() as db:
   if value is not None:db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,value));return
   row=db.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone();return row[0] if row else None
 def first():
  files=sorted((batch/'private').glob(case+'-*-first-chunk.json'))
  if not files:raise BudgetStop('first_chunk_not_observed')
  result=json.loads(files[0].read_text())
  if result['first_chunk_terminal']:raise BudgetStop('scenario_premise_not_met_no_rerun')
  return result
 async def accepted(c,text):
  verify()
  if text!=MESSAGES[case] or meta('session_'+case) is not None or c.messages:raise BudgetStop('unregistered_or_repeated_input')
  meta('session_'+case,c.id);meta('input_'+case,'1')
  result=await start(c,text)
  if not result:ledger.halt('turn_start_failed');raise BudgetStop('turn_start_failed')
  def settled(task):
   try:
    verify();private_json(batch/'private'/f'{case}-settled.json',dict(status=c.status,resources=c.resources,steers=c.state()['steers'],session_id=c.id,preview_status=c.stream_preview.get('status'),saved_reply_sha256=__import__('hashlib').sha256(c.messages[-1]['content'].encode()).hexdigest() if c.messages and c.messages[-1]['role']=='assistant' else None))
    if c.resources.get('output',{}).get('status') in ('provider_error','response_unconfirmed') or c.status in ('failed','cleanup_uncertain','execution_uncertain'):ledger.halt('protocol_or_runtime_failure')
   except Exception:ledger.halt('settlement_or_integrity_failure');app.runtime.cleanup_uncertain=True
  c.task.add_done_callback(settled);return result
 def user_steer(c,value):
  verify();first()
  if case not in STEER or value.get('text')!=STEER[case] or meta('session_'+case)!=c.id:raise BudgetStop('unregistered_steer')
  return steer(c,value)
 async def user_stop(c):
  verify()
  if case!='R04' or meta('session_'+case)!=c.id:
   ledger.halt('operator_abort');await stop(c);return
  first();meta('stop_'+case,'1');await stop(c)
 original_new=app.runtime.new
 def new():
  c=original_new();emit=c.emit;seen=set()
  def observe(event):
   emit(event)
   kind=event.get('type')
   if kind=='model_text_delta' and event.get('stream_id') not in seen and box['streams']:
    stream=box['streams'][-1];seen.add(event['stream_id'])
    private_json(batch/'private'/f'{case}-{stream.rid:02}-preview-emission.json',dict(server_monotonic=time.monotonic(),request_started=stream.start,chunks_before_first_sse_preview=stream.count,browser_dom_time='UNKNOWN; separate clock domain'))
   if kind in ('tool_started','tool_finished','steer_status'):
    with (batch/'private'/f'{case}-events.jsonl').open('a') as f:
     f.write(json.dumps(dict(monotonic=time.monotonic(),event=c.events[-1]),ensure_ascii=False)+'\n');f.flush();__import__('os').fsync(f.fileno())
  c.emit=observe;return c
 app.runtime.new=new
 app.runtime.start=accepted;app.runtime.steer=user_steer;app.runtime.stop=user_stop
 @asynccontextmanager
 async def owned_lifespan(application):
  try:
   verify();ledger.start(case);module.build_default_tool_registry=restricted
   # Original close invokes stop for idle sessions; restore stop only on shutdown.
   async with lifespan(application):
    try:yield
    finally:app.runtime.stop=stop
   if meta('input_'+case)!='1':ledger.halt('case_incomplete')
   verify();ledger.finish(case)
  finally:module.build_default_tool_registry=original_registry
 app.app.router.lifespan_context=owned_lifespan;app.uat_ledger=ledger
 return app

def main():
 p=argparse.ArgumentParser();p.add_argument('--case',choices=list(LIMITS),required=True);p.add_argument('--batch',type=Path,default=BATCH);p.add_argument('--provider-config',type=Path,required=True);p.add_argument('--authorization',default=AUTHORIZATION);a=p.parse_args();require_authorization(a.authorization)
 with socket.socket() as probe:probe.bind(('127.0.0.1',PORT))
 import uvicorn
 uvicorn.run(make_app(a.case,a.batch,a.provider_config,authorization=a.authorization),host='127.0.0.1',port=PORT,access_log=False,log_level='warning')
if __name__=='__main__':main()
