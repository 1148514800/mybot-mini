"""Single authorized Live entry; native runtime plus restrictive operator gates."""
import argparse,hashlib,json,socket,time
from contextlib import closing
from pathlib import Path
from dataclasses import replace
from contextlib import asynccontextmanager
from mybot.web.server import create_app
from mybot.provider_failover import ProviderFailoverClient
from mybot.config import build_client
from mybot.workspace_lease import WorkspaceLease
from scripts.streaming_steer_uat.server import ReadRegistry
from scripts.uat.server import credentials,private_json
from .plan import BATCH,PORT,AUTHORIZATION,REQUIRED_AUTHORIZATION,MESSAGE,config_for,plan_hash
from .budget import Ledger,BudgetStop
from .adapter import BudgetClient
from .prepare import verify_frozen,ro

def require_authorization(value):
 if type(value) is not str or value!=REQUIRED_AUTHORIZATION:raise BudgetStop('new_live_authorization_not_granted')

def owned_app(batch,cfg,backup,ledger,client_builder,verify,port):
 """Shared harness for Live and separate MockTransport fixture, never swaps production code."""
 batch=Path(batch);streams=[];accountings=[];result={};used=False
 def wrap(settings):return BudgetClient(client_builder(settings),settings,ledger,streams,accountings)
 def factory(settings):return ProviderFailoverClient(wrap(settings),settings,backup,wrap)
 import mybot.web.runtime as module
 original_registry=module.build_default_tool_registry
 def restricted(*a,**kw):return ReadRegistry(original_registry(*a,**kw),[])
 app=create_app(cfg,port=port,client_factory=factory);start=app.runtime.start;new=app.runtime.new;lifespan=app.app.router.lifespan_context
 def observe_new():
  c=new();emit=c.emit
  def emit_observed(event):
   emit(event)
   if event.get('type')=='model_text_delta' and streams and streams[-1].first_sse is None:streams[-1].first_sse=time.monotonic()
  c.emit=emit_observed;return c
 app.runtime.new=observe_new
 def settle(c):
  try:
   verify(True)
   evidence=[s.evidence() for s in streams]
   stored=app.runtime.event_store.query("SELECT content FROM messages WHERE session_id=? AND role='assistant' ORDER BY rowid DESC LIMIT 1",(c.id,))
   digest=hashlib.sha256(stored[0]['content'].encode()).hexdigest() if stored else None
   stream=evidence[0] if len(evidence)==1 else {}
   diagnostic=stream.get('diagnostic') or {}
   passed=bool(c.status=='completed' and stream.get('terminal_trusted') and stream.get('natural_eof') and stream.get('sdk_closed') and diagnostic.get('error_code') is None and stream.get('stream_status')=='complete' and digest==stream.get('assembled_stripped_sha256'))
   rows=ledger.rows()
   result.update(protocol='PASS' if passed else 'FAIL',session_id=c.id,status=c.status,streams=evidence,saved_reply_sha256=digest,trusted_final_persisted=passed,
    physical_requests=len(rows),http_attempts=sum(r['http_attempts'] for r in rows),providers=[r['provider'] for r in rows],models=[r['model'] for r in rows],opening_error_types=[r['error_type'] for r in rows if r['error_type']],observed_usage=[s.usage for s in streams],usage=[json.loads(r['usage']) if r['usage'] else None for r in rows],cost=None,
    fallback_dispatch_blocked=any(r.get('is_fallback') and r.get('http_dispatch_attempts')==0 for a in accountings for r in a.records),
    accounting_admission_records=sum(len(a.records) for a in accountings),accounting_note='includes blocked fallback admission; durable reservations and HTTP hook are authoritative physical counts')
   private_json(batch/'private/diagnostics.json',result)
   ledger.finish('D02',passed)
  except Exception:
   ledger.halt('settlement_or_integrity_failure');app.runtime.cleanup_uncertain=True
 async def accepted(c,text):
  nonlocal used
  verify(False)
  if used or text!=MESSAGE or c.messages:raise BudgetStop('unregistered_or_repeated_input')
  used=True
  ok=await start(c,text)
  if not ok:ledger.halt('turn_start_failed');raise BudgetStop('turn_start_failed')
  c.task.add_done_callback(lambda _:settle(c));return ok
 def no_steer(*a,**kw):raise BudgetStop('steer_disabled')
 app.runtime.start=accepted;app.runtime.steer=no_steer
 @asynccontextmanager
 async def owned_lifespan(application):
  try:
   verify(False);ledger.start('D02');module.build_default_tool_registry=restricted
   async with lifespan(application):yield
   # No admission check here: HALT must not prohibit closing our resources.
   verify(True)
   if not used:ledger.finish('D02',False)
   lease=WorkspaceLease(cfg.workspace).acquire();lease.release()
   with closing(ro(cfg.session_event_path)) as db:
    consistent=db.execute('pragma integrity_check').fetchone()[0]=='ok'
   private_json(batch/'private/cleanup.json',dict(runtime_closed=app.runtime.closed,cleanup_uncertain=app.runtime.cleanup_uncertain,sdk_streams_closed=all(s.closed for s in streams),lease_released=True,database_consistent=consistent,process_exit_code=None,note='operator must independently verify exit code and port; this is lifespan evidence only'))
  finally:module.build_default_tool_registry=original_registry
 app.app.router.lifespan_context=owned_lifespan;app.uat_ledger=ledger;app.canary_streams=streams;app.canary_result=result
 return app

def make_app(batch,provider_config,authorization=AUTHORIZATION):
 require_authorization(authorization)
 checked=verify_frozen(batch,provider_config)
 if any(checked['usage'][k] for k in ('real_requests','attempts','unsettled','http_attempts')):raise BudgetStop('batch_already_used')
 batch=Path(batch).resolve();providers=credentials(provider_config);cfg=config_for(batch,providers['coco']);ledger=Ledger(batch/'private/requests.sqlite',plan_hash())
 backup=replace(cfg,provider='coco2',**{k:providers['coco2'][k] for k in ('model','base_url','api_key')})
 def verify(allow_halt=False):return verify_frozen(batch,provider_config,allow_halt=allow_halt)
 ledger.verify=lambda:verify(False)
 return owned_app(batch,cfg,backup,ledger,lambda settings:build_client(settings).with_options(max_retries=0),verify,PORT)

def main():
 p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,default=BATCH);p.add_argument('--provider-config',type=Path,required=True);p.add_argument('--authorization',default=AUTHORIZATION);a=p.parse_args();require_authorization(a.authorization)
 with socket.socket() as probe:probe.bind(('127.0.0.1',PORT))
 import uvicorn
 uvicorn.run(make_app(a.batch,a.provider_config,a.authorization),host='127.0.0.1',port=PORT,access_log=False,log_level='warning')
if __name__=='__main__':main()
