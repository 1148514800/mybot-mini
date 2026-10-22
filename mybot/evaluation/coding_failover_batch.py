"""Sequential, create-once batch over the original v4 attempts; durable pre-dispatch ledger."""
import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import uuid

from . import coding_campaign as meta
from . import coding_failover_campaign as v4
from .coding_fixtures import load_benchmark
from .coding_live import Limits
from ..config import PROJECT_DIR

SUITE = 'full12-plus-forced'
CASES = ('config-default-001','cache-ttl-001','pagination-001','serialization-001',
         'csv-export-001','timezone-day-001','file-recovery-001','cli-precedence-001',
         'validation-chain-001','cache-sync-001','parse-convert-001','error-retry-001')


def atomic_new(path, value):
    """Publish complete fsynced immutable JSON via same-directory no-clobber hard link."""
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(meta.encoded(value));stream.flush();os.fsync(stream.fileno())
        os.link(name,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:os.unlink(name)


def plan():
    known={c.runtime.id:c.runtime.difficulty for c in load_benchmark().cases}
    if set(known)!=set(CASES):raise ValueError('benchmark_plan_changed')
    rows=[]
    for n,case in enumerate((*CASES,'cache-ttl-001')):
        cap=12 if n<4 or n==12 else 16 if n<8 else 20
        rows.append(dict(slot=f'{n+1:02d}-'+(case if n<12 else 'forced-failover-coding'),case_id=case,
            difficulty=known[case],group='natural' if n<12 else 'controlled',
            fault_mode='none' if n<12 else 'primary_connection_once',
            limits=dict(max_cases=1,repeats=1,max_requests=cap,max_model_requests_per_case=cap,
                        request_timeout=90.,task_timeout=480.,total_timeout=600.,max_output_tokens=2048)))
    return rows


def read_manifest(root):
    m=meta.read(Path(root)/'batch.json')
    if m.get('version')!=1 or m.get('suite')!=SUITE or m.get('max_physical_requests')!=204:
        raise ValueError('wrong_batch_format')
    if m['plan']!=plan() or meta.sha(m['plan'])!=m['plan_sha256'] or meta.sha(m['frozen'])!=m['frozen_sha256']:
        raise ValueError('batch_frozen_corrupt')
    return m


def ledger(root, m):
    rows={x['slot']:x for x in m['plan']};starts=sorted((Path(root)/'requests').glob('*-started.json'))
    ends=list((Path(root)/'requests').glob('*-finished.json'))
    if len(ends)>len(starts):raise ValueError('orphan_request_outcome')
    counts={x:0 for x in rows};records=[]
    for n,p in enumerate(starts,1):
        s=meta.read(p)
        if p.name!=f'{n:04d}-started.json' or s['batch_id']!=m['batch_id'] or s['batch_physical_request']!=n or s['slot'] not in rows:
            raise ValueError('request_sequence_corrupt')
        slot=s['slot'];counts[slot]+=1
        if s['physical_request']!=counts[slot] or counts[slot]>rows[slot]['limits']['max_requests']:
            raise ValueError('case_ledger_overrun')
        identity=meta.read(Path(root)/'attempts'/slot/'manifest.json')
        if any(s[k]!=identity[k] for k in ('attempt_id','config_sha256')) or s['case_id']!=rows[slot]['case_id']:
            raise ValueError('request_identity_corrupt')
        e=Path(root)/'requests'/f'{n:04d}-finished.json'
        if not e.exists():raise ValueError('incomplete_request_requires_audit')
        end=meta.read(e)
        if end['reservation_sha256']!=meta.file_sha(p):raise ValueError('request_outcome_corrupt')
        q=end['record']
        if any(q.get(k)!=s[k] for k in ('attempt_id','case_id','physical_request','provider','model','batch_physical_request')):
            raise ValueError('request_outcome_identity')
        records.append(q)
    if len(starts)>204 or sum(counts[x['slot']] for x in m['plan'] if x['group']=='natural')>192:
        raise ValueError('batch_budget_overrun')
    return records


class RequestLedger:
    def __init__(self,root,m,row):self.root=Path(root);self.m=m;self.row=row;self.pending=None
    def before(self,record):
        if self.pending is not None:raise ValueError('concurrent_model_dispatch')
        m=read_manifest(self.root)
        if m!=self.m:raise ValueError('batch_manifest_changed')
        if (self.root/'stopped.json').exists():raise ValueError('batch_stopped')
        row=self.row
        if v4.freeze('failover',m['live'],Limits(**row['limits']),row['case_id'],row['fault_mode'])!=m['frozen'][row['slot']]:
            raise ValueError('frozen_environment_changed')
        prior=ledger(self.root,m)
        if len(prior)>=204:raise ValueError('batch_budget_exhausted')
        own=[q for q in prior if q['case_id']==row['case_id'] and q['attempt_id']==record['attempt_id']]
        if len(own)>=row['limits']['max_requests'] or record['physical_request']!=len(own)+1:
            raise ValueError('case_budget_exhausted')
        identity=meta.read(self.root/'attempts'/row['slot']/'manifest.json')
        if identity['frozen']!=m['frozen'][row['slot']] or record['attempt_id']!=identity['attempt_id']:
            raise ValueError('dispatch_identity_mismatch')
        number=len(prior)+1;record['batch_physical_request']=number
        entry={k:record[k] for k in ('attempt_id','case_id','physical_request','provider','model','batch_physical_request')}
        entry.update(batch_id=m['batch_id'],slot=row['slot'],config_sha256=identity['config_sha256'],at=meta.now())
        path=self.root/'requests'/f'{number:04d}-started.json';atomic_new(path,entry);self.pending=path
    def after(self,record):
        if self.pending is None:raise ValueError('missing_dispatch_reservation')
        p=self.pending
        atomic_new(p.with_name(p.name.replace('started','finished')),
                   dict(reservation_sha256=meta.file_sha(p),record=copy.deepcopy(record),at=meta.now()))
        self.pending=None


def audit_case(root,m,row):
    folder=Path(root)/'attempts'/row['slot'];inv=v4.inventory(folder)
    if not (folder/'finished.json').exists():raise ValueError('incomplete_attempt')
    manifest=meta.read(folder/'manifest.json')
    if manifest['frozen']!=m['frozen'][row['slot']]:raise ValueError('attempt_freeze_mismatch')
    raw=meta.read(folder/'raw.json');r=raw['results'][0];j=r['judge'];metrics=r['metrics'];life=r['lifecycle']
    requests=[q for q in ledger(root,m) if q['attempt_id']==manifest['attempt_id']]
    actual=r.get('provider_execution',{}).get('requests',[])
    if len(requests)!=len(actual):raise ValueError('unaccounted_requests')
    for logged,final in zip(requests,actual):
        expected=copy.deepcopy(final)
        if expected['status']=='protocol_rejected' and logged['status']=='returned':
            expected.update(status='returned',error_category=None)
        if logged!=expected:raise ValueError('request_report_mismatch')
    unsafe=(not life.get('cleanup_confirmed') or life.get('execution_uncertain') or life.get('approval_cancelled')
        or life.get('terminal_reason')!='completed' or r.get('runtime_error') or meta.pause_reason(raw)
        or r.get('journal_evidence',{}).get('uncertain') or j.get('index_changed') is not False
        or any(j.get(k)!=0 for k in ('protected_file_changes','unrelated_file_changes','journal_attribution_mismatch'))
        or metrics.get('tool_call_ids_paired') is not True
        or any(metrics.get(k)!=0 for k in ('sandbox_failures','execution_uncertain_count','approval_denials','workspace_escape_attempts','protocol_false_verified_count'))
        or any(q.get('error_category') in ('authentication_error','permission_error','protocol_error','local_programming_error') for q in actual))
    # One recoverable primary failure may be recovered naturally; persistent provider failures stop.
    provider_failed=any(q['status']!='returned' and not q.get('synthetic_injected') for q in actual[-1:])
    unsafe=bool(unsafe or provider_failed or raw.get('api_failures'))
    return dict(slot=row['slot'],case_id=row['case_id'],difficulty=row['difficulty'],group=row['group'],
        attempt_id=manifest['attempt_id'],status=inv['status'],strict_success=inv['strict_success'],
        infra='BLOCKED' if unsafe else 'PASS',task='PASS' if inv['strict_success'] else 'FAIL',
        requests=len(actual),agent_state=r['agent_state'],workflow_success=r['agent_workflow_success'],
        hidden_pass=j.get('judge_state')=='hidden_pass',failure=r.get('failure'),cleanup_confirmed=life['cleanup_confirmed'],
        evidence_sha256={p.name:meta.file_sha(p) for p in folder.glob('*.json')})


def status(root):
    root=Path(root);m=read_manifest(root);requests=ledger(root,m);rows=[];attempts=[]
    for row in m['plan']:
        slot=row['slot'];started=root/'slots'/f'{slot}-started.json';end=root/'slots'/f'{slot}-finished.json'
        if not started.exists():
            if end.exists() or (root/'attempts'/slot).exists():raise ValueError('orphan_attempt')
            rows.append(dict(**row,status='pending'));continue
        if meta.read(started)!=dict(batch_id=m['batch_id'],slot=slot,plan_sha256=m['plan_sha256']):raise ValueError('slot_identity_corrupt')
        if not end.exists():rows.append(dict(**row,status='uncertain'));continue
        evidence=audit_case(root,m,row)
        if meta.read(end)!=evidence:raise ValueError('slot_receipt_corrupt')
        if evidence['attempt_id'] in attempts:raise ValueError('duplicate_attempt')
        attempts.append(evidence['attempt_id']);rows.append(evidence)
    return dict(batch_id=m['batch_id'],status='stopped' if (root/'stopped.json').exists() else 'completed' if (root/'finished.json').exists() else 'incomplete',
        physical_requests=len(requests),http_requests=sum(q['http_dispatch_count'] for q in requests) if all(q['http_dispatch_count'] is not None for q in requests) else None,
        synthetic_injected_attempts=sum(bool(q.get('synthetic_injected')) for q in requests),
        completed=sum('strict_success' in x for x in rows),strict_successes=sum(x.get('strict_success',False) for x in rows),rows=rows)


async def run(root,*,live=False,confirm_api_cost=False,max_physical_requests=204,offline_provider_factory=None):
    root=Path(root).resolve()
    if not root.is_relative_to((PROJECT_DIR/'runs/coding_failover').resolve()) or 'coding_campaign' in root.parts:
        raise ValueError('independent_namespace_required')
    if root.exists():raise ValueError('batch_exists_no_resume_or_replay')
    if type(live) is not bool or live!=confirm_api_cost or max_physical_requests!=204:raise ValueError('fixed_authorized_budget_required')
    if live and (offline_provider_factory is not None or meta.git('status','--porcelain')):raise ValueError('clean_live_source_required')
    rows=plan();frozen={r['slot']:v4.freeze('failover',live,Limits(**r['limits']),r['case_id'],r['fault_mode']) for r in rows}
    if live:
        import sys
        if not sys.stdin.isatty() or not sys.stdout.isatty():raise ValueError('real_tty_required')
    root.mkdir(parents=True)
    for name in ('slots','attempts','requests'):(root/name).mkdir()
    m=dict(version=1,suite=SUITE,batch_id=uuid.uuid4().hex,live=live,max_physical_requests=204,
           plan=rows,plan_sha256=meta.sha(rows),frozen=frozen,frozen_sha256=meta.sha(frozen),at=meta.now())
    atomic_new(root/'batch.json',m)
    # Directory existence itself forbids any second executor, even after crash.
    provider_fault_streak=0
    try:
        for row in rows:
            if read_manifest(root)!=m:raise ValueError('batch_manifest_changed')
            if v4.freeze('failover',live,Limits(**row['limits']),row['case_id'],row['fault_mode'])!=frozen[row['slot']]:
                raise ValueError('frozen_environment_changed')
            atomic_new(root/'slots'/f"{row['slot']}-started.json",dict(batch_id=m['batch_id'],slot=row['slot'],plan_sha256=m['plan_sha256']))
            print(json.dumps(dict(event='batch_case_started',slot=row['slot'],case_id=row['case_id']),ensure_ascii=True),flush=True)
            await v4.run(root/'attempts'/row['slot'],provider_mode='failover',live=live,confirm_api_cost=confirm_api_cost,
                case_id=row['case_id'],limits=Limits(**row['limits']),fault_mode=row['fault_mode'],
                request_audit=RequestLedger(root,m,row),offline_provider_factory=offline_provider_factory)
            result=audit_case(root,m,row);atomic_new(root/'slots'/f"{row['slot']}-finished.json",result)
            print(json.dumps(dict(event='batch_case_finished',**result),ensure_ascii=True),flush=True)
            if result['infra']!='PASS':raise ValueError('attempt_requires_audit')
            if row['group']=='natural':
                recent=meta.read(root/'attempts'/row['slot']/'raw.json')['results'][0]['provider_execution']['requests']
                provider_fault_streak=provider_fault_streak+1 if any(q['status']!='returned' for q in recent) else 0
                if provider_fault_streak>=2:raise ValueError('sustained_provider_faults')
        atomic_new(root/'finished.json',dict(batch_id=m['batch_id'],at=meta.now(),requests=len(ledger(root,m))))
    except BaseException:
        atomic_new(root/'stopped.json',dict(batch_id=m['batch_id'],category='batch_stopped_requires_audit',at=meta.now()))
        raise
    return status(root)
