"""Shared experiment orchestration; frozen arms execute their original Harness.

No automatic approval, tool replay, response rewriting or scoring changes.
"""
import argparse
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
BASELINE = '871510f8a682990da63448ef27ec282c376a8711'
CANDIDATE = '04b6968fdab288d8562447e25c84a6d5cec3df41'
BENCHMARK = ROOT / 'evals/tool_verification_ab_v1'
RUNS = ROOT / 'runs/tool_verification_ab'
CASES = ('bucket-boundaries-v1', 'quoted-cells-v1', 'reservation-flow-v1', 'span-coverage-v1')
LIMITS = dict(max_cases=1, repeats=1, max_requests=16, max_model_requests_per_case=16,
              max_output_tokens=2048, request_timeout=90, task_timeout=480,
              total_timeout=600, judge_timeout=10, seed=24)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()


def sha(value): return hashlib.sha256(encoded(value)).hexdigest()
def file_sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())


def write_new(path, value):
    path = Path(path)
    with path.open('xb') as stream:
        stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.DEVNULL, text=True).strip()


def tree_hash(root, folders=('mybot', 'scripts')):
    return sha({str(p.relative_to(root)):file_sha(p) for folder in folders
                for p in sorted((Path(root) / folder).rglob('*.py')) if not p.name.startswith('._')})


def assets_hash(root):
    return sha({str(p.relative_to(root)):file_sha(p) for p in sorted(Path(root).rglob('*')) if p.is_file()})


def plan():
    rows=[]
    for i, case in enumerate(CASES):
        for arm in (('baseline','candidate') if i%2==0 else ('candidate','baseline')):
            rows.append(dict(slot=f'{len(rows)+1:02d}-{arm}-{case}',arm=arm,case_id=case,
                source_commit=BASELINE if arm=='baseline' else CANDIDATE))
    return rows


def freeze(arm_roots, config_source):
    config=read(config_source); llm=config['llm']; providers=llm['providers']
    if llm['provider']!='coco': raise ValueError('primary_provider_mismatch')
    profiles=[]
    for provider in ('coco','coco2'):
        row=providers[provider]
        if not all(isinstance(row.get(k),str) and row[k] for k in ('model','api_key','base_url')):
            raise ValueError('missing_provider_configuration')
        # Reuse the existing safe label policy without serializing private configuration.
        from mybot.evaluation.artifacts import redact
        if redact(row['model'],tuple(p['api_key'] for p in providers.values() if isinstance(p,dict) and p.get('api_key')))!=row['model']:
            raise ValueError('unsafe_model_label')
        profiles.append(dict(provider=provider,model=row['model'],endpoint_sha256=hashlib.sha256(row['base_url'].encode()).hexdigest()))
    arms={}
    for arm,commit in [('baseline',BASELINE),('candidate',CANDIDATE)]:
        root=Path(arm_roots[arm]).resolve()
        if git(root,'rev-parse','HEAD')!=commit or git(root,'status','--porcelain'):raise ValueError('arm_not_clean_and_pinned')
        arms[arm]=dict(commit=commit,source_tree_sha256=tree_hash(root),lock_sha256=file_sha(root/'uv.lock'),
            grading_sha256=file_sha(root/'mybot/evaluation/coding_judge.py'))
    if arms['baseline']['grading_sha256']!=arms['candidate']['grading_sha256'] or arms['baseline']['lock_sha256']!=arms['candidate']['lock_sha256']:
        raise ValueError('unmatched_grading_or_dependencies')
    if git(ROOT,'status','--porcelain'):raise ValueError('orchestrator_requires_clean_commit')
    return dict(version=1,kind='tool_verification_live_ab',orchestrator_commit=git(ROOT,'rev-parse','HEAD'),
        orchestrator_source_sha256=tree_hash(ROOT),benchmark_assets_sha256=assets_hash(BENCHMARK),
        arms=arms,providers=profiles,private_config_sha256=file_sha(config_source),limits=LIMITS,
        max_physical_requests=128,max_http_requests=128,max_attempts=8,
        temperature=0.1,retries=0,fault_mode='none',provider_mode='failover',
        provider_policy='network-timeout-429-500-502-503-504-v1',
        cost_limit=None,cost_unknown_accepted=True,slots=plan(),
        authorization='User selected 128 total physical requests; accepts unknown costs; fresh 4 tasks x 2 arms.',
        model_version_limitation='Configured aliases pinned; immutable backend version/system fingerprint unavailable.',
        no_replay=True,no_result_tuning=True,strict_scoring='original coding_campaign.strict_success')


