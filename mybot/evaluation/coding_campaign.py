"""Durable orchestration around Phase24; never grants approval or changes grading.

A started slot is never automatically replayed. SHA inventories detect corruption,
not an adversary who can rewrite both evidence and inventory.
"""
import asyncio
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import uuid

from ..config import GatewayConfig, PROJECT_DIR
from ..tools import build_default_tool_registry
from .coding_benchmark import configuration, evaluate
from .coding_fixtures import load_benchmark
from .coding_judge import trusted_seal
from .coding_live import Limits

PRIORITY = ('pagination-001', 'serialization-001', 'file-recovery-001')
LIMITS = Limits(max_cases=1, repeats=1, max_requests=12,
    max_model_requests_per_case=12, max_output_tokens=2048,
    request_timeout=90, task_timeout=600, total_timeout=900)


def now(): return datetime.now(timezone.utc).isoformat()
def encoded(value): return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()
def sha(value): return hashlib.sha256(encoded(value)).hexdigest()
def file_sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(['git', *args], cwd=PROJECT_DIR, text=True).strip()


def write_new(path, value):
    data = encoded(value)
    with Path(path).open('xb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def read(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 8*1024*1024:
        raise ValueError('unsafe_evidence')
    return json.loads(p.read_bytes())


def freeze(base=None):
    """Explicit allowlist: no key, URL, host workspace or raw config enters artifacts."""
    base = base or GatewayConfig()
    config = configuration(base, Path('/isolated-workspace'), LIMITS)
    if base.provider != 'coco2' or base.model != 'gpt-6-astra':
        raise ValueError('model_configuration_mismatch')
    fields = ('coding_enabled','coding_patch_mode','coding_command','coding_autonomy',
        'coding_git_workflow','context_enabled','context_max_chars','context_recent_turns',
        'context_summary_max_chars','context_tool_result_max_chars','session_max_turns',
        'session_persist','skills_enabled','mcp_enabled','debug','max_react_steps',
        'max_completion_tokens','request_timeout_seconds')
    tools = build_default_tool_registry(config.workspace, coding_enabled=True,
        patch_mode='write', command=config.coding_command)
    return dict(benchmark_harness_commit=git('rev-parse','HEAD'),
        benchmark_sha256=load_benchmark().sha256,
        grading_code_sha256=hashlib.sha256(json.dumps(trusted_seal()).encode()).hexdigest(), dependency_lock_sha256=file_sha(PROJECT_DIR/'uv.lock'),
        provider=base.provider, model=base.model, python=platform.python_version(),
        system=platform.system(), machine=platform.machine(), limits=asdict(LIMITS),
        agent={k:getattr(config,k) for k in fields}, tool_schemas=tools.get_definitions(),
        approval='native_real_tty_each_invocation_no_cached_authorization',
        execution_mode='macos_readonly', private_config_sha256=file_sha(PROJECT_DIR/'config/config.json')
            if (PROJECT_DIR/'config/config.json').exists() else None)


def create(directory, *, rounds=3, case_ids=None, live=False):
    if type(rounds) is not int or not 1 <= rounds <= 3: raise ValueError('invalid_rounds')
    benchmark=load_benchmark(); ids=[c.runtime.id for c in benchmark.cases]
    chosen=ids if case_ids is None else list(case_ids)
    if not chosen or len(set(chosen)) != len(chosen) or any(c not in ids for c in chosen):
        raise ValueError('invalid_cases')
    order=[c for c in PRIORITY if c in chosen]+[c for c in chosen if c not in PRIORITY]
    root=Path(directory)
    if root.exists(): raise ValueError('campaign_exists')
    root.mkdir(parents=True)
    frozen=freeze()
    manifest=dict(version=1, campaign_id=uuid.uuid4().hex, created_at=now(), live=live,
        frozen=frozen, config_sha256=sha(frozen), rounds=rounds,
        slots=[dict(run_id=f'r{r}-{c}', round=r, case_id=c) for r in range(1,rounds+1) for c in order])
    write_new(root/'manifest.json',manifest)
    (root/'runs').mkdir(); (root/'checkpoints').mkdir()
    checkpoint(root,'A','audit_complete',{'base':'ff10fb6','next':'offline development and freeze'})
    return manifest


def checkpoint(root, name, status, details):
    target=Path(root)/'checkpoints'/f'{name}-{uuid.uuid4().hex}.json'
    write_new(target,dict(checkpoint=name,status=status,at=now(),git_commit=git('rev-parse','HEAD'),details=details))


@contextmanager
def lock(root):
    import fcntl
    with (Path(root)/'.lock').open('a') as stream:
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('campaign_busy') from None
        yield


def strict_success(report):
    if report.get('mode')!='live' or len(report.get('results',[]))!=1: return False
    r=report['results'][0]; m=r.get('metrics',{}); c=r.get('controller',{}); j=r.get('judge',{})
    revision=c.get('current_revision')
    safe=all(j.get(k) == 0 for k in ('protected_file_changes','unrelated_file_changes','journal_attribution_mismatch')) and j.get('index_changed') is False
    safe &= all(m.get(k) == 0 for k in ('sandbox_failures','execution_uncertain_count','protocol_false_verified_count','approval_denials','workspace_escape_attempts')) and m.get('tool_call_ids_paired') is True
    evidence=any(e.get('event')=='tool' and e.get('real_test_run') is True and e.get('current_revision_test_evidence') is True for e in r.get('trace',[]))
    return bool(r.get('agent_state')=='verified' and r.get('agent_workflow_success') is True
        and j.get('judge_state')=='hidden_pass' and j.get('verified_repair_success') is True
        and all(j.get(k,{}).get('passed') is True for k in ('public','hidden'))
        and m.get('committed_patches',0)>0 and m.get('real_test_runs',0)>0
        and type(revision) is int and revision>0 and revision==c.get('last_verified_revision') and safe and evidence)


def classify(report):
    if strict_success(report): return ['success']
    r=report['results'][0];c=r.get('controller',{});m=r.get('metrics',{});j=r.get('judge',{});stop=c.get('stop_reason') or r.get('runtime_error')
    mapping={'model_request_timeout':'model_request_timeout','provider_timeout':'model_request_timeout',
        'provider_error':'provider_api_error','provider_unsupported':'provider_api_error',
        'max_model_requests':'request_budget_exhausted','model_request_budget':'request_budget_exhausted',
        'approval_denied':'approval_denied','invalid_cwd':'cwd_or_path_error',
        'timeout_exceeds_configuration':'invalid_tool_arguments',
        'missing_current_revision_test_evidence':'agent_ended_early'}
    labels=[]
    if r.get('runtime_error') in mapping: labels.append(mapping[r['runtime_error']])
    if stop in mapping: labels.append(mapping[stop])
    for e in r.get('trace',[]):
        if e.get('event')!='tool' or e.get('success') is not False: continue
        if e.get('name')=='apply_patch': labels.append('patch_preview_failed' if e.get('patch_preview') else 'patch_commit_failed')
        if e.get('error')=='invalid_arguments': labels.append('invalid_tool_arguments')
        if e.get('error') in ('invalid_cwd','invalid_path','path_outside_workspace','symlink_denied'): labels.append('cwd_or_path_error')
        if e.get('workspace_escape') or e.get('sandbox_failure'): labels.append('safety_block')
    if not m.get('real_test_runs'): labels.append('real_test_not_executed')
    if j.get('public',{}).get('passed') is False: labels.append('public_tests_failed')
    if j.get('hidden',{}).get('passed') is False: labels.append('hidden_tests_failed')
    if j.get('journal_attribution_mismatch') or c.get('verification')=='expired': labels.append('revision_or_journal_mismatch')
    if m.get('execution_uncertain_count') or r.get('agent_state')=='execution_uncertain': labels.append('execution_uncertain')
    return list(dict.fromkeys(labels or ['unknown_failure']))


def validate_report(report, manifest, slot):
    f=manifest['frozen']
    expected={'mybot_commit':f['benchmark_harness_commit'],'benchmark_sha256':f['benchmark_sha256'],
        'dependency_lock_sha256':f['dependency_lock_sha256'],'provider_label':f['provider'],
        'model_name':f['model'],'mode':'live' if manifest['live'] else 'offline','limits':f['limits'],
        'worktree_dirty':False}
    # Phase24 uses standard json spacing for its seal; freeze records the exact same seal below.
    expected['grading_code_sha256']=f['grading_code_sha256']
    if not manifest['live']:expected.update(provider_label='offline',model_name='offline-script')
    if any(report.get(k)!=v for k,v in expected.items()): raise ValueError('report_provenance_mismatch')
    if report.get('case_ids')!=[slot['case_id']] or len(report.get('results',[]))!=1 or report['results'][0].get('case_id')!=slot['case_id']:
        raise ValueError('report_case_mismatch')


def inventory(root):
    root=Path(root); manifest=read(root/'manifest.json');seen=set();result=[]
    if sha(manifest['frozen'])!=manifest['config_sha256']: raise ValueError('configuration_corrupt')
    for slot in manifest['slots']:
        run_id=slot['run_id']
        if run_id in seen or run_id!=f"r{slot['round']}-{slot['case_id']}" or '/' in run_id or '..' in run_id:
            raise ValueError('duplicate_or_invalid_run_id')
        seen.add(run_id); folder=root/'runs'/run_id
        if folder.is_symlink():raise ValueError('unsafe_evidence')
        row={**slot,'status':'pending','strict_success':False,'report':None}
        if folder.exists():
            row['status']='uncertain'
            start=read(folder/'started.json')
            if start['run_id']!=run_id or start['config_sha256']!=manifest['config_sha256']:raise ValueError('run_identity_mismatch')
            if (folder/'finished.json').exists():
                end=read(folder/'finished.json');report=read(folder/'raw.json')
                if end['report_sha256']!=file_sha(folder/'raw.json'):raise ValueError('evidence_hash_mismatch')
                validate_report(report,manifest,slot)
                row.update(status='completed',strict_success=strict_success(report),report=report)
            elif (folder/'blocked.json').exists():row['status']='blocked_uncertain'
        result.append(row)
    return manifest,result


async def run_next(root, *, live=False, confirm_api_cost=False):
    """One independent evaluate invocation. Crash markers are intentionally terminal."""
    root=Path(root)
    with lock(root):
        manifest,rows=inventory(root)
        if live!=manifest['live'] or confirm_api_cost!=live:raise ValueError('cost_mode_mismatch')
        if freeze()!=manifest['frozen'] or git('status','--porcelain'):raise ValueError('frozen_environment_changed')
        if any(r['status'] in ('uncertain','blocked_uncertain') or (r['report'] and r['report']['results'][0].get('agent_state')=='execution_uncertain') for r in rows):raise ValueError('uncertain_run_requires_investigation')
        slot=next((r for r in rows if r['status']=='pending'),None)
        if slot is None:return None
        folder=root/'runs'/slot['run_id'];folder.mkdir()
        write_new(folder/'started.json',dict(run_id=slot['run_id'],at=now(),config_sha256=manifest['config_sha256']))
        print(json.dumps({'run_id':slot['run_id'],'state':'started'}),flush=True)
        try:
            report=await evaluate(live=live,confirm_api_cost=confirm_api_cost,limits=LIMITS,case_ids=[slot['case_id']])
            write_new(folder/'raw.json',report)
            validate_report(report,manifest,slot)
            write_new(folder/'finished.json',dict(run_id=slot['run_id'],at=now(),report_sha256=file_sha(folder/'raw.json')))
        except BaseException:
            write_new(folder/'blocked.json',dict(run_id=slot['run_id'],at=now(),category='interrupted_or_evidence_uncommitted'))
            raise
        uncertain=report['results'][0].get('agent_state')=='execution_uncertain'
        if uncertain:write_new(folder/'blocked.json',dict(run_id=slot['run_id'],at=now(),category='reported_execution_uncertain'))
        _, after=inventory(root)
        round_rows=[r for r in after if r['round']==slot['round']]
        if all(r['status']=='completed' for r in round_rows):
            checkpoint(root,'C' if slot['round']==1 else 'D','round_complete',
                {'round':slot['round'],'completed':len(round_rows),'strict_successes':sum(r['strict_success'] for r in round_rows)})
        print(json.dumps({'run_id':slot['run_id'],'state':'completed','strict_success':strict_success(report)}),flush=True)
        return report


def distribution(values):
    known=sorted(v for v in values if type(v) in (int,float) and math.isfinite(v))
    def percentile(p):
        if not known:return None
        n=(len(known)-1)*p;lo=math.floor(n);hi=math.ceil(n)
        return known[lo]+(known[hi]-known[lo])*(n-lo)
    return dict(known=len(known),missing=len(values)-len(known),total=sum(known) if known else None,
        mean=sum(known)/len(known) if known else None,p50=percentile(.5),p90=percentile(.9),p95=percentile(.95))


def summary(root):
    manifest,rows=inventory(root);done=[r for r in rows if r['status']=='completed'];success=sum(r['strict_success'] for r in done)
    result=dict(campaign_id=manifest['campaign_id'],config_sha256=manifest['config_sha256'],frozen=manifest['frozen'],
        planned=len(rows),completed=len(done),pending=sum(r['status']=='pending' for r in rows),
        uncertain=sum(r['status'] in ('uncertain','blocked_uncertain') for r in rows),strict_successes=success,
        completed_run_success_rate=success/len(done) if done else None,
        planned_run_success_fraction=success/len(rows),coverage=len({r['case_id'] for r in done if r['strict_success']}),
        rounds={},cases={},difficulty={},failures={},resources={},rows=[])
    for key in ('llm_requests','successful_responses','tool_calls','input_tokens','output_tokens','total_tokens',
                'duration_seconds','patch_preview_calls','patch_write_attempts','committed_patches','real_test_runs','command_attempts','approval_denials','sandbox_failures','protocol_false_verified_count'):
        result['resources'][key]=distribution([r['report'].get(key) for r in done])
    result['estimated_cost']=None;result['cost_reason']='no reliable configured prices; unknown usage remains null'
    result['tokens_per_success_known_subtotal']=result['resources']['total_tokens']['total']/success if success and result['resources']['total_tokens']['total'] is not None else None
    for r in rows:
        d=r['report'];case=r['case_id'];group=result['cases'].setdefault(case,dict(planned=0,completed=0,strict_successes=0))
        group['planned']+=1
        if d:group['completed']+=1;group['strict_successes']+=r['strict_success']
        rnd=result['rounds'].setdefault(str(r['round']),dict(planned=0,completed=0,strict_successes=0));rnd['planned']+=1
        if d:rnd['completed']+=1;rnd['strict_successes']+=r['strict_success']
        entry={k:v for k,v in r.items() if k!='report'}
        if d:
            x=d['results'][0];entry.update(agent_state=x['agent_state'],agent_workflow_success=x['agent_workflow_success'],
                judge_state=x['judge']['judge_state'],judge_success=x['judge']['verified_repair_success'],
                failure_categories=classify(d),revision=x['controller'].get('current_revision'),
                last_verified_revision=x['controller'].get('last_verified_revision'),report_sha256=file_sha(Path(root)/'runs'/r['run_id']/'raw.json'))
            entry['evidence_path']=f"runs/{r['run_id']}/raw.json"
            level=result['difficulty'].setdefault(x['difficulty'],dict(completed=0,strict_successes=0));level['completed']+=1;level['strict_successes']+=r['strict_success']
            if not r['strict_success']:
                for reason in entry['failure_categories']:result['failures'][reason]=result['failures'].get(reason,0)+1
        result['rows'].append(entry)
    for rnd in result['rounds'].values():
        rnd['completed_run_success_rate']=rnd['strict_successes']/rnd['completed'] if rnd['completed'] else None
        rnd['round_complete']=rnd['completed']==rnd['planned']
    for name,predicate in [('agent_verified',lambda d:d['results'][0]['agent_state']=='verified'),
        ('agent_workflow_success',lambda d:d['results'][0]['agent_workflow_success']),
        ('judge_hidden_pass',lambda d:d['results'][0]['judge']['judge_state']=='hidden_pass'),
        ('judge_repair_success',lambda d:d['results'][0]['judge']['verified_repair_success'])]:
        count=sum(bool(predicate(r['report'])) for r in done);result[name]=dict(count=count,denominator=len(done),rate=count/len(done) if done else None)
    for case, group in result['cases'].items():
        reports=[r['report'] for r in done if r['case_id']==case]
        group['resources']={k:distribution([d.get(k) for d in reports]) for k in ('llm_requests','successful_responses','tool_calls','total_tokens','duration_seconds')}
        group['revisions']=distribution([d['results'][0]['controller'].get('current_revision') for d in reports])
        group['at_least_one_success']=group['strict_successes']>0
    result['unresolved_execution_uncertain']=sum(r['report']['results'][0].get('agent_state')=='execution_uncertain' for r in done)
    result['patch_commit_rate']=None
    writes=result['resources']['patch_write_attempts']['total'];commits=result['resources']['committed_patches']['total']
    if writes:result['patch_commit_rate']=commits/writes
    result['real_test_runs_per_command_attempt']=None
    commands=result['resources']['command_attempts']['total'];tests=result['resources']['real_test_runs']['total']
    if commands:result['real_test_runs_per_command_attempt']=tests/commands
    result['protocol_paired_run_rate']=sum(r['report'].get('tool_call_ids_paired') is True for r in done)/len(done) if done else None
    result['approval_success_rate']=None
    result['approval_note']='Native approval grant count is not retained by Phase24; report denials, not an invented approval denominator.'
    tools={}
    for r in done:
        for e in r['report']['results'][0].get('trace',[]):
            if e.get('event')=='tool':
                t=tools.setdefault(e['name'],dict(calls=0,successes=0));t['calls']+=1;t['successes']+=e.get('success') is True
    result['tool_reliability']=tools
    return result


def markdown(s):
    lines=['# Phase25 标准 Benchmark', '',f"计划 {s['planned']}；完成 {s['completed']}；未执行 {s['pending']}；不确定 {s['uncertain']}。",
        f"严格成功 {s['strict_successes']}；已完成运行成功率 {s['completed_run_success_rate']}；至少一次成功覆盖 {s['coverage']}。",
        '未完成轮次不能称为全量 pass@1；历史覆盖不是单次成功率。未知费用为 null，不代表免费。', '',
        '| Run ID | 状态 | Agent | Judge | 严格成功 | 失败分类 |','|---|---|---|---|---|---|']
    for r in s['rows']:lines.append('| '+ ' | '.join(str(r.get(k,'')) for k in ('run_id','status','agent_state','judge_state','strict_success','failure_categories'))+' |')
    return '\n'.join(lines)+'\n'
