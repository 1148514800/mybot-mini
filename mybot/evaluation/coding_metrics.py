"""Metadata instrumentation and independent protocol audit, never transcript retention."""
import hashlib
import json
import re

from .trace import Trace, TracedAgent
from .coding_fixtures import snapshot
from .tool_agent import token_totals, usage_values, estimated_cost, pair_messages
from ..agent.coding_controller import test_runner, passed_tests
from ..tools.command_process import resolve_launch


class CodingTrace(Trace):
    def __init__(self):
        super().__init__();self.paired=True;self.revision=0;self.last_test_revision=None;self.hashes={};self.command_start=None

    def current_hashes(self):
        images=snapshot(self.workspace)
        return {p:hashlib.sha256(images[p].data).hexdigest() for p in self.hashes if p in images}

    def tool(self,name,arguments,result,duration):
        super().tool(name,arguments,result,duration)
        event=self.events[-1];meta=result.metadata
        try: args=json.loads(arguments) if isinstance(arguments,str) else arguments
        except (ValueError,TypeError): args={}
        args=args if isinstance(args,dict) else {}
        event.update(patch_preview=name=='apply_patch' and args.get('dry_run',True) is True,
            patch_write=name=='apply_patch' and args.get('dry_run') is False,
            patch_committed=name=='apply_patch' and result.success and meta.get('applied') is True,
            approval_denied=meta.get('permission_denied') is True,
            sandbox_failure=meta.get('status')=='sandbox_unavailable',
            stale_patch=result.error=='stale_file_hash',
            workspace_escape=result.error in ('path_outside_workspace','path_outside_root','invalid_path','path_escape'),
            execution_uncertain=meta.get('status') in ('partial_failure_possible','rollback_conflict','process_state_unknown'))
        if event['patch_committed']:
            self.revision+=1;self.hashes.update(meta['after_sha256']);self.last_test_revision=None
        event['real_test_run']=False;event['current_revision_test_evidence']=False
        if name=='run_command':
            runner=None
            try:
                runner=test_runner(resolve_launch(tuple(args.get('argv',())),self.workspace).argv)
                streams=json.loads(result.output); output=streams['stdout']+'\n'+streams['stderr']
            except (ValueError,KeyError,TypeError,IndexError,OSError): output=''
            ran=bool(re.search(r'^Ran [1-9][0-9]* tests? in [0-9.]+s$',output,re.M)) if runner=='unittest' else passed_tests(runner,output)>0
            complete=(meta.get('status')=='completed' and all(meta.get(k) is True for k in ('approved','spawned','completed','sandbox_applied'))
                and meta.get('execution_mode')=='macos_readonly' and not any(meta.get(k) for k in ('output_truncated','timed_out','encoding_replaced')))
            event['real_test_run']=bool(complete and runner and ran)
            try: match=self.command_start==self.hashes==self.current_hashes()
            except (ValueError,OSError): match=False
            valid=(complete and result.success and type(meta.get('exit_code')) is int and meta['exit_code']==0
                and passed_tests(runner,output)>0 and match and bool(self.hashes))
            if valid:self.last_test_revision=self.revision
            event['current_revision_test_evidence']=bool(valid)

    def protocol_valid(self):
        try:return bool(self.hashes) and self.last_test_revision==self.revision and self.current_hashes()==self.hashes
        except (ValueError,OSError):return False


class BenchmarkAgent(TracedAgent):
    """Instrumentation only. All decisions and execution remain in original Loop."""
    async def _execute(self,name,raw_arguments):
        if name=='run_command':
            try:self.trace.command_start=self.trace.current_hashes()
            except (ValueError,OSError):self.trace.command_start=None
        return await super()._execute(name,raw_arguments)


def case_metrics(trace,controller,messages,live):
    tools=[e for e in trace.events if e['event']=='tool']
    requests=[e for e in trace.events if e['event']=='llm_request']
    tokens=token_totals([usage_values(u) for u in trace.usage],len(requests)) if live else dict.fromkeys(('prompt_tokens','completion_tokens','total_tokens','cached_input_tokens'))
    return {'llm_requests':len(requests),'tool_calls':len(tools),'input_tokens':tokens['prompt_tokens'],
        'output_tokens':tokens['completion_tokens'],'total_tokens':tokens['total_tokens'],
        'cached_input_tokens':tokens['cached_input_tokens'],
        'search_calls':sum(e['name'] in ('search_code','list_files','git_status','git_diff') for e in tools),
        'read_calls':sum(e['name'] in ('read_file','read_file_range') for e in tools),
        **{key:sum(bool(e.get(event)) for e in tools) for key,event in [
            ('patch_preview_calls','patch_preview'),('patch_write_attempts','patch_write'),('committed_patches','patch_committed'),
            ('real_test_runs','real_test_run'),('stale_patch_conflicts','stale_patch'),('approval_denials','approval_denied'),
            ('command_denied_count','approval_denied'),('sandbox_failures','sandbox_failure'),('workspace_escape_attempts','workspace_escape')]},
        'command_attempts':sum(e['name']=='run_command' for e in tools),
        'schema_chars':sum(e.get('schema_chars',0) for e in requests),'repeated_actions':controller.get('repeated_actions',0),
        'budget_stops':int(controller.get('state')=='budget_exhausted'),
        'execution_uncertain_count':int(controller.get('state')=='execution_uncertain' or any(e.get('execution_uncertain') for e in tools)),
        'tool_call_ids_paired':trace.paired and pair_messages(messages,complete=True),
        'protocol_false_verified_count':int(controller.get('state')=='verified' and not trace.protocol_valid())}


