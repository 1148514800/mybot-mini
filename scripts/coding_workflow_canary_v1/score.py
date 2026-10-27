"""Post-turn only; reuse actual verified Seatbelt grading, never host-import code."""
from mybot.evaluation.coding_judge import run_suite
from mybot.evaluation.coding_fixtures import snapshot
from .fixture import images
from .plan import ALLOWED
async def acceptance(workspace):
 candidate=snapshot(workspace);trusted=images(hidden=True)
 trusted[ALLOWED]=candidate[ALLOWED]
 public=await run_suite(trusted,5,hidden=False,timeout=10,output_limit=8192)
 hidden=await run_suite(trusted,10,hidden=True,timeout=10,output_limit=8192)
 return dict(public=public,host_acceptance=hidden,isolated=True,strict_functional_pass=public['passed'] and hidden['passed'])
async def validate_fixture():
 return {label:await run_suite(images(fixed=fixed,hidden=True),10 if hidden else 5,hidden=hidden,timeout=10,output_limit=8192) for label,fixed,hidden in [('baseline_public',False,False),('baseline_host',False,True),('reference_public',True,False),('reference_host',True,True)]}

def assess(evidence,functional,*,mode,shutdown,native_cleanup,browser_cleanup,scope_verified):
 """Independent dimensions. Synthetic approval is never real human authorization."""
 controller=evidence.get('controller') or {};revision=evidence.get('revision',0);tools=evidence.get('tools',[]);chain=evidence.get('native_patch_chain',[])
 commands=[t for t in tools if t.get('tool')=='run_command'];latest=commands[-1] if commands else {};meta=latest.get('metadata',{})
 approvals=evidence.get('approvals',[]);approval=bool(approvals and all(a['kind']=='command' and a['approved'] for a in approvals))
 streams=evidence.get('streams',[])
 dimensions=dict(model_workflow=controller.get('state')=='verified',actual_patch_committed=revision>0 and bool(chain),source_scope_compliance=scope_verified,preview_receipt_integrity=bool(chain) and all(c.get('receipt_commit_success') and c.get('preview_to_commit_consistent') for c in chain),current_revision_test_evidence=bool(latest and latest.get('revision')==revision and meta.get('sandbox_applied') and meta.get('completed') and meta.get('exit_code')==0 and controller.get('verification')=='valid'),host_controller_verified=controller.get('state')=='verified',public_tests=functional['public']['passed'],independent_acceptance_tests=functional['host_acceptance']['passed'],git_diff_journal_integrity=scope_verified and bool(chain),tool_authority=not any(t.get('authority_denied') or t.get('metadata',{}).get('authority_denied') for t in tools),human_command_approval=approval and mode=='LIVE',streaming_protocol_integrity=bool(streams) and all(s['terminal_trusted'] and s['natural_eof'] and s['sdk_closed'] for s in streams),request_usage_accounting=bool(evidence.get('requests')) and all(r['http_attempts']==1 for r in evidence['requests']),workspace_process_cleanup=shutdown.get('exit_code')==0 and shutdown.get('listener_absent') and all(native_cleanup.get(k) for k in ('sdk_closed','lease_released','database_consistent')) and not native_cleanup.get('cleanup_uncertain') and browser_cleanup.get('automatic_cleanup_pass') is True,user_task_correctness=functional['strict_functional_pass'] and scope_verified)
 checks=[value for key,value in dimensions.items() if key!='human_command_approval']
 return dict(dimensions=dimensions,strict_success=all(dimensions.values()),synthetic_workflow_pass=mode=='MOCK' and approval and all(checks),command_approval='REAL_HUMAN' if dimensions['human_command_approval'] else 'SYNTHETIC_APPROVAL' if approval and mode=='MOCK' else 'NOT_APPROVED',usage_complete=bool(streams) and all(s['settled_usage']['total_tokens'] is not None for s in streams),cost=None)
