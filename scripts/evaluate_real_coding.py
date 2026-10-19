"""Default offline: validate the benchmark/harness, never claim model ability."""
import argparse
import asyncio
import json
from pathlib import Path

from mybot.evaluation.coding_benchmark import evaluate, save_report
from mybot.evaluation.coding_live import Limits


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--live',action='store_true')
    result.add_argument('--confirm-api-cost',action='store_true')
    result.add_argument('--case-ids')
    for name in ('max_cases','repeats','max_requests','max_model_requests_per_case','max_output_tokens','seed'):
        result.add_argument('--'+name.replace('_','-'),type=int,default=getattr(Limits(),name))
    for name in ('task_timeout','total_timeout','request_timeout','judge_timeout'):
        result.add_argument('--'+name.replace('_','-'),type=float,default=getattr(Limits(),name))
    result.add_argument('--prices',type=Path)
    result.add_argument('--max-estimated-cost',type=float)
    result.add_argument('--save',action='store_true',help='Exclusive bounded metadata report; no raw transcript')
    return result


def main():
    p=parser();args=p.parse_args()
    try:
        limits=Limits(**{k:getattr(args,k) for k in Limits.__dataclass_fields__})
        if args.prices and args.prices.stat().st_size>16384: raise ValueError('price_file_too_large')
        prices=json.loads(args.prices.read_text()) if args.prices else None
        report=asyncio.run(evaluate(live=args.live,confirm_api_cost=args.confirm_api_cost,limits=limits,
            case_ids=args.case_ids,prices=prices,max_estimated_cost=args.max_estimated_cost))
        if args.save:save_report(report)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if any(v['status']!='valid' for v in report['validations']) or report['infra_error_cases'] or report['protocol_false_verified_count']:raise SystemExit(1)
    except (ValueError,OSError,TypeError):p.exit(2,'Invalid benchmark/options/configuration; no API fallback.\n')
    except Exception:p.exit(1,'Evaluation failed; sensitive details omitted.\n')


if __name__=='__main__':main()
