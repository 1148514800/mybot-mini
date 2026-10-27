"""Unique Coding batch preparation; revision-aware verification after legal Patch."""
import argparse,asyncio,json,sqlite3,subprocess,os
from contextlib import closing
from pathlib import Path
from scripts.streaming_steer_recovery_v3.prepare import sources,ro
from scripts.persistent_uat.prepare import file_hash,provider_snapshot
from scripts.uat.server import private_json
from mybot.storage.history import open_store
from mybot.workspace_lease import WorkspaceLease
from .plan import *
from .fixture import create,hashes
from .integrity import IntegrityGate,digest_images
from .score import validate_fixture
from .budget import Ledger,BudgetStop,private_directory
REPO=Path(__file__).resolve().parents[2]

def prepare(batch,provider_config,browser_evidence):
    batch=Path(batch).absolute();private_directory(batch.parent)
    if batch.exists() or batch.is_symlink():raise BudgetStop('batch_exists_no_replacement')
    probe=json.loads(Path(browser_evidence).read_text())
    if not probe.get('passed') or not probe.get('profiles_removed') or not probe.get('server_closed'):raise BudgetStop('browser_isolation_unproven')
    validation=asyncio.run(validate_fixture())
    if validation['baseline_public']['status']!='fail' or validation['baseline_host']['status']!='fail' or not validation['reference_public']['passed'] or not validation['reference_host']['passed']:raise BudgetStop('fixture_or_sandbox_unverified')
    provider=provider_snapshot(provider_config)
    batch.mkdir(mode=0o700);private_directory(batch/'private');head=create(batch/'workspace');gate=IntegrityGate(batch/'workspace',batch/'private/integrity.json');gate.initialize();state=gate.verify()
    cfg=config_for(batch,dict(model='deepseek-v4.1-flash',base_url='http://offline.invalid',api_key=None));lease=WorkspaceLease(cfg.workspace).acquire();lease.release();engine=open_store(cfg,'web');event_identity=[engine.path.stat().st_dev,engine.path.stat().st_ino];engine.close();ledger=Ledger(batch/'private/requests.sqlite',plan_hash())
    private_json(batch/'browser-isolation.json',probe)
    data=dict(version=1,authorization='NOT_GRANTED',plan_sha256=plan_hash(),contract=contract(),fixture_hashes=hashes(),fixture_validation=validation,fixture_head=head,provider=provider,provider_config_path=str(Path(provider_config).resolve()),workspace_hashes=state['workspace'],git_hashes=state['git'],workspace_identity=[cfg.workspace.stat().st_dev,cfg.workspace.stat().st_ino],event_identity=event_identity,ledger_identity=list(ledger.identity),browser_evidence_sha256=file_hash(batch/'browser-isolation.json'))
    private_json(batch/'prepared.json',data);return data

def freeze(batch,provider_config):
    batch=Path(batch).resolve()
    if (batch/'freeze.json').exists():raise BudgetStop('already_frozen_no_replacement')
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO).strip():raise BudgetStop('freeze_requires_clean_commit')
    subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'HEAD'],cwd=REPO,check=True,capture_output=True)
    p=json.loads((batch/'prepared.json').read_text())
    if str(Path(provider_config).resolve())!=p['provider_config_path']:raise BudgetStop('provider_path_changed')
    if [ (batch/'workspace').stat().st_dev, (batch/'workspace').stat().st_ino ]!=p['workspace_identity']:raise BudgetStop('workspace_replaced')
    initial=IntegrityGate(batch/'workspace',batch/'private/integrity.json').verify()
    if initial['revision']!=0 or initial['workspace']!=p['workspace_hashes'] or initial['git']!=p['git_hashes']:raise BudgetStop('initial_workspace_changed')
    if p['plan_sha256']!=plan_hash() or p['provider']!=provider_snapshot(provider_config):raise BudgetStop('prepared_changed')
    if file_hash(batch/'browser-isolation.json')!=p['browser_evidence_sha256']:raise BudgetStop('browser_evidence_changed')
    for name,key in [('requests.sqlite','ledger_identity'),('session-events.sqlite3','event_identity')]:
        path=batch/'private'/name;info=path.lstat()
        if path.is_symlink() or [info.st_dev,info.st_ino]!=p[key]:raise BudgetStop('database_replaced')
        with closing(ro(path)) as db:
            if db.execute('pragma integrity_check').fetchone()[0]!='ok':raise BudgetStop('database_corrupt')
            tables=['cases','reservations'] if name=='requests.sqlite' else ['events','sessions']
            if any(db.execute('select count(*) from '+t).fetchone()[0] for t in tables):raise BudgetStop('live_state_already_present')
    value=dict(version=1,plan_sha256=plan_hash(),preregistration_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),source_hashes=sources(),prepared_sha256=file_hash(batch/'prepared.json'),ledger_identity=p['ledger_identity'],event_identity=p['event_identity'],browser_evidence_sha256=p['browser_evidence_sha256'])
    private_json(batch/'freeze.json',value);return value