def campaign_path(value):
    path=Path(value).resolve()
    if path==RUNS.resolve() or not path.is_relative_to(RUNS.resolve()):raise ValueError('independent_namespace_required')
    return path


def prepare(directory, arm_roots, config_source):
    root=campaign_path(directory)
    if root.exists():raise ValueError('campaign_exists_no_resume')
    frozen=freeze(arm_roots,config_source)
    root.mkdir(parents=True)
    manifest=dict(campaign_id=uuid.uuid4().hex,frozen=frozen,frozen_sha256=sha(frozen),
        attempts={r['slot']:uuid.uuid4().hex for r in frozen['slots']})
    write_new(root/'manifest.json',manifest)
    (root/'requests').mkdir();(root/'attempts').mkdir()
    # Copy only to newly created ignored config paths, with no overwrite or logging.
    for arm in ('baseline','candidate'):
        target=Path(arm_roots[arm])/'config/config.json'
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(Path(config_source).read_bytes());stream.flush();os.fsync(stream.fileno())
    return dict(campaign_id=manifest['campaign_id'],slots=len(frozen['slots']),max_physical_requests=128)


def validate_ledger(root, manifest):
    rows=[];directory=Path(root)/'requests';frozen=manifest['frozen']
    for index,path in enumerate(sorted(directory.glob('*-started.json')),1):
        start=read(path)
        if path.name!=f'{index:04d}-started.json' or start['sequence']!=index or start['frozen_sha256']!=manifest['frozen_sha256']:
            raise ValueError('request_ledger_corrupt')
        slot=next((r for r in frozen['slots'] if r['slot']==start['slot']),None)
        if slot is None or start['attempt_id']!=manifest['attempts'][start['slot']]:raise ValueError('request_identity_mismatch')
        end=directory/f'{index:04d}-finished.json'
        if not end.exists():raise ValueError('incomplete_request_requires_audit')
        outcome=read(end)
        if outcome['reservation_sha256']!=file_sha(path):raise ValueError('request_outcome_corrupt')
        if any(outcome['record'].get(k)!=start['record'].get(k) for k in ('attempt_id','case_id','physical_request','provider','model')):
            raise ValueError('request_outcome_identity')
        rows.append(outcome)
    if len(rows)>128 or any(sum(r['slot']==s['slot'] for r in rows)>16 for s in frozen['slots']):raise ValueError('physical_budget_overrun')
    if any(r['record'].get('http_dispatch_count') not in (0,1) for r in rows):raise ValueError('http_observation_invalid')
    return rows


class RequestAudit:
    def __init__(self, root, manifest, slot, guard):
        self.root=Path(root);self.manifest=manifest;self.slot=slot;self.guard=guard;self.pending=None

    def before(self, record):
        if self.pending is not None:raise ValueError('concurrent_physical_dispatch')
        self.guard()
        if read(self.root/'manifest.json')!=self.manifest:raise ValueError('manifest_changed')
        if (self.root/'stopped.json').exists():raise ValueError('campaign_stopped')
        rows=validate_ledger(self.root,self.manifest)
        own=sum(r['slot']==self.slot for r in rows)
        if len(rows)>=128 or own>=16:raise ValueError('physical_request_budget')
        expected_case=next(row['case_id'] for row in self.manifest['frozen']['slots'] if row['slot']==self.slot)
        if record.get('case_id')!=expected_case:raise ValueError('case_identity_invalid')
        if record['attempt_id']!=self.manifest['attempts'][self.slot] or record['physical_request']!=own+1:
            raise ValueError('physical_identity_invalid')
        providers={p['provider']:p['model'] for p in self.manifest['frozen']['providers']}
        if record['model']!=providers.get(record['provider']):raise ValueError('provider_identity_invalid')
        n=len(rows)+1
        start=dict(sequence=n,slot=self.slot,attempt_id=record['attempt_id'],frozen_sha256=self.manifest['frozen_sha256'],record=copy.deepcopy(record))
        path=self.root/'requests'/f'{n:04d}-started.json';write_new(path,start)
        self.pending=(n,path)

    def after(self, record):
        if self.pending is None:raise ValueError('missing_physical_reservation')
        n,path=self.pending
        write_new(self.root/'requests'/f'{n:04d}-finished.json',dict(sequence=n,slot=self.slot,
            reservation_sha256=file_sha(path),record=copy.deepcopy(record)))
        self.pending=None


