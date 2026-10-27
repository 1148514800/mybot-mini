"""One new offline-only batch, clean preregistration freeze, read-only verification."""
import argparse,json,os,sqlite3,subprocess
from contextlib import closing
from pathlib import Path
from urllib.parse import quote
from scripts.persistent_uat.prepare import file_hash,fingerprint,provider_snapshot
from scripts.uat.server import private_json
from mybot.workspace import init_workspace
from mybot.workspace_lease import WorkspaceLease
from mybot.storage.history import open_store
from scripts.streaming_steer_uat.server import ReadRegistry
from mybot.tools import build_default_tool_registry
from .budget import Ledger,BudgetStop,private_directory
from .plan import BATCH,BASELINE,config_for,contract,plan_hash,FIXTURES

REPO=Path(__file__).resolve().parents[2]

def sources():
    if subprocess.check_output(['git','ls-files','--others','--exclude-standard','--','mybot','scripts'],cwd=REPO).strip():raise BudgetStop('untracked_source')
    names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0')
    return {n:file_hash(REPO/n) for n in names if n and (n.startswith(('mybot/','scripts/')) or n in ('pyproject.toml','uv.lock'))}

def ro(path):
    return sqlite3.connect('file:'+quote(str(path))+'?mode=ro',uri=True)

def prepare(batch,provider_config,browser_evidence):
    batch=Path(batch).absolute();private_directory(batch.parent)
    if batch.exists() or batch.is_symlink():raise BudgetStop('batch_exists_no_replacement')
    probe=json.loads(Path(browser_evidence).read_text())
    if probe.get('passed') is not True or not probe.get('profiles_removed') or not probe.get('server_closed'):raise BudgetStop('browser_isolation_unproven')
    provider=provider_snapshot(provider_config)  # Local bytes/model/presence only, no SDK.
    batch.mkdir(mode=0o700);private_directory(batch/'private');root=batch/'workspace';root.mkdir(mode=0o700);init_workspace(root)
    for name,text in FIXTURES.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    cfg=config_for(batch,dict(model='deepseek-v4.1-flash',base_url='https://offline.invalid/v1',api_key=None))
    names=[d['function']['name'] for d in ReadRegistry(build_default_tool_registry(root,coding_enabled=False,file_access='read_only'),[]).get_definitions()]
    if names or cfg.web_steer or not cfg.web_streaming or cfg.context_compaction['mode']!='deterministic' or cfg.mcp_enabled or cfg.skills_enabled or cfg.coding_enabled or cfg.coding_command['mode']!='off':raise BudgetStop('unsafe_config')
    lease=WorkspaceLease(root).acquire();lease.release()
    engine=open_store(cfg,'web');event_identity=[engine.path.stat().st_dev,engine.path.stat().st_ino];engine.close()
    ledger=Ledger(batch/'private/requests.sqlite',plan_hash())
    private_json(batch/'browser-isolation.json',probe)
    data=dict(version=1,authorization='NOT_GRANTED',contract=contract(),plan_sha256=plan_hash(),provider=provider,provider_config_path=str(Path(provider_config).resolve()),workspace_hashes=fingerprint(root),workspace_identity=[root.stat().st_dev,root.stat().st_ino],event_identity=event_identity,ledger_identity=list(ledger.identity),event_path=str(cfg.session_event_path),ledger_path=str(ledger.path),browser_evidence_sha256=file_hash(batch/'browser-isolation.json'),
        configuration={k:getattr(cfg,k) for k in ('session_max_turns','coding_enabled','coding_file_access','coding_patch_mode','mcp_enabled','skills_enabled','max_react_steps','max_completion_tokens','request_timeout_seconds','context_token_budget','context_compaction','web_streaming','web_steer')},environment=dict(local_only=True,real_requests=0,credential_remote_validity='UNVERIFIED',tool_names=names,workspace_lease='acquired_and_released'))
    private_json(batch/'prepared.json',data);return data

def freeze(batch,provider_config):
    batch=Path(batch).resolve()
    if (batch/'freeze.json').exists():raise BudgetStop('already_frozen_no_replacement')
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO).strip():raise BudgetStop('freeze_requires_clean_commit')
    subprocess.run(['git','merge-base','--is-ancestor',BASELINE,'HEAD'],cwd=REPO,check=True,capture_output=True)
    p=json.loads((batch/'prepared.json').read_text())
    if str(Path(provider_config).resolve())!=p['provider_config_path']:raise BudgetStop('provider_path_changed')
    if [ (batch/'workspace').stat().st_dev, (batch/'workspace').stat().st_ino ]!=p['workspace_identity']:raise BudgetStop('workspace_replaced')
    if p['plan_sha256']!=plan_hash() or p['provider']!=provider_snapshot(provider_config) or p['workspace_hashes']!=fingerprint(batch/'workspace'):raise BudgetStop('prepared_changed')
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
    if p['provider']!=provider_snapshot(provider_config) or p['workspace_hashes']!=fingerprint(batch/'workspace'):raise BudgetStop('provider_or_workspace_changed')
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
                if usage['real_requests']>1 or usage['http_attempts']>1 or usage['attempts']>1 or any(c not in LIMITS or n>LIMITS[c] for c,n in counts.items()):raise BudgetStop('budget_invalid')
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
