"""Prepare once, before freeze. Never called for a live-started batch."""
import argparse,asyncio,json,os
from pathlib import Path
from .fixtures import create,assess,GOLD_U03,HIDDEN
from .plan import preregistration,plan_hash
from .server import private_json

async def prepare(batch):
    batch=Path(batch).resolve();batch.mkdir(mode=0o700,parents=True,exist_ok=True)
    if (batch/'prepared.json').exists():raise RuntimeError('batch_already_prepared')
    if (batch/'requests.sqlite').exists():raise RuntimeError('ledger_already_exists')
    values={}
    for case in preregistration()['limits']:
        root=batch/'workspaces'/case
        values[case]={'before':create(case,root)}
        if case in ('U03','U04','U05'):values[case]['public_before']=await assess(case,root,hidden=False)
        if case in HIDDEN:values[case]['independent_before']=await assess(case,root)
    private_json(batch/'prepared.json',{'plan_hash':plan_hash(),'fixtures':values,'oracle_sha256':__import__('hashlib').sha256(json.dumps([GOLD_U03,HIDDEN],sort_keys=True).encode()).hexdigest()})
    return values
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('batch');args=parser.parse_args()
    result=asyncio.run(prepare(args.batch));print(json.dumps({k:{key:value['passed'] for key,value in v.items() if key!='before'} for k,v in result.items()}))