def check_slot(root, manifest, slot):
    frozen=manifest['frozen']
    if sha(frozen)!=manifest['frozen_sha256']:raise ValueError('manifest_corrupt')
    slots=frozen['slots'];row=next((x for x in slots if x['slot']==slot),None)
    if row is None:raise ValueError('invalid_slot')
    if (root/'stopped.json').exists():raise ValueError('campaign_stopped')
    if (root/'attempts'/slot).exists():raise ValueError('attempt_started_no_replay')
    for prior in slots[:slots.index(row)]:
        folder=root/'attempts'/prior['slot']
        if not (folder/'finished.json').exists():raise ValueError('prior_attempt_incomplete')
        finished=read(folder/'finished.json')
        if finished['raw_sha256']!=file_sha(folder/'raw.json') or finished['terminal_sha256']!=file_sha(folder/'terminal.json'):
            raise ValueError('prior_evidence_changed')
    validate_ledger(root,manifest)
    return row


async def run_slot(directory, slot, arm_root):
    root=campaign_path(directory);manifest=read(root/'manifest.json');row=check_slot(root,manifest,slot)
    arm_root=Path(arm_root).resolve();frozen=manifest['frozen']
    def guard():
        if git(ROOT,'rev-parse','HEAD')!=frozen['orchestrator_commit'] or git(ROOT,'status','--porcelain'):
            raise ValueError('orchestrator_changed')
        if tree_hash(ROOT)!=frozen['orchestrator_source_sha256'] or assets_hash(BENCHMARK)!=frozen['benchmark_assets_sha256']:
            raise ValueError('shared_assets_changed')
        if git(arm_root,'rev-parse','HEAD')!=row['source_commit'] or git(arm_root,'status','--porcelain'):
            raise ValueError('arm_source_changed')
        if tree_hash(arm_root)!=frozen['arms'][row['arm']]['source_tree_sha256'] or file_sha(arm_root/'config/config.json')!=frozen['private_config_sha256']:
            raise ValueError('arm_source_or_config_changed')
    guard()
    # One fresh interpreter per arm. Do not monkeypatch either frozen Harness.
    sys.path.insert(0,str(arm_root))
    from mybot.evaluation.coding_fixtures import load_benchmark
    from mybot.evaluation.coding_live import Limits
    from mybot.evaluation.coding_failover import evaluate
    from mybot.evaluation.coding_campaign import strict_success,pause_reason
    from mybot.config import PROJECT_DIR
    if PROJECT_DIR!=arm_root:raise ValueError('wrong_import_root')
    folder=root/'attempts'/slot;folder.mkdir()
    identity=dict(campaign_id=manifest['campaign_id'],run_id=slot,attempt_id=manifest['attempts'][slot],config_sha256=manifest['frozen_sha256'])
    write_new(folder/'started.json',dict(**identity,arm=row['arm'],source_commit=row['source_commit']))
    def terminal(value):write_new(folder/'terminal.json',dict(**identity,evidence=value))
    audit=RequestAudit(root,manifest,slot,guard)
    try:
        report=await evaluate(provider_mode='failover',live=True,confirm_api_cost=True,
            benchmark=load_benchmark(BENCHMARK),limits=Limits(**LIMITS),case_ids=[row['case_id']],
            execution_identity=identity,terminal_sink=terminal,request_audit=audit,fault_mode='none')
        guard();write_new(folder/'raw.json',report)
        if not (folder/'terminal.json').exists():raise ValueError('terminal_missing')
        ledger=validate_ledger(root,manifest)
        own=[r for r in ledger if r['slot']==slot]
        if len(own)!=report['physical_model_requests'] or sum(r['record']['http_dispatch_count'] for r in own)!=report['http_model_requests']:
            raise ValueError('physical_or_http_audit_mismatch')
        if read(folder/'terminal.json')['evidence']!=report['results'][0]:raise ValueError('terminal_raw_mismatch')
        if report.get('mybot_commit')!=row['source_commit'] or report.get('worktree_dirty') is not False:
            raise ValueError('source_provenance_mismatch')
        if any(report['results'][0].get('lifecycle',{}).get(k)!=v for k,v in identity.items()):
            raise ValueError('lifecycle_identity_mismatch')
        pause=pause_reason(report)
        r=report['results'][0];m=r.get('metrics',{});j=r.get('judge',{})
        if any(m.get(k) for k in ('sandbox_failures','execution_uncertain_count','protocol_false_verified_count','approval_denials','workspace_escape_attempts')) or m.get('tool_call_ids_paired') is not True or any(j.get(k) for k in ('protected_file_changes','unrelated_file_changes','journal_attribution_mismatch','index_changed')):
            pause=pause or 'security_boundary_requires_audit'
        if j.get('judge_state') in ('grader_error','invalid_case','unscored'):pause=pause or 'judge_infrastructure_requires_audit'
        write_new(folder/'finished.json',dict(**identity,strict_success=strict_success(report),
            raw_sha256=file_sha(folder/'raw.json'),terminal_sha256=file_sha(folder/'terminal.json'),pause_reason=pause))
        if pause:write_new(root/'stopped.json',dict(slot=slot,reason=pause))
        return dict(slot=slot,state=r['agent_state'],judge=j['judge_state'],strict_success=strict_success(report),
            physical_requests=report['physical_model_requests'],http_requests=report['http_model_requests'],pause_reason=pause)
    except BaseException:
        if not (root/'stopped.json').exists():write_new(root/'stopped.json',dict(slot=slot,reason='attempt_incomplete_requires_audit'))
        raise


