"""Phase25: init offline/live cohort, run independent slots, audit/summarize evidence."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid

from mybot.evaluation.coding_campaign import create, run_next, summary, markdown, write_new


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('init','run','status','export'))
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--case-ids')
    p.add_argument('--live',action='store_true');p.add_argument('--confirm-api-cost',action='store_true')
    p.add_argument('--max-runs',type=int,default=1)
    a=p.parse_args()
    if a.confirm_api_cost and not a.live:p.error('cost confirmation requires live')
    if not 1<=a.max_runs<=36:p.error('max-runs must be 1..36')
    try:
        if a.action=='init':
            d=create(a.directory,rounds=a.rounds,case_ids=a.case_ids.split(',') if a.case_ids else None,live=a.live)
            print(json.dumps({'campaign_id':d['campaign_id'],'planned':len(d['slots']),'config_sha256':d['config_sha256']}))
        elif a.action=='run':
            if a.live and (not a.confirm_api_cost or not sys.stdin.isatty() or not sys.stdout.isatty()):
                p.error('Live requires explicit cost confirmation and real stdin/stdout TTY')
            for _ in range(a.max_runs):
                if asyncio.run(run_next(a.directory,live=a.live,confirm_api_cost=a.confirm_api_cost)) is None:break
        else:
            d=summary(a.directory)
            if a.action=='export':
                dest=a.directory/('summary-'+uuid.uuid4().hex);write_new(dest.with_suffix('.json'),d)
                with dest.with_suffix('.md').open('x') as f:f.write(markdown(d))
                print(str(dest))
            else:print(json.dumps(d,ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError):
        p.exit(2,'Campaign rejected; inspect durable metadata. Sensitive exception details omitted.\n')


if __name__=='__main__':main()
