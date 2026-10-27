"""Native Coding runtime plus host-only scope/integrity checks; no second loop."""
import argparse,json,time
from pathlib import Path
from dataclasses import replace
from contextlib import asynccontextmanager,closing
from mybot.web.server import create_app
from mybot.provider_failover import ProviderFailoverClient
from mybot.config import build_client
from mybot.workspace_lease import WorkspaceLease
from scripts.uat.server import credentials,private_json
from scripts.uat_operator.ports import serve
from .plan import *
from .budget import Ledger,BudgetStop
from .adapter import BudgetClient
from .integrity import IntegrityGate

async def native_scope_execute(original,registry,gate,ledger,events,name,args):
 patch=registry.get_tool('apply_patch');journal=patch.observer
 try:before=gate.verify(journal)
 except Exception:ledger.halt('integrity_drift');raise
 if name not in TOOLS:return registry.denied()
 if name=='run_command' and (args.get('argv')!=COMMAND or args.get('cwd','.')!='.' or args.get('timeout_seconds',30)>30):
  events.append(dict(tool=name,authority_denied=True,executed=False));ledger.halt('unregistered_command');return registry.denied()
 if name=='apply_patch':
  changes=args.get('changes')
  if changes is None and patch._receipt is not None:changes=json.loads(patch._receipt.changes)
  if changes is not None and (not isinstance(changes,list) or any(type(c) is not dict or c.get('path') not in ALLOWED or c.get('op')!='update' for c in changes)):
   events.append(dict(tool=name,authority_denied=True,executed=False));ledger.halt('patch_scope_denied');return registry.denied()
 result=await original(name,args)
 meta=result.metadata
 if meta.get('partial_failure_possible') or meta.get('status') in ('partial_failure_possible','rollback_conflict'):
  events.append(dict(tool=name,success=False,revision=journal.revision,metadata={k:meta[k] for k in ('status','rollback_status','failure_phase','safe_error_code','safe_to_retry') if k in meta}))
  ledger.halt('partial_publication_uncertain');raise BudgetStop('partial_publication_uncertain')
 if name=='apply_patch' and result.success and meta.get('applied'):
  try:gate.accept_native_patch(before,journal,result)
  except Exception:ledger.halt('patch_attribution_uncertain');raise
 else:
  try:gate.verify(journal)
  except Exception:ledger.halt('unknown_tool_drift');raise
 safe=('error_category','safe_error_code','failure_phase','safe_to_retry','file_metadata_supported','dry_run','applied','receipt_created','receipt_commit_success','preview_to_commit_consistent','file_revision_verified','after_sha256','before_sha256','changed_files','status','approved','completed','spawned','sandbox_applied','exit_code','execution_mode','execution_evidence','permission_denied','authority_denied','process_terminated','output_truncated','timed_out')
 events.append(dict(tool=name,success=result.success,error_code=result.error if isinstance(result.error,str) and result.error.isidentifier() else None,target=args.get('path') if name=='read_file_range' and args.get('path') in (*ALLOWED,'tests/test_csvmini.py') else None,metadata={k:meta[k] for k in safe if k in meta},revision=gate.verify()['revision']))
 return result