def summarize(directory):
    root=campaign_path(directory);manifest=read(root/'manifest.json')
    ledger=validate_ledger(root,manifest)
    from mybot.evaluation.coding_metrics import failure_classification
    from mybot.evaluation.coding_campaign import strict_success
    results=[]
    for row in manifest['frozen']['slots']:
        folder=root/'attempts'/row['slot']
        result={**row,'attempt_id':manifest['attempts'][row['slot']], 'attempted':folder.exists(),
                'status':'not_started','strict_success':False,'agent_state':None,'judge_state':None}
        if (folder/'finished.json').exists():
            end=read(folder/'finished.json')
            if end['raw_sha256']!=file_sha(folder/'raw.json') or end['terminal_sha256']!=file_sha(folder/'terminal.json'):
                raise ValueError('evidence_hash_mismatch')
            raw=read(folder/'raw.json');r=raw['results'][0];m=r['metrics'];c=r['controller']
            if end['strict_success']!=strict_success(raw):raise ValueError('strict_score_mismatch')
            result.update(status='completed',strict_success=end['strict_success'],agent_state=r['agent_state'],
                judge_state=r['judge']['judge_state'],original_failure=r.get('failure'),failure_classification=failure_classification(r),
                logical_requests=raw['logical_model_requests'],physical_requests=raw['physical_model_requests'],http_requests=raw['http_model_requests'],
                provider_counts=raw['physical_requests_by_provider'],fallback_attempts=raw['fallback_attempts'],
                tool_calls=m['tool_calls'],patch_write_attempts=m['patch_write_attempts'],committed_patches=m['committed_patches'],
                invalid_patch_arguments=sum(e.get('event')=='tool' and e.get('name')=='apply_patch' and e.get('error')=='invalid_arguments' for e in r['trace']),
                stale_previews=sum(e.get('stale_patch') is True and e.get('patch_preview') is True for e in r['trace']),
                test_runs=c.get('test_runs'),test_passes=c.get('test_passes'),stop_reason=c.get('stop_reason'),
                current_revision=c.get('current_revision'),verified_revision=c.get('last_verified_revision'),
                command_tool_calls=sum(e.get('event')=='tool' and e.get('name')=='run_command' for e in r['trace']),
                cleanup_confirmed=r.get('lifecycle',{}).get('cleanup_confirmed'),tool_ids_paired=m.get('tool_call_ids_paired'),
                journal_uncertain=r.get('journal_evidence',{}).get('uncertain'),raw_sha256=file_sha(folder/'raw.json'),
                terminal_sha256=file_sha(folder/'terminal.json'),duration_seconds=raw.get('duration_seconds'))
        elif folder.exists():result['status']='incomplete_requires_audit'
        results.append(result)
    arms={}
    for arm in ('baseline','candidate'):
        own=[r for r in results if r['arm']==arm];complete=[r for r in own if r['status']=='completed']
        arms[arm]=dict(planned=4,attempted=sum(r['attempted'] for r in own),completed=len(complete),
            strict_success=sum(r['strict_success'] for r in complete),controller_verified=sum(r['agent_state']=='verified' for r in complete),
            hidden_pass=sum(r['judge_state']=='hidden_pass' for r in complete),
            **{k:sum(r[k] for r in complete) for k in ('logical_requests','physical_requests','http_requests','tool_calls','invalid_patch_arguments','stale_previews','committed_patches')})
    usage=[r['record'].get('usage',{}) for r in ledger]
    tokens={k:sum(x[k] for x in usage if type(x.get(k)) is int) for k in ('prompt_tokens','completion_tokens','total_tokens')}
    unknown=sum(any(type(x.get(k)) is not int for k in ('prompt_tokens','completion_tokens','total_tokens')) for x in usage)
    return dict(kind='real_live_paired_ab',status='completed' if all(r['status']=='completed' for r in results) else 'stopped_or_incomplete',
        frozen=manifest['frozen'],campaign_id=manifest['campaign_id'],results=results,arms=arms,
        physical_requests=len(ledger),http_requests=sum(r['record']['http_dispatch_count'] for r in ledger),
        observable_tokens=tokens,requests_with_incomplete_usage=unknown,estimated_cost=None,
        stop=read(root/'stopped.json') if (root/'stopped.json').exists() else None,
        limitations=['Four task pairs; no estimate of population model improvement.','Provider model aliases do not prove immutable backend version.','Unknown costs; observed HTTP dispatch is not billing confirmation.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--directory',required=True);prep.add_argument('--baseline-root',required=True);prep.add_argument('--candidate-root',required=True);prep.add_argument('--config-source',required=True)
    summary=sub.add_parser('summarize');summary.add_argument('--directory',required=True)
    run=sub.add_parser('run-slot');run.add_argument('--directory',required=True);run.add_argument('--slot',required=True);run.add_argument('--arm-root',required=True);run.add_argument('--live',action='store_true');run.add_argument('--confirm-api-cost',action='store_true')
    args=p.parse_args()
    try:
        if args.action=='prepare':result=prepare(args.directory,dict(baseline=args.baseline_root,candidate=args.candidate_root),args.config_source)
        elif args.action=='summarize':result=summarize(args.directory)
        else:
            if not args.live or not args.confirm_api_cost:raise ValueError('explicit_live_flags_required')
            result=asyncio.run(run_slot(args.directory,args.slot,args.arm_root))
        print(json.dumps(result,ensure_ascii=True));return 0
    except (Exception,KeyboardInterrupt):
        print('A/B stopped or rejected; preserve evidence, no replay.');return 1


if __name__=='__main__':raise SystemExit(main())
