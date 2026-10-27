"""Future authorized entry, same native Web/Agent/SDK; admission != HTTP evidence."""
import argparse,json,time,socket,re
from pathlib import Path
from dataclasses import replace
from contextlib import asynccontextmanager,closing
from mybot.web.server import create_app
from mybot.provider_failover import ProviderFailoverClient
from mybot.config import build_client
from mybot.workspace_lease import WorkspaceLease
from scripts.streaming_steer_uat.server import ReadRegistry
from scripts.uat.server import credentials,private_json
from .plan import BATCH,PORT,LIMITS,MESSAGES,STEER,AUTHORIZATION,REQUIRED_AUTHORIZATION,config_for,plan_hash,BARRIER,IDENTIFIER
from .budget import Ledger,BudgetStop
from .adapter import BudgetClient
from .prepare import verify_frozen,ro
from .evidence import digest,target,tool_name

def require_authorization(value):
 if type(value) is not str or value!=REQUIRED_AUTHORIZATION:raise BudgetStop('new_live_authorization_not_granted')

def owned_app(case,batch,cfg,backup,ledger,builder,verify,port,*,barriers=BARRIER):
 batch=Path(batch);streams=[];requests=[];events=[];box={};result={};used=False;steered=False;stopped=False
 def save_events():private_json(batch/'private'/f'{case}-events.json',events)
 def source_rows():
  c=box.get('conversation')
  return [] if c is None else app.runtime.event_store.query("SELECT event_id,session_id,sequence,source,payload FROM events WHERE session_id=? AND event_type='steer.queued' ORDER BY sequence LIMIT 32",(c.id,))
 def wrap(settings):return BudgetClient(builder(settings),settings,ledger,case,streams,requests,source_rows,batch/'private',barriers)
 def factory(settings):return ProviderFailoverClient(wrap(settings),settings,backup,wrap)
 import mybot.web.runtime as module
 original_registry=module.build_default_tool_registry
 def restricted(*a,**kw):return ReadRegistry(original_registry(*a,**kw),['list_files','read_file'] if case=='T01' else [])
 app=create_app(cfg,port=port,client_factory=factory);start=app.runtime.start;steer=app.runtime.steer;stop=app.runtime.stop;new=app.runtime.new;lifespan=app.app.router.lifespan_context
 def remember(row):
  if len(events)>=256:ledger.halt('evidence_limit');raise BudgetStop('evidence_limit')
  events.append(dict(monotonic=time.monotonic(),**row));save_events()
 def observed_new():
  c=new();emit=c.emit
  def observe(e):
   emit(e);kind=e.get('type')
   if kind=='model_text_delta' and streams and 'first_sse_emit' not in streams[-1].row:streams[-1].row['first_sse_emit']=time.monotonic()
   if kind=='steer_status':
    s=e['steer'];remember(dict(stage='native_on_dispatch_admitted' if s['status']=='applied' else s['status'],steer_id=s['steer_id'],source_event_id=s['source_event_id'],turn_id=s['turn_id'],registered_text_match=s['text']==STEER.get(case)))
   if kind=='tools_deferred_by_steer':remember(dict(stage=kind,count=e.get('count')))
   if kind in ('tool_started','tool_finished'):
    if e.get('tool') not in (('read_file','list_files') if case=='T01' else ()):
     box['authority_anomaly']=True;ledger.halt('authority_anomaly')
    meta=e.get('metadata') or {};path=meta.get('relative_path');category=target(json.dumps({'path':path})) if path else 'unknown'
    remember(dict(stage=kind,call_id_sha256=digest(e.get('call_id','')),tool=tool_name(e.get('tool')),success=e.get('success') if type(e.get('success')) is bool else None,target=category))
  c.emit=observe;return c
 app.runtime.new=observed_new
 def first_delivered():
  if not any(s.first_delivered for s in streams):raise BudgetStop('first_nonterminal_not_delivered')
 def settle(c):
  try:
   for stream in streams:stream.finalize()
   verify(True)
   evidence=[s.evidence() for s in streams];rows=[r for r in ledger.rows() if r['case_id']==case]
   errors=[s['diagnostic']['error_code'] for s in evidence if s.get('diagnostic') and s['diagnostic']['error_code']]
   protocol_failure=any(s.get('diagnostic') and s['diagnostic']['error_code'] and s['diagnostic']['error_code']!='stream_user_or_caller_cancelled' and not (s['chunks']==0 and s['diagnostic']['error_code'] in ('stream_transport_interrupted','stream_local_timeout')) for s in evidence) or c.status in ('execution_uncertain','cleanup_uncertain','failed') or any(not s.closed for s in streams)
   if case!='T03' and (not streams or not streams[-1].physical.get('terminal_trusted')):protocol_failure=True
   protocol_failure=protocol_failure or box.get('authority_anomaly',False)
   if protocol_failure:ledger.halt('protocol_or_runtime_failure')
   records=c.steer_inbox.records.values() if c.steer_inbox else []
   safe_steers=[{k:v for k,v in s.items() if k in ('steer_id','source_event_id','turn_id','status','cause')} for s in records]
   stored=app.runtime.event_store.query("SELECT content FROM messages WHERE session_id=? AND role='assistant' ORDER BY rowid DESC LIMIT 1",(c.id,));reply=stored[0]['content'] if stored else ''
   premise=bool(any(s.first_delivered for s in streams) and (steered if case in STEER else stopped))
   outcome='failed' if protocol_failure else 'completed' if premise else 'inconclusive'
   result.update(case=case,session_id=c.id,status=c.status,scenario_premise= 'MET' if premise else 'INCONCLUSIVE',streams=evidence,requests=requests,host_events=events,steers=safe_steers,logical_requests=c.resources.get('logical_requests'),physical_reservations=len(rows),actual_http_attempts=sum(r['http_attempts'] for r in rows),provider_models=[{'provider':r['provider'],'model':r['model']} for r in rows],fallback_dispatches=sum(bool(r['native_is_fallback'] and r['http_attempts']) for r in requests),
    saved_reply_sha256=digest(reply) if stored else None,final_persistence_matches_sdk=bool(stored and evidence and evidence[-1]['terminal_trusted'] and evidence[-1]['reply_sha256']==digest(reply)),reply_features=dict(identifier_present=IDENTIFIER in reply,sentence_terminal_marks=len(re.findall(r'[。！？.!?](?:[\s\n]|$)',reply)),characters=len(reply),semantic_adherence='REQUIRES_INDEPENDENT_OPERATOR_REVIEW'),protocol_security_halt=protocol_failure,cost=None)
   private_json(batch/'private'/f'{case}-settled.json',result);ledger.finish(case,outcome)
  except Exception:
   app.runtime.cleanup_uncertain=True;ledger.halt('settlement_or_integrity_failure')
   private_json(batch/'private'/f'{case}-settlement-failure.json',dict(stage='turn_settlement',cleanup_uncertain=True,streams=[s.evidence() for s in streams]))
 async def accepted(c,text):
  nonlocal used
  verify(False)
  if used or text!=MESSAGES[case] or c.messages:raise BudgetStop('unregistered_or_repeated_input')
  used=True;box['conversation']=c
  ok=await start(c,text)
  if not ok:ledger.halt('turn_start_failed');raise BudgetStop('turn_start_failed')
  c.task.add_done_callback(lambda _:settle(c));return ok
 def user_steer(c,value):
  nonlocal steered
  verify(False);first_delivered()
  if steered or case not in STEER or value.get('text')!=STEER[case] or value.get('expected_turn_id')!=c.history.turn_id or box.get('conversation') is not c:raise BudgetStop('unregistered_steer')
  unchanged=all(digest(s.request)==s.row['sdk_request_sha256'] for s in streams)
  row=steer(c,value);steered=True;remember(dict(stage='web_steer_accepted',turn_id=row['turn_id'],steer_id=row['steer_id'],source_event_id=row['source_event_id'],in_flight_request_unchanged=unchanged));return row
 async def user_stop(c):
  nonlocal stopped
  if case!='T03' or box.get('conversation') is not c:ledger.halt('operator_abort');await stop(c);return
  verify(False);first_delivered();stopped=True;remember(dict(stage='web_stop_accepted'));await stop(c)
 app.runtime.start=accepted;app.runtime.steer=user_steer;app.runtime.stop=user_stop
 @asynccontextmanager
 async def owned_lifespan(application):
  try:
   verify(False);ledger.start(case);module.build_default_tool_registry=restricted
   async with lifespan(application):yield
   verify(True)
   if not used:ledger.halt('case_incomplete');ledger.finish(case,'inconclusive')
   lease=WorkspaceLease(cfg.workspace).acquire();lease.release()
   with closing(ro(cfg.session_event_path)) as db:consistent=db.execute('pragma integrity_check').fetchone()[0]=='ok'
   private_json(batch/'private'/f'{case}-cleanup.json',dict(runtime_closed=app.runtime.closed,cleanup_uncertain=app.runtime.cleanup_uncertain,sdk_streams_closed=all(s.closed for s in streams),lease_released=True,database_consistent=consistent,process_exit_code=None))
  finally:module.build_default_tool_registry=original_registry
 app.app.router.lifespan_context=owned_lifespan;app.uat_ledger=ledger;app.uat_streams=streams;app.uat_requests=requests;app.uat_result=result
 return app

