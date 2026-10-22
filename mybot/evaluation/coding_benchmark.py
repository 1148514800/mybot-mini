"""Original Coding Agent over public repositories; private Judge runs only after it."""
import asyncio
import contextlib
import copy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import partial
import hashlib
import io
import json
import math
import sys
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as N

from ..agent import ContextBuilder
from ..agent.git_workflow import GitBaseline
from ..config import GatewayConfig, PROJECT_DIR
from ..tools import build_default_tool_registry
from ..tools.git_tools import GitStatusTool
from ..tools.command_approval import cli_command_approval
from ..mcp_client.approval import ApprovalDecision
from .coding_fixtures import load_benchmark, create_repository, snapshot, report_paths
from .coding_judge import validate_benchmark, trusted_seal, judge
from .coding_live import Limits, RequestBudget, CodingClient, CodingEvaluationStop, live_client, labels
from .coding_lifecycle import Attempt, WorkspaceDirectory
from .coding_approval import AttemptApproval
from .coding_metrics import CodingTrace, BenchmarkAgent, case_metrics, summarize, failure_reason, failure_classification
from .runner import select_cases, save_report as _save_report
from .tool_agent import safe_label, estimated_cost


class OfflineClient:
    """No repair policy or Gold. A completion claim is deliberately not evidence."""
    def __init__(self):self.chat=N(completions=N(create=self.create))
    async def create(self,**kwargs):
        return N(choices=[N(message=N(content='Fixed; all tests passed.',tool_calls=None),finish_reason='stop')],usage=None)


async def synthetic_approval(request):
    # Only the host's built-in temporary fixtures use this offline provider.
    return ApprovalDecision.APPROVE


def configuration(base, workspace, limits):
    return replace(base,workspace=workspace,session_persist=False,session_path=workspace.parent/'unused-session.json',
        skills_enabled=False,mcp_enabled=False,mcp_servers={},mcp_discovery={'enabled':False},debug=False,
        coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'macos_readonly','timeout_seconds':30,'max_output_bytes':32768},
        coding_autonomy={'enabled':True,'max_model_requests':limits.max_model_requests_per_case,'max_task_seconds':math.ceil(limits.task_timeout)},
        coding_git_workflow={'enabled':True,'undo_enabled':False},context_enabled=True,context_max_chars=160000,
        context_tool_result_max_chars=24000,max_react_steps=30,max_completion_tokens=limits.max_output_tokens,
        request_timeout_seconds=limits.request_timeout)


def selected_cases(benchmark, ids, maximum, seed=24):
    rows=[{'id':c.runtime.id,'case':c} for c in benchmark.cases]
    if ids is None:
        import random
        random.Random(seed).shuffle(rows)
    return [row['case'] for row in select_cases(rows,ids,maximum)]


