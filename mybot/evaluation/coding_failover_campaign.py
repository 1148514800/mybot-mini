"""Create-once manifest v4; never resumes/replays a started Attempt or v3 cohort."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import uuid

from ..config import GatewayConfig, PROJECT_DIR
from . import coding_campaign as legacy
from .coding_failover import evaluate, settings, POLICY
from .coding_live import Limits, labels
from .coding_fixtures import load_benchmark


def base_config(live):
    return GatewayConfig(**({} if live else dict(provider='coco',model='deepseek-v4.1-flash',api_key=None,base_url=None)))


def freeze(mode, live, limits, case_id):
    base=base_config(live)
    frozen=legacy.freeze(base)
    from .coding_benchmark import configuration
    actual=configuration(base,Path('/isolated-workspace'),limits)
    actual=replace(actual,coding_autonomy={**actual.coding_autonomy,
        'max_model_requests':min(limits.max_model_requests_per_case,limits.max_requests)})
    frozen['agent']={k:getattr(actual,k) for k in frozen['agent']}
    profiles=(base,) if mode=='single' else settings(base,live=live)
    frozen.update(campaign_version=4,provider_mode=mode,policy='single' if mode=='single' else POLICY,
        providers=[dict(provider=c.provider,model=labels(c)['model'],
            endpoint_sha256=hashlib.sha256(c.base_url.encode()).hexdigest() if c.base_url else None) for c in profiles],
        limits=asdict(limits),case_id=case_id,live=live,cost_authorized=live,
        source_tree_sha256=legacy.sha({str(p.relative_to(PROJECT_DIR)):legacy.file_sha(p)
            for folder in ('mybot','scripts') for p in sorted((PROJECT_DIR/folder).rglob('*.py')) if not p.name.startswith('._')}))
    return frozen


def inventory(directory):
    root=Path(directory)
    manifest=legacy.read(root/'manifest.json')
    if manifest.get('version')!=4 or manifest.get('kind')!='provider_failover_harness':raise ValueError('wrong_campaign_format')
    if legacy.sha(manifest['frozen'])!=manifest['config_sha256']:raise ValueError('configuration_corrupt')
    identity={k:manifest[k] for k in ('campaign_id','run_id','attempt_id','config_sha256')}
    start=legacy.read(root/'started.json')
    if any(start.get(k)!=v for k,v in identity.items()):raise ValueError('attempt_identity_mismatch')
    result=dict(**identity,status='uncertain',strict_success=False)
    if (root/'terminal.json').exists():
        terminal=legacy.read(root/'terminal.json')
        if any(terminal.get(k)!=v for k,v in identity.items()):raise ValueError('terminal_identity_mismatch')
    if (root/'finished.json').exists():
        if not (root/'terminal.json').exists():raise ValueError('missing_terminal_evidence')
        end=legacy.read(root/'finished.json');raw=legacy.read(root/'raw.json')
        if any(end.get(k)!=v for k,v in identity.items()) or raw.get('execution_identity')!=identity:
            raise ValueError('finished_identity_mismatch')
        if end['report_sha256']!=legacy.file_sha(root/'raw.json') or end['terminal_sha256']!=legacy.file_sha(root/'terminal.json'):
            raise ValueError('evidence_hash_mismatch')
        f=manifest['frozen']
        expected={'mybot_commit':f['benchmark_harness_commit'],'benchmark_sha256':f['benchmark_sha256'],
            'grading_code_sha256':f['grading_code_sha256'],'dependency_lock_sha256':f['dependency_lock_sha256'],
            'limits':f['limits'],'mode':'live' if f['live'] else 'offline'}
        if any(raw.get(k)!=v for k,v in expected.items()) or (f['live'] and raw.get('worktree_dirty') is not False):
            raise ValueError('report_provenance_mismatch')
        if f['provider_mode']=='failover' and (raw.get('provider_mode')!='failover' or raw.get('provider_label')!='mixed'):
            raise ValueError('report_provider_mode_mismatch')
        if len(raw['results'])!=1 or terminal['evidence']!=raw['results'][0] or raw['case_ids']!=[manifest['frozen']['case_id']]:
            raise ValueError('terminal_result_mismatch')
        lifecycle=raw['results'][0].get('lifecycle',{})
        if lifecycle and any(lifecycle.get(k)!=v for k,v in identity.items()):raise ValueError('lifecycle_identity_mismatch')
        requests=raw['results'][0].get('provider_execution',{}).get('requests',[])
        if f['provider_mode']=='failover' and any(
            e.get('attempt_id')!=identity['attempt_id'] or e.get('case_id')!=manifest['frozen']['case_id']
            for e in requests):
            raise ValueError('physical_request_identity_mismatch')
        if f['provider_mode']=='failover':
            providers={c['provider']:c['model'] for c in f['providers']}
            if len(requests)!=raw.get('physical_model_requests') or len(requests)>f['limits']['max_requests'] or any(
                r.get('provider') not in providers or r.get('model')!=providers[r['provider']]
                or r.get('physical_request')!=i for i,r in enumerate(requests,1)):
                raise ValueError('physical_request_provenance_mismatch')
        result.update(status='completed',strict_success=legacy.strict_success(raw))
    if (root/'blocked.json').exists():
        blocked=legacy.read(root/'blocked.json')
        if any(blocked.get(k)!=v for k,v in identity.items()):raise ValueError('blocked_identity_mismatch')
        result.update(status='blocked',strict_success=False,blocked_reason=blocked['category'])
    return result


async def run(directory, *, provider_mode='single', live=False, confirm_api_cost=False,
              case_id='cache-ttl-001', limits=None, offline_provider_factory=None):
    if provider_mode not in ('single','failover'):raise ValueError('invalid_provider_mode')
    if type(live) is not bool or live!=confirm_api_cost:raise ValueError('live_requires_both_flags')
    if live and offline_provider_factory is not None:raise ValueError('live_forbids_synthetic_overrides')
    limits=limits or Limits(max_cases=1,repeats=1,max_requests=12)
    if limits.max_cases!=1 or limits.repeats!=1:raise ValueError('one_case_per_independent_attempt')
    if case_id not in {c.runtime.id for c in load_benchmark().cases}:raise ValueError('invalid_case')
    root=Path(directory).resolve()
    if 'coding_campaign' in root.parts or root.exists():raise ValueError('campaign_exists_or_historical_namespace')
    if live and legacy.git('status','--porcelain'):raise ValueError('live_requires_clean_source')
    frozen=freeze(provider_mode,live,limits,case_id)
    identity=dict(campaign_id=uuid.uuid4().hex,run_id=case_id,attempt_id=uuid.uuid4().hex,config_sha256=legacy.sha(frozen))
    root.mkdir(parents=True)
    legacy.write_new(root/'manifest.json',dict(version=4,kind='provider_failover_harness',**identity,frozen=frozen,created_at=legacy.now()))
    legacy.write_new(root/'started.json',dict(**identity,at=legacy.now()))
    def terminal(value):
        legacy.write_new(root/'terminal.json',dict(**identity,at=legacy.now(),evidence=value))
    try:
        report=await evaluate(provider_mode=provider_mode,live=live,confirm_api_cost=confirm_api_cost,
            limits=limits,case_ids=[case_id],base_config=base_config(live),execution_identity=identity,
            terminal_sink=terminal,offline_provider_factory=offline_provider_factory)
        report['execution_identity']=identity
        legacy.write_new(root/'raw.json',report)
        if not (root/'terminal.json').exists():terminal(report['results'][0])
        if frozen!=freeze(provider_mode,live,limits,case_id):raise ValueError('frozen_environment_changed')
        legacy.write_new(root/'finished.json',dict(**identity,at=legacy.now(),
            report_sha256=legacy.file_sha(root/'raw.json'),terminal_sha256=legacy.file_sha(root/'terminal.json')))
        if not legacy.strict_success(report):
            legacy.write_new(root/'blocked.json',dict(**identity,at=legacy.now(),category=legacy.pause_reason(report) or 'not_strictly_verified'))
    except BaseException:
        if not (root/'blocked.json').exists():
            legacy.write_new(root/'blocked.json',dict(**identity,at=legacy.now(),category='interrupted_or_incomplete_evidence'))
        raise
    return inventory(root),report