def failure_reason(result):
    if result.get('runtime_error'):return result['runtime_error']
    metrics=result.get('metrics',{});state=result.get('agent_state');judge=result.get('judge',{})
    if metrics.get('approval_denials'):return 'approval_denied'
    if metrics.get('sandbox_failures'):return 'sandbox_unavailable'
    stop=result.get('controller',{}).get('stop_reason','')
    if stop=='max_model_requests':return 'model_request_budget'
    if stop=='max_task_seconds':return 'task_timeout'
    if stop=='max_no_progress':return 'repeated_action_loop'
    if stop.startswith('max_'):return 'tool_budget'
    if judge.get('judge_state') in ('invalid_case','grader_error','unscored'):return judge.get('failure') or 'grader_error'
    if judge.get('failure') in ('unexpected_file_change','index_changed','journal_attribution_mismatch'):return judge['failure']
    if state=='blocked' and stop:return stop
    if judge.get('verified_repair_success'):return None
    if not judge.get('modified_code'):
        return 'model_did_not_investigate' if not metrics.get('tool_calls') else 'no_code_change'
    if state=='verified' and judge.get('judge_state')=='hidden_fail':return 'public_tests_only'
    return judge.get('failure') or 'unknown'


def summarize(results, *, live, budget):
    attempted=[r for r in results if r['attempted']]
    eligible=[r for r in attempted if r['judge']['judge_state'] in ('hidden_pass','hidden_fail')]
    successes=[r for r in attempted if r['judge'].get('verified_repair_success')]
    hidden=[r for r in attempted if r['judge']['judge_state']=='hidden_pass']
    public=[r for r in eligible if r['judge'].get('public',{}).get('passed')]
    verified=[r for r in attempted if r['agent_state']=='verified']
    multi=[r for r in eligible if r.get('multi_file_task',r['difficulty']=='hard')]
    tokens=budget.tokens if live else dict.fromkeys(('prompt_tokens','completion_tokens','total_tokens','cached_input_tokens'))
    cost=estimated_cost(tokens,budget.prices) if live else None
    measured=live and budget.successes>0 and bool(eligible)
    from collections import Counter
    return {'total_cases':len(results),'attempted_cases':len(attempted),'eligible_cases':len(eligible),
        'hidden_pass_cases':len(hidden),'verified_repair_cases':len(successes),
        'verified_repair_rate':len(successes)/len(attempted) if measured and attempted else None,
        'real_model_repair_rate':len(successes)/len(attempted) if measured and attempted else None,
        'eligible_repair_rate':sum(r['judge'].get('verified_repair_success',False) for r in eligible)/len(eligible) if measured and eligible else None,
        'public_test_pass_rate':len(public)/len(eligible) if measured and eligible else None,
        'hidden_test_pass_rate':len(hidden)/len(attempted) if measured and attempted else None,
        'multi_file_repair_rate':sum(r['judge'].get('verified_repair_success',False) for r in multi)/len(multi) if measured and multi else None,
        'multi_file_eligible_cases':len(multi),'agent_verified_count':len(verified),
        'agent_workflow_success_cases':sum(r.get('agent_workflow_success',r['agent_state']=='verified') for r in attempted),
        'agent_blocked_count':sum(r['agent_state']=='blocked' for r in attempted),
        'hidden_pass_after_agent_verified':sum(r['judge']['judge_state']=='hidden_pass' for r in verified),
        'hidden_failure_after_agent_verified':sum(r['judge']['judge_state']=='hidden_fail' for r in verified),
        'edited_unverified_count':sum(r['agent_state']=='edited_unverified' for r in attempted),
        'premature_completion_count':sum(r.get('premature_completion_count',0) for r in attempted),
        'false_success_claim_count':sum(r['agent_state']=='verified' and not r['judge'].get('verified_repair_success') for r in attempted),
        'verification_expired_count':sum(bool(r['judge'].get('stale_final_version')) or (r['agent_state']=='edited_unverified' and r.get('controller',{}).get('test_passes',0)>0) for r in attempted),
        'infra_error_cases':sum(r['judge']['judge_state']=='grader_error' for r in results),
        'invalid_cases':sum(r['judge']['judge_state']=='invalid_case' for r in results),
        'unscored_cases':sum(r['judge']['judge_state']=='unscored' for r in results),
        'llm_requests':budget.state['used'],'successful_responses':budget.successes,'api_failures':budget.api_failures,'cancelled_requests':budget.cancelled,
        'input_tokens':tokens['prompt_tokens'],'output_tokens':tokens['completion_tokens'],'total_tokens':tokens['total_tokens'],
        'actual_tokens':tokens['total_tokens'],'cached_input_tokens':tokens['cached_input_tokens'],
        'estimated_cost':cost,'estimated_cost_per_success':({'currency':cost['currency'],'amount':cost['amount']/len(successes)} if cost and successes else None),
        'failures':dict(Counter(r['failure'] for r in results if r.get('failure'))),
        **{k:sum(r['metrics'].get(k,0) for r in attempted) for k in ('tool_calls','search_calls','read_calls','patch_preview_calls','patch_write_attempts','committed_patches','command_attempts','real_test_runs','schema_chars','repeated_actions','stale_patch_conflicts','approval_denials','sandbox_failures','budget_stops','workspace_escape_attempts','command_denied_count','execution_uncertain_count','protocol_false_verified_count')},
        **{k:sum(r['judge'].get(k,0) for r in results) for k in ('unrelated_file_changes','protected_file_changes','index_changed','journal_attribution_mismatch')},
        'tool_call_ids_paired':all(r['metrics'].get('tool_call_ids_paired',False) for r in attempted)}