async def run_task(case, validation, benchmark, seal, parent, *, repeat, limits, budget, base, raw,
                   live, offline_client_factory=None, command_provider=None, execution_identity=None, terminal_sink=None,
                   _adapter_factory=None):
    result={'case_id':case.runtime.id,'difficulty':case.runtime.difficulty,'repeat':repeat,'attempted':False,
        'agent_state':None,'agent_workflow_success':False,'controller':{},'metrics':{},'runtime_error':None,'multi_file_task':len(case.reference)>1,
        'judge':{'judge_state':'unscored','failure':'not_started','verified_repair_success':False}}
    if validation['status']!='valid':
        result['judge'].update(judge_state='invalid_case' if validation['status']=='invalid_benchmark_case' else 'grader_error',failure=validation['status'])
        result['failure']=validation['status'];return result
    try:budget.check()
    except CodingEvaluationStop as exc:
        result['judge']['failure']=exc.category;result['failure']=exc.category;return result
    if not benchmark.unchanged() or trusted_seal()!=seal:
        result['judge'].update(judge_state='grader_error',failure='trusted_assets_changed');result['failure']='grader_error';return result
    agent=None;adapter=None;reply='';trace=CodingTrace();started=time.monotonic()
    attempt = Attempt(execution_identity)
    trace.attempt = attempt
    cancelled = None
    root=create_repository(parent/'agent',case.public)
    before=snapshot(root);baseline=await GitBaseline.capture(root)
    config=configuration(base,root,limits)
    if _adapter_factory is not None:
        config=replace(config,coding_autonomy={**config.coding_autonomy,
            'max_model_requests':min(config.coding_autonomy['max_model_requests'],budget.state['maximum']-budget.state['used'])})
    # Keep only approval output on the actual caller channel; raw Agent output
    # remains captured below in both modes. The approval function checks its TTY.
    provider=AttemptApproval(attempt, output=sys.stdout, challenge=execution_identity is not None) if live else (command_provider or synthetic_approval)
    chosen_provider = provider
    async def tracked_approval(request):
        attempt.check()
        try:decision = await chosen_provider(request)
        except asyncio.CancelledError:
            attempt.approval_cancelled = True
            raise
        attempt.check()
        attempt.command_approved = decision is ApprovalDecision.APPROVE
        return decision
    tools=build_default_tool_registry(root,coding_enabled=True,patch_mode='write',command=config.coding_command,command_approval_provider=tracked_approval)
    # Public fields only cross the client boundary. No Case/private evaluator object.
    client=None if _adapter_factory is not None else (raw if live else (offline_client_factory(case.runtime) if offline_client_factory else OfflineClient()))
    trace.paths=set(before)
    result['attempted']=True
    try:
        traced = CodingClient(client,trace,budget) if _adapter_factory is None else _adapter_factory(case.runtime,config,trace,budget,attempt)
        adapter = traced if _adapter_factory is not None else None
        agent=BenchmarkAgent(traced,config,tools,ContextBuilder(root),trace=trace)
        if adapter is not None:adapter.controller = lambda: agent.coding_controller
        with contextlib.redirect_stdout(io.StringIO()):
            reply=await attempt.run(agent.handle_message(case.runtime.prompt + '\nTrusted public test argv (workspace root): '
                + json.dumps(list(case.runtime.public_test)) + '. Model must invoke run_command and obtain approval.'),
                timeout=min(limits.task_timeout,max(.001,budget.deadline-time.monotonic())))
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit) as exc:
        cancelled = exc
        result['runtime_error'] = 'task_cancelled'
    except CodingEvaluationStop as exc:result['runtime_error']=exc.category
    except TimeoutError:result['runtime_error']='task_timeout'
    except Exception:result['runtime_error']='agent_error'
    if adapter is not None:
        closing = asyncio.create_task(adapter.close())
        await attempt.settle(closing)
        if not attempt.cleanup_confirmed or closing.cancelled() or (closing.done() and closing.exception() is not None):
            attempt.tool_uncertain = True
            attempt.revoke('provider_cleanup_failed')
            result['runtime_error'] = 'provider_cleanup_failed'
        if attempt.reason == 'task_cancelled' and cancelled is None:
            cancelled = asyncio.CancelledError()
            result['runtime_error'] = 'task_cancelled'
    # End of all agent execution. Nothing from private validation/Judge is fed back.
    controller=dict(agent.last_coding_report or {}) if agent else {}
    if attempt.reason is not None:
        controller.update(state='execution_uncertain' if not attempt.cleanup_confirmed or attempt.tool_uncertain else 'cancelled',
            stop_reason=attempt.reason, verification='invalid')
    attempt.revoke('completed' if result['runtime_error'] is None else result['runtime_error'])
    result['agent_state']=controller.get('state','blocked')
    result['controller']={k:v for k,v in controller.items() if k not in ('last_test_command','changed_files')}
    result['controller']['changed_files']=report_paths(controller.get('changed_files',[]),case.public)
    result['metrics']=case_metrics(trace,controller,agent.session.history() if agent else [],live)
    if adapter is not None:
        result['provider_execution'] = adapter.summary()
        result['metrics'].update(adapter.metric_fields())
    result['agent_workflow_success']=(result['agent_state']=='verified' and
        not result['metrics']['protocol_false_verified_count'] and result['metrics']['tool_call_ids_paired'])
    result['premature_completion_count']=sum(e['event']=='llm_response' and not e.get('tool_calls') for e in trace.events) if controller.get('continuation_used') else int(controller.get('stop_reason')=='missing_current_revision_test_evidence')
    records = getattr(trace, 'journal_records', {})
    owned=set(agent._git_capsule.entries) if agent and agent._git_capsule else set(records)
    result['journal_evidence'] = dict(records=copy.deepcopy(records), uncertain=getattr(trace, 'journal_uncertain', False))
    result['lifecycle'] = attempt.metadata()
    if agent and agent._git_capsule:agent._git_capsule.close();agent._git_capsule=None
    result['final_output']={'chars':len(reply),'sha256':hashlib.sha256(reply.encode()).hexdigest()}
    # Metadata only; never retain message lists, raw arguments, stdout or SDK errors.
    result['trace']=trace.events
    result['estimated_cost']=estimated_cost({'prompt_tokens':result['metrics']['input_tokens'],
        'completion_tokens':result['metrics']['output_tokens'],'cached_input_tokens':result['metrics']['cached_input_tokens']},budget.prices) if live else None
    try:
        if not attempt.cleanup_confirmed:raise ValueError('cleanup_unconfirmed')
        candidate=snapshot(root)
        # Captured ownership is valid only for the exact final bytes, never a guess
        # from trace flags or merely the set of files that changed.
        if not (agent and agent._git_capsule):
            owned = {p for p in owned if p in records and p in candidate and
                hashlib.sha256(candidate[p].data).hexdigest() == records[p]['final_sha256'] and
                records[p]['original_sha256'] == (hashlib.sha256(before[p].data).hexdigest() if p in before else None)}
        if result['journal_evidence']['uncertain']:
            result['lifecycle']['execution_uncertain'] = True
            result['lifecycle']['workspace_retained'] = True
            result['agent_state'] = 'execution_uncertain'
            result['agent_workflow_success'] = False
            result['metrics']['execution_uncertain_count'] = 1
    except (OSError,ValueError):
        result['judge']={'judge_state':'grader_error','failure':'unsafe_candidate_snapshot','verified_repair_success':False,'unrelated_file_changes':1}
    else:
        try:
            if cancelled is not None:raise CodingEvaluationStop('task_cancelled')
            remaining=budget.deadline-time.monotonic()
            if remaining<=0:raise CodingEvaluationStop('total_timeout')
            result['judge']=await asyncio.wait_for(judge(case,candidate,validation,benchmark=benchmark,seal=seal,
                index_unchanged=baseline.unchanged(),journal_paths=owned,agent_state=result['agent_state'],
                timeout=min(limits.judge_timeout,remaining)),timeout=remaining)
            if snapshot(root)!=candidate or not baseline.unchanged():
                result['judge'].update(verified_repair_success=False,failure='candidate_changed_during_grading',
                    index_changed=not baseline.unchanged(),stale_final_version=True)
        except asyncio.CancelledError as exc:
            cancelled = exc
            result.update(agent_state='cancelled', agent_workflow_success=False, runtime_error='task_cancelled')
            result['judge']={'judge_state':'unscored','failure':'judge_cancelled','verified_repair_success':False}
        except (TimeoutError,CodingEvaluationStop):
            result['judge']={'judge_state':'grader_error','failure':'grader_timeout','verified_repair_success':False}
        except Exception:
            result['judge']={'judge_state':'grader_error','failure':'grader_error','verified_repair_success':False}
    if result['metrics']['protocol_false_verified_count'] or not result['metrics']['tool_call_ids_paired']:
        result['judge'].update(verified_repair_success=False,failure='protocol_verification_error')
    result['duration_seconds']=round(time.monotonic()-started,6)
    result['failure']=failure_reason(result)
    result['failure_classification'] = failure_classification(result)
    # Drop transient source/transcript/controller references before the next task.
    if agent and attempt.cleanup_confirmed:agent.session.clear()
    result = copy.deepcopy(result)
    if terminal_sink is not None:terminal_sink(result)
    if cancelled is not None:
        cancelled.evaluation_evidence = result
        raise cancelled
    return result