def make_app(case,batch,provider_config,*,authorization=AUTHORIZATION):
 require_authorization(authorization)
 if case not in LIMITS:raise BudgetStop('unknown_case')
 f=verify_frozen(batch,provider_config)
 if f['usage']['unsettled']:raise BudgetStop('unsettled_request')
 providers=credentials(provider_config);cfg=config_for(batch,providers['coco']);ledger=Ledger(Path(batch)/'private/requests.sqlite',plan_hash())
 backup=replace(cfg,provider='coco2',**{k:providers['coco2'][k] for k in ('model','base_url','api_key')})
 def verify(allow_halt=False):return verify_frozen(batch,provider_config,allow_halt=allow_halt)
 ledger.verify=lambda:verify(False)
 return owned_app(case,batch,cfg,backup,ledger,lambda settings:build_client(settings).with_options(max_retries=0),verify,PORT)
def main():
 p=argparse.ArgumentParser();p.add_argument('--case',choices=list(LIMITS),required=True);p.add_argument('--batch',type=Path,default=BATCH);p.add_argument('--provider-config',type=Path,required=True);p.add_argument('--authorization',default=AUTHORIZATION);a=p.parse_args();require_authorization(a.authorization)
 with socket.socket() as probe:probe.bind(('127.0.0.1',PORT))
 import uvicorn
 uvicorn.run(make_app(a.case,a.batch,a.provider_config,authorization=a.authorization),host='127.0.0.1',port=PORT,access_log=False,log_level='warning')
if __name__=='__main__':main()
