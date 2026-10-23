"""Prepare independent APFS fixtures; freeze only a clean committed preregistration."""
import argparse,asyncio,hashlib,json,os,subprocess,stat
from pathlib import Path
from scripts.uat.server import private_json
from .budget import Ledger,BudgetStop
from .fixtures import create,fingerprint
from .plan import plan_hash,preregistration,LIMITS,MODELS,LIVE_AUTHORIZATION
from .preflight import require_environment
from .calibrate import calibrate

REPO=Path(__file__).resolve().parents[2]


def source_hashes():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0')[:-1]
    selected=[n for n in names if n.startswith(('mybot/','scripts/uat/','scripts/uat_v2/','scripts/check_targeted_user_uat_v2')) or n in ('pyproject.toml','uv.lock')]
    return {n:hashlib.sha256((REPO/n).read_bytes()).hexdigest() for n in selected}


def verify_fixture(case,root,prepared):
    if fingerprint(root)!=prepared['fixtures'][case]:raise BudgetStop('frozen_fixture_changed')
    for item in prepared['environment'][case]['files']:
        path=root/item['path'];info=path.lstat()
        stamp=[info.st_dev,info.st_ino,info.st_mtime_ns,info.st_ctime_ns]
        if stamp!=item['version'] or info.st_uid!=item['uid'] or info.st_gid!=item['gid'] or oct(stat.S_IMODE(info.st_mode))!=item['mode']:
            raise BudgetStop('frozen_fixture_metadata_changed')


def provider_snapshot(path):
    # Offline local read only. Never instantiate a client or print credentials.
    data=Path(path).read_bytes();config=json.loads(data);llm=config['llm']
    if llm['provider']!='coco':raise BudgetStop('unexpected_primary')
    snapshot={}
    for name,model in MODELS.items():
        provider=llm['providers'][name]
        if provider['model']!=model:raise BudgetStop('provider_model_changed')
        if not provider.get('api_key') or provider['api_key'].startswith('YOUR_'):raise BudgetStop('provider_credential_missing')
        snapshot[name]=dict(model=model,base_url_sha256=hashlib.sha256(provider['base_url'].encode()).hexdigest())
    return dict(file_sha256=hashlib.sha256(data).hexdigest(),public=snapshot)


async def prepare(batch,provider_config):
    batch=Path(batch).resolve();batch.mkdir(mode=0o700,parents=True,exist_ok=False)
    reports={};fixtures={}
    for case in LIMITS:
        root=batch/'workspaces'/case;fixtures[case]=create(case,root)
        reports[case]=await require_environment(case,root)
    calibration=await calibrate(batch/'workspaces'/'T03')
    if not calibration['passed']:raise BudgetStop('synthetic_calibration_failed')
    if any(fingerprint(batch/'workspaces'/case)!=before for case,before in fixtures.items()):raise BudgetStop('preparation_changed_fixture')
    ledger=Ledger(batch/'requests.sqlite',plan_hash())
    value=dict(version=2,authorization=LIVE_AUTHORIZATION,plan_hash=plan_hash(),fixtures=fixtures,
               environment=reports,calibration=calibration,provider=provider_snapshot(provider_config))
    private_json(batch/'prepared.json',value)
    return value


def freeze(batch,provider_config):
    batch=Path(batch).resolve()
    if (batch/'freeze.json').exists():raise BudgetStop('already_frozen')
    if subprocess.check_output(['git','status','--porcelain'],cwd=REPO).strip():raise BudgetStop('freeze_requires_clean_commit')
    prepared=json.loads((batch/'prepared.json').read_text())
    if prepared['plan_hash']!=plan_hash() or prepared['provider']!=provider_snapshot(provider_config):raise BudgetStop('prepared_contract_changed')
    ledger=Ledger(batch/'requests.sqlite',plan_hash())
    with ledger.connect() as db:
        if db.execute('SELECT COUNT(*) FROM cases').fetchone()[0] or ledger.rows():raise BudgetStop('live_already_started')
    for case in LIMITS:
        verify_fixture(case,batch/'workspaces'/case,prepared)
    info=ledger.path.stat();value=dict(version=2,plan_hash=plan_hash(),preregistration_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO).decode().strip(),
        source_hashes=source_hashes(),prepared_sha256=hashlib.sha256((batch/'prepared.json').read_bytes()).hexdigest(),
        provider_config_sha256=prepared['provider']['file_sha256'],ledger_identity=[info.st_dev,info.st_ino])
    private_json(batch/'freeze.json',value);return value


def verify_frozen(batch,provider_config):
    batch=Path(batch).resolve();frozen=json.loads((batch/'freeze.json').read_text())
    if frozen['plan_hash']!=plan_hash() or frozen['source_hashes']!=source_hashes():raise BudgetStop('frozen_source_or_plan_changed')
    if hashlib.sha256((batch/'prepared.json').read_bytes()).hexdigest()!=frozen['prepared_sha256']:raise BudgetStop('prepared_evidence_changed')
    if provider_snapshot(provider_config)['file_sha256']!=frozen['provider_config_sha256']:raise BudgetStop('provider_config_changed')
    info=(batch/'requests.sqlite').stat()
    if [info.st_dev,info.st_ino]!=frozen['ledger_identity']:raise BudgetStop('ledger_replaced')
    prepared=json.loads((batch/'prepared.json').read_text())
    ledger=Ledger(batch/'requests.sqlite',plan_hash())
    with ledger.connect() as db:started={r[0] for r in db.execute('SELECT id FROM cases')}
    for case,before in prepared['fixtures'].items():
        if case not in started:verify_fixture(case,batch/'workspaces'/case,prepared)
    subprocess.run(['git','merge-base','--is-ancestor',frozen['preregistration_commit'],'HEAD'],cwd=REPO,check=True,capture_output=True)
    return frozen


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','freeze','verify']);p.add_argument('--batch',required=True);p.add_argument('--provider-config',required=True);a=p.parse_args()
    if a.action=='prepare':value=asyncio.run(prepare(a.batch,a.provider_config));print(json.dumps(dict(status='PREPARED_OFFLINE',environment={k:v['status'] for k,v in value['environment'].items()},calibration=value['calibration']['passed'],real_requests=0)))
    elif a.action=='freeze':value=freeze(a.batch,a.provider_config);print(json.dumps(dict(status='FROZEN_OFFLINE',preregistration_commit=value['preregistration_commit'])))
    else:verify_frozen(a.batch,a.provider_config);print('FROZEN_VERIFIED_OFFLINE')
if __name__=='__main__':main()