async def evaluate(*,live=False,confirm_api_cost=False,limits=None,case_ids=None,prices=None,max_estimated_cost=None,
                   base_config=None,offline_client_factory=None,command_provider=None,benchmark=None,execution_identity=None,terminal_sink=None,
                   _adapter_factory=None):
    if type(live) is not bool or type(confirm_api_cost) is not bool or live!=confirm_api_cost:
        raise ValueError('live_requires_both_flags')
    if live and (offline_client_factory is not None or command_provider is not None):
        raise ValueError('live_forbids_synthetic_overrides')
    limits=limits or Limits();budget=RequestBudget(limits,prices,max_estimated_cost)
    benchmark=benchmark or load_benchmark();cases=selected_cases(benchmark,case_ids,limits.max_cases,limits.seed)
    seal=trusted_seal();started=time.monotonic();raw=None;results=[]
    neutral=dict(mcp_enabled=False,mcp_servers={},mcp_discovery={'enabled':False},skills_enabled=False,session_persist=False,debug=False)
    base=base_config or GatewayConfig(**neutral,**({} if live else dict(provider='offline',model='offline-script',api_key=None,base_url=None)))
    with WorkspaceDirectory() as workspace:
        parent=workspace.path
        try:
            validations=await asyncio.wait_for(validate_benchmark(benchmark,timeout=limits.judge_timeout),
                timeout=max(.001,budget.deadline-time.monotonic()))
        except TimeoutError:
            validations=[{'case_id':c.runtime.id,'status':'grader_error','category':'validation_timeout','public_tests':c.public_count,'hidden_tests':c.hidden_count} for c in benchmark.cases]
        if live and any(by_value['status']=='valid' for by_value in validations if by_value['case_id'] in {c.runtime.id for c in cases}):
            # An empty synthetic probe root, never base.workspace (which could be a user project).
            probe=parent/'probe';probe.mkdir()
            raw=await live_client(configuration(base,probe,limits),limits,live=live,confirm_api_cost=confirm_api_cost,
                cases=len(cases),prices=budget.prices,**({'gate_only':True} if _adapter_factory is not None else {}))
        by_id={v['case_id']:v for v in validations}
        try:
            stopped = False
            for repeat in range(1,limits.repeats+1):
                for index,case in enumerate(cases):
                    task = parent / f'task-{repeat}-{index}'
                    task.mkdir()
                    def receipt(value):
                        workspace.retain |= value.get('lifecycle', {}).get('workspace_retained', False)
                        if terminal_sink is not None:terminal_sink(value)
                    result = await run_task(case,by_id[case.runtime.id],benchmark,seal,task,repeat=repeat,
                        limits=limits,budget=budget,base=base,raw=raw,live=live,
                        offline_client_factory=offline_client_factory,command_provider=command_provider,
                        execution_identity=execution_identity,terminal_sink=receipt,_adapter_factory=_adapter_factory)
                    results.append(result)
                    # A terminal interruption is a cohort boundary, not a case failure
                    # that licenses another model request or a later slot.
                    if result.get('runtime_error') or result.get('agent_state') in ('cancelled','execution_uncertain') or result.get('lifecycle',{}).get('execution_uncertain') or result.get('controller',{}).get('stop_reason') in ('max_task_seconds','task_timeout','task_interrupted'):
                        stopped = True
                        break
                if stopped:break
        finally:
            if raw is not None:
                closing = Attempt()
                task = asyncio.create_task(raw.close())
                await closing.settle(task)
                if not closing.cleanup_confirmed:
                    workspace.retain = True
                    for value in results:
                        value.update(agent_state='execution_uncertain',agent_workflow_success=False)
                        value['lifecycle'].update(execution_uncertain=True,workspace_retained=True,provider_cleanup_confirmed=False)
                        value['metrics']['execution_uncertain_count']=1
                if closing.reason is not None:raise asyncio.CancelledError
                if task.cancelled() or (task.done() and task.exception() is not None):
                    raise CodingEvaluationStop('provider_cleanup_failed')

    metrics=summarize(results,live=live,budget=budget)
    provenance=GitStatusTool(PROJECT_DIR)
    head=await provenance.git(['rev-parse','--verify','HEAD'],PROJECT_DIR,stdout_limit=256)
    status=await provenance.git(['status','--porcelain'],PROJECT_DIR,stdout_limit=8192)
    commit=head.stdout.decode().strip() if head.code==0 and not head.truncated else None
    dirty=bool(status.stdout) if status.code==0 and not status.truncated else None
    return {'report_type':'coding_benchmark','version':1,'benchmark_version':1,'grading_version':1,'benchmark_sha256':benchmark.sha256,
        'mybot_commit':commit,'worktree_dirty':dirty,'prices':budget.prices,'max_estimated_cost':budget.max_cost,
        'dependency_lock_sha256':hashlib.sha256((PROJECT_DIR/'uv.lock').read_bytes()).hexdigest(),
        'grading_code_sha256':hashlib.sha256(json.dumps(seal).encode()).hexdigest(),
        'platform':{'system':__import__('platform').system(),'release':__import__('platform').release(),
            'machine':__import__('platform').machine(),'python':__import__('platform').python_version()},'mode':'live' if live else 'offline','execution_mode':'macos_readonly',
        'ability_score':bool(live and budget.successes and metrics['eligible_cases']),
        'model_name':labels(base)['model'] if live else 'offline-script','provider_label':labels(base)['provider'] if live else 'offline',
        'created_at':datetime.now(timezone.utc).isoformat(),'limits':asdict(limits),'repeats':limits.repeats,'seed':limits.seed,
        'case_ids':[c.runtime.id for c in cases],'benchmark_case_count':len(benchmark.cases),'validations':validations,
        'results':results,**metrics,'duration_seconds':round(time.monotonic()-started,6),
        'cost_semantics':'Explicit prices and returned Usage only; a final response may exceed the estimated limit; not a billing hard cap.',
        'privacy':'Bounded metadata only; no raw prompts, arguments, test output, source, credentials or private host paths.',
        'limitation':'Synthetic benchmark; offline scripts are not real model coding ability. Same-process Python unittest cannot prove immunity to arbitrary interpreter tampering.'}


def save_report(report, directory=None):
    return _save_report(report,directory if directory is not None else PROJECT_DIR/'runs/coding_benchmark')