def owned_app(batch,cfg,backup,ledger,builder,verify,port,approval_timeout=90):
 batch=Path(batch);gate=IntegrityGate(cfg.workspace,batch/'private/integrity.json');box={};streams=[];requests=[];events=[];used=False
 import mybot.web.runtime as module
 factory=module.build_default_tool_registry
 def restricted(*args,**kwargs):
  registry=factory(*args,**kwargs);original=registry.execute
  async def guarded(name,params):
   try:return await native_scope_execute(original,registry,gate,ledger,events,name,params)
   finally:private_json(batch/'private/tool-evidence.json',events)
  registry.execute=guarded;box['registry']=registry;return registry
 def current_verify(allow_halt=False):
  verify(allow_halt);r=box.get('registry');gate.verify(r.get_tool('apply_patch').observer if r else None)
 def wrap(settings):return BudgetClient(builder(settings),settings,ledger,'C02',streams,requests,lambda:[],batch/'private')
 ledger.verify=lambda:current_verify(False)
 def client(settings):return ProviderFailoverClient(wrap(settings),settings,backup,wrap)
 app=create_app(cfg,port=port,client_factory=client,approval_timeout=approval_timeout,task_timeout=1200);start=app.runtime.start;native=app.app.router.lifespan_context
 async def accepted(c,text):
  nonlocal used
  current_verify()
  if used or c.messages or text!=MESSAGE:raise BudgetStop('unregistered_or_repeated_input')
  used=True;ok=await start(c,text);box['conversation']=c
  def settle(_):
   try:
    for s in streams:s.finalize()
    current_verify(True);e=[s.evidence() for s in streams]
    dangerous=c.status in ('cleanup_uncertain','execution_uncertain') or any(not s.closed for s in streams)
    if dangerous:ledger.halt('uncertain_execution')
    if any(s.get('diagnostic',{}).get('error_code') not in (None,'stream_user_or_caller_cancelled') for s in e):ledger.halt('protocol_failure')
    state=gate.verify();report=dict(c.report or {});approvals=[dict(kind=a['kind'],approved=a['approved']) for a in c.approval.audit]
    private_json(batch/'private/settled.json',dict(status=c.status,controller=report,revision=state['revision'],native_patch_chain=state['native_patch_chain'],tools=events,approvals=approvals,streams=e,requests=requests,session_id=c.id,uncertain=dangerous,logical_requests=c.resources.get('logical_requests'),cost=None))
    ledger.finish('C02','failed' if dangerous else 'completed')
   except Exception:ledger.halt('settlement_uncertain');private_json(batch/'private/settlement-failure.json',dict(uncertain=True));app.runtime.cleanup_uncertain=True
  c.task.add_done_callback(settle);return ok
 app.runtime.start=accepted
 @asynccontextmanager
 async def lifespan(application):
  try:
   current_verify();ledger.start('C02');module.build_default_tool_registry=restricted
   async with native(application):yield
   current_verify(True)
   if not used:ledger.halt('case_not_submitted');ledger.finish('C02','inconclusive')
   lease_released=False
   if not app.runtime.cleanup_uncertain:
    lease=WorkspaceLease(cfg.workspace).acquire();lease.release();lease_released=True
   else:ledger.halt('cleanup_uncertain')
   from scripts.streaming_steer_recovery_v3.prepare import ro
   with closing(ro(cfg.session_event_path)) as db:consistent=db.execute('pragma integrity_check').fetchone()[0]=='ok'
   private_json(batch/'private/cleanup.json',dict(runtime_closed=app.runtime.closed,sdk_closed=all(s.closed for s in streams),lease_released=lease_released,database_consistent=consistent,cleanup_uncertain=app.runtime.cleanup_uncertain))
  finally:module.build_default_tool_registry=factory
 app.app.router.lifespan_context=lifespan;app.uat_ledger=ledger;app.uat_gate=gate;app.uat_streams=streams;app.uat_events=events;return app

def main():
 p=argparse.ArgumentParser();p.add_argument('--provider-config',type=Path,required=True);p.add_argument('--authorization',default=AUTHORIZATION);p.add_argument('--status-file',type=Path,required=True);a=p.parse_args()
 if a.authorization!=REQUIRED_AUTHORIZATION:raise BudgetStop('new_model_authorization_required')
 from .prepare import verify_frozen
 verify_frozen(BATCH,a.provider_config)
 providers=credentials(a.provider_config);cfg=config_for(BATCH,providers['coco']);backup=replace(cfg,provider='coco2',**providers['coco2'])
 serve(lambda port:owned_app(BATCH,cfg,backup,Ledger(BATCH/'private/requests.sqlite',plan_hash()),lambda c:build_client(c).with_options(max_retries=0),lambda allow:verify_frozen(BATCH,a.provider_config,allow_halt=allow),port),PORT,a.status_file)
if __name__=='__main__':main()
