"""Independent create-once Harness entry; single/offline by default, never resumes."""
import argparse
import asyncio
import json
from pathlib import Path
import uuid
from mybot.config import PROJECT_DIR
from mybot.evaluation.coding_failover_campaign import run,inventory
from mybot.evaluation.coding_live import Limits


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider-mode',choices=('single','failover'),default='single')
    p.add_argument('--live',action='store_true');p.add_argument('--confirm-api-cost',action='store_true')
    p.add_argument('--directory',type=Path)
    p.add_argument('--case-id',default='cache-ttl-001')
    p.add_argument('--status',action='store_true')
    p.add_argument('--max-requests',type=int,default=12)
    p.add_argument('--max-model-requests-per-case',type=int,default=12)
    p.add_argument('--request-timeout',type=float,default=45)
    p.add_argument('--task-timeout',type=float,default=240)
    p.add_argument('--total-timeout',type=float,default=900)
    args=p.parse_args(argv)
    root=PROJECT_DIR/'runs/coding_failover'
    directory=args.directory or root/uuid.uuid4().hex
    try:
        if not directory.resolve().is_relative_to(root.resolve()):raise ValueError('independent_namespace_required')
        if args.status:
            if not args.directory:raise ValueError('status_requires_directory')
            result=inventory(directory)
        else:
            limits=Limits(max_cases=1,repeats=1,max_requests=args.max_requests,
                max_model_requests_per_case=args.max_model_requests_per_case,request_timeout=args.request_timeout,
                task_timeout=args.task_timeout,total_timeout=args.total_timeout)
            result,_=asyncio.run(run(directory,provider_mode=args.provider_mode,live=args.live,
                confirm_api_cost=args.confirm_api_cost,case_id=args.case_id,limits=limits))
        print(json.dumps(dict(directory=str(directory.resolve()),**result),ensure_ascii=False))
        return 0
    except (Exception,KeyboardInterrupt):
        print('Evaluation rejected/stopped; inspect durable sanitized metadata. No automatic replay.')
        return 1


if __name__=='__main__':raise SystemExit(main())