def verify_frozen(batch,provider_config,*,allow_halt=False):
    batch=Path(batch).resolve();f=json.loads((batch/'freeze.json').read_text());p=json.loads((batch/'prepared.json').read_text())
    if str(Path(provider_config).resolve())!=p['provider_config_path']:raise BudgetStop('provider_path_changed')
    if f['plan_sha256']!=plan_hash() or f['source_hashes']!=sources() or f['prepared_sha256']!=file_hash(batch/'prepared.json'):raise BudgetStop('frozen_source_or_contract_changed')
    if [ (batch/'workspace').stat().st_dev, (batch/'workspace').stat().st_ino ]!=p['workspace_identity']:raise BudgetStop('workspace_replaced')
    if p['provider']!=provider_snapshot(provider_config):raise BudgetStop('provider_or_workspace_changed')
    integrity=IntegrityGate(batch/'workspace',batch/'private/integrity.json').verify()
    if integrity['git']!=p['git_hashes'] or integrity['head']!=p['fixture_head'] or {n:v for n,v in integrity['workspace'].items() if n not in ALLOWED}!={n:v for n,v in p['workspace_hashes'].items() if n not in ALLOWED}:raise BudgetStop('protected_assets_drift')
    expected={n:p['workspace_hashes'][n]['sha256'] for n in ALLOWED}
    for i,change in enumerate(integrity['native_patch_chain'],1):
        if change['revision']!=i or change['before_hashes']!=expected or not change['receipt_commit_success'] or not change['preview_to_commit_consistent']:raise BudgetStop('revision_chain_invalid')
        expected=change['after_hashes']
    if expected!={n:integrity['workspace'][n]['sha256'] for n in ALLOWED}:raise BudgetStop('revision_hash_mismatch')
    if file_hash(batch/'browser-isolation.json')!=f['browser_evidence_sha256']:raise BudgetStop('browser_evidence_changed')
    usage={}
    for name,key in [('requests.sqlite','ledger_identity'),('session-events.sqlite3','event_identity')]:
        path=batch/'private'/name;info=path.lstat()
        if path.is_symlink() or [info.st_dev,info.st_ino]!=f[key] or info.st_uid!=os.geteuid() or info.st_nlink!=1 or info.st_mode&0o077:raise BudgetStop('database_identity_or_privacy_changed')
        with closing(ro(path)) as db:
            if db.execute('pragma integrity_check').fetchone()[0]!='ok':raise BudgetStop('database_corrupt')
            if name=='session-events.sqlite3' and db.execute("SELECT 1 FROM turns WHERE state='execution_uncertain' LIMIT 1").fetchone():raise BudgetStop('uncertain_execution')
            if name=='requests.sqlite':
                if db.execute("select 1 from meta where key='plan' and value=?",(plan_hash(),)).fetchone() is None:raise BudgetStop('ledger_plan_changed')
                if not allow_halt and db.execute("select 1 from meta where key='halt'").fetchone():raise BudgetStop('batch_halted')
                usage=dict(real_requests=db.execute('select count(*) from reservations').fetchone()[0],attempts=db.execute('select count(*) from cases').fetchone()[0],unsettled=db.execute("select count(*) from reservations where state='reserved'").fetchone()[0],http_attempts=db.execute('select coalesce(sum(http_attempts),0) from reservations').fetchone()[0])
                from .plan import LIMITS
                counts=dict(db.execute('select case_id,count(*) from reservations group by case_id'))
                if usage['real_requests']>GLOBAL_LIMIT or usage['http_attempts']>GLOBAL_LIMIT or usage['attempts']>len(LIMITS) or any(c not in LIMITS or n>LIMITS[c] for c,n in counts.items()):raise BudgetStop('budget_invalid')
    subprocess.run(['git','merge-base','--is-ancestor',f['preregistration_commit'],'HEAD'],cwd=REPO,check=True,capture_output=True)
    return {**f,'usage':usage}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','freeze','verify']);p.add_argument('--batch',type=Path,default=BATCH);p.add_argument('--provider-config',type=Path,required=True);p.add_argument('--browser-evidence',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.browser_evidence is None:p.error('--browser-evidence required for new preparation')
        result=prepare(a.batch,a.provider_config,a.browser_evidence)
    elif a.action=='freeze':result=freeze(a.batch,a.provider_config)
    else:result=verify_frozen(a.batch,a.provider_config)
    if a.action=='verify' and result['usage']['unsettled']:raise BudgetStop('unsettled_request_preflight')
    print(json.dumps(dict(status=a.action.upper()+'_OFFLINE',plan_sha256=plan_hash(),preregistration_commit=result.get('preregistration_commit'),usage=result.get('usage',dict(real_requests=0,attempts=0,unsettled=0,http_attempts=0)))))
if __name__=='__main__':main()
