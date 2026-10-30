"""Offline preparation and clean-commit freeze; never builds a model client."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
from scripts.uat.server import credentials,private_json
from mybot.workspace import init_workspace
from mybot.workspace_lease import WorkspaceLease
from mybot.storage.history import open_store
from mybot.tools import build_default_tool_registry
from .plan import BATCH,BASELINE,config_for,plan_hash,preregistration
from .budget import Ledger,BudgetStop,private_directory

REPO=Path(__file__).resolve().parents[2]

def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def sources():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0')
    return {n:file_hash(REPO/n) for n in names if n and (n.startswith(('mybot/','scripts/')) or n in ('pyproject.toml','uv.lock'))}

def fingerprint(root):
    result={}
    for p in sorted(Path(root).rglob('*')):
        if p.is_symlink():raise BudgetStop('workspace_symlink')
        if p.is_file():result[str(p.relative_to(root))]=file_hash(p)
    return result

def provider_snapshot(path):
    providers=credentials(path)
    return dict(file_sha256=file_hash(path),providers={k:dict(model=v['model'],base_url_sha256=hashlib.sha256(v['base_url'].encode()).hexdigest(),credential_present=True) for k,v in providers.items()})

def prepare(batch,provider_config):
    batch=Path(batch).absolute();private_directory(batch.parent)
    if batch.exists():raise BudgetStop('batch_exists_no_replacement')
    batch.mkdir(mode=0o700);private_directory(batch/'private');root=batch/'workspace';root.mkdir(mode=0o700)
    init_workspace(root)
    (root/'README.md').write_text('# Disposable Markdown design discussion\nNo real user project or data. Discussion only; no writes authorized.\n')
    cfg=config_for(batch,dict(model='deepseek-v4.1-flash',base_url='https://offline.invalid/v1',api_key=None))
    tools=build_default_tool_registry(root,coding_enabled=False)
    names=[t['function']['name'] for t in tools.get_definitions()]
    if set(names)!={'read_file','list_files'} or cfg.mcp_enabled or cfg.coding_enabled or cfg.context_compaction['mode']!='deterministic':raise BudgetStop('unsafe_config')
    lease=WorkspaceLease(root).acquire();lease.release()
    engine=open_store(cfg,'web');event_identity=[engine.path.stat().st_dev,engine.path.stat().st_ino];engine.close()
    ledger=Ledger(batch/'private/requests.sqlite',plan_hash())
    value=dict(version=1,authorization='NOT_GRANTED',plan_sha256=plan_hash(),contract=preregistration(),provider=provider_snapshot(provider_config),workspace_hashes=fingerprint(root),
        event_identity=event_identity,event_path=str(cfg.session_event_path),ledger_path=str(ledger.path),
        configuration={k:getattr(cfg,k) for k in ('session_max_turns','coding_enabled','coding_patch_mode','mcp_enabled','skills_enabled','max_react_steps','max_completion_tokens','request_timeout_seconds','context_token_budget','context_compaction')},
        environment=dict(status='OFFLINE_PASS',workspace_lease='acquired_and_released',tool_names=names,event_store='private v1 opened and closed',credential_check='local presence/model match only; remote validity unverified',real_requests=0))
    private_json(batch/'prepared.json',value);return value

def freeze(batch,provider_config):
    batch=Path(batch).resolve()
    if (batch/'freeze.json').exists():raise BudgetStop('already_frozen')
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO).strip():raise BudgetStop('freeze_requires_clean_commit')
    data=json.loads((batch/'prepared.json').read_text())
    if data['plan_sha256']!=plan_hash() or data['provider']!=provider_snapshot(provider_config):raise BudgetStop('prepared_or_provider_changed')
    if data['workspace_hashes']!=fingerprint(batch/'workspace'):raise BudgetStop('workspace_changed')
    ledger=Ledger(batch/'private/requests.sqlite',plan_hash())
    with ledger.connect() as db:
        if db.execute('SELECT count(*) FROM cases').fetchone()[0] or ledger.rows():raise BudgetStop('attempt_already_started')
    value=dict(version=1,plan_sha256=plan_hash(),preregistration_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),source_hashes=sources(),prepared_sha256=file_hash(batch/'prepared.json'),ledger_identity=list(ledger.identity),event_identity=data['event_identity'])
    private_json(batch/'freeze.json',value);return value

def verify_frozen(batch,provider_config):
    batch=Path(batch).resolve();value=json.loads((batch/'freeze.json').read_text());data=json.loads((batch/'prepared.json').read_text())
    if value['plan_sha256']!=plan_hash() or value['source_hashes']!=sources() or value['prepared_sha256']!=file_hash(batch/'prepared.json'):raise BudgetStop('frozen_source_or_contract_changed')
    if data['provider']!=provider_snapshot(provider_config) or data['workspace_hashes']!=fingerprint(batch/'workspace'):raise BudgetStop('configuration_or_workspace_changed')
    for path,key in ((batch/'private/requests.sqlite','ledger_identity'),(batch/'private/session-events.sqlite3','event_identity')):
        info=path.lstat()
        if path.is_symlink() or [info.st_dev,info.st_ino]!=value[key]:raise BudgetStop('database_replaced')
    subprocess.run(['git','merge-base','--is-ancestor',value['preregistration_commit'],'HEAD'],cwd=REPO,check=True,capture_output=True)
    return value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','freeze','verify']);parser.add_argument('--batch',type=Path,default=BATCH);parser.add_argument('--provider-config',type=Path,required=True);a=parser.parse_args()
    result=prepare(a.batch,a.provider_config) if a.action=='prepare' else freeze(a.batch,a.provider_config) if a.action=='freeze' else verify_frozen(a.batch,a.provider_config)
    print(json.dumps(dict(status=a.action.upper()+'_OFFLINE',real_requests=0,plan_sha256=plan_hash(),preregistration_commit=result.get('preregistration_commit'))))
if __name__=='__main__':main()
