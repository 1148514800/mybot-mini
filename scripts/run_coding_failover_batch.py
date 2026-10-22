"""Create-once sequential full12 + controlled failover. Never resumes an existing directory."""
import argparse
import asyncio
import json
from pathlib import Path
from mybot.config import PROJECT_DIR
from mybot.evaluation.coding_failover_batch import run,status,SUITE


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true');p.add_argument('--confirm-api-cost',action='store_true')
    p.add_argument('--suite',choices=[SUITE],default=SUITE)
    p.add_argument('--max-physical-requests',type=int,default=204)
    p.add_argument('--directory',type=Path,default=PROJECT_DIR/'runs/coding_failover/full-batch-001')
    p.add_argument('--status',action='store_true');args=p.parse_args(argv)
    try:
        if not args.directory.resolve().is_relative_to((PROJECT_DIR/'runs/coding_failover').resolve()):raise ValueError('namespace')
        result=status(args.directory) if args.status else asyncio.run(run(args.directory,live=args.live,confirm_api_cost=args.confirm_api_cost,max_physical_requests=args.max_physical_requests))
        print(json.dumps(dict(directory=str(args.directory.resolve()),**result),ensure_ascii=True));return 0
    except (Exception,KeyboardInterrupt):
        print('Batch rejected/stopped; preserve evidence and inspect read-only status. No replay.');return 1


if __name__=='__main__':raise SystemExit(main())
