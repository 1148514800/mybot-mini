"""Independent isolated business grading and cross-file attribution dimensions."""
from mybot.evaluation.coding_judge import run_suite
from mybot.evaluation.coding_fixtures import snapshot
from scripts.coding_workflow_canary_v1.score import assess as base_assess
from .fixture import images
from .plan import ALLOWED
async def acceptance(workspace):
 candidate=snapshot(workspace);trusted=images(hidden=True)
 for n in ALLOWED:trusted[n]=candidate[n]
 public=await run_suite(trusted,8,hidden=False,timeout=10,output_limit=8192)
 hidden=await run_suite(trusted,18,hidden=True,timeout=10,output_limit=8192)
 return dict(public=public,host_acceptance=hidden,isolated=True,strict_functional_pass=public['passed'] and hidden['passed'])
async def validate_fixture():
 return {label:await run_suite(images(fixed=fixed,hidden=True),18 if hidden else 8,hidden=hidden,timeout=10,output_limit=8192) for label,fixed,hidden in [('baseline_public',False,False),('baseline_host',False,True),('reference_public',True,False),('reference_host',True,True)]}
def assess(evidence,functional,**kwargs):
 result=base_assess(evidence,functional,**kwargs);chain=evidence.get('native_patch_chain',[])
 owned=set().union(*(set(e.get('changed_files',[])) for e in chain))
 both=owned==set(ALLOWED) and bool(chain) and all(chain[0]['before_hashes'][n]!=chain[-1]['after_hashes'][n] for n in ALLOWED)
 result['dimensions']['both_files_legally_modified']=both
 result['dimensions']['user_task_correctness'] &= both
 result['strict_success']=all(result['dimensions'].values())
 result['synthetic_workflow_pass'] &= both
 tools=[t for t in evidence.get('tools',[]) if t.get('tool')=='record_task_contract']
 result['contract_metadata']=dict(contract_tool_calls=len(tools),contract_tool_success=sum(t.get('success',False) for t in tools),contract_tool_rejection=sum(not t.get('success',False) for t in tools),provenance_coverage='UNKNOWN',independent_requirement_coverage='UNKNOWN')
 return result
