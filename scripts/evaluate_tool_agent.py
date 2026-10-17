"""Safe synthetic Agent evaluation; real API requests require BOTH live flags."""
import argparse
import asyncio
import json
from mybot.evaluation.tool_agent import evaluate, Limits, MODES, save_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--confirm-api-cost',action='store_true')
    parser.add_argument('--modes',default=','.join(MODES))
    for name,default in (('max-cases',12),('repeats',1),('max-requests',240),('max-output-tokens',512),('max-react-steps',16),('context-max-chars',160000),('seed',16)):
        parser.add_argument('--'+name,type=int,default=default)
    for name,default in (('task-timeout',15.0),('total-timeout',240.0),('request-timeout',10.0)):
        parser.add_argument('--'+name,type=float,default=default)
    parser.add_argument('--prices',help='Explicit local JSON price file; no built-in provider prices')
    parser.add_argument('--save',action='store_true',help='Write exclusive metadata-only report under runs/evals')
    args=parser.parse_args()
    try:
        limits=Limits(**{k:getattr(args,k) for k in Limits.__dataclass_fields__})
        prices=json.loads(open(args.prices).read()) if args.prices else None
        report=asyncio.run(evaluate(live=args.live,confirm_api_cost=args.confirm_api_cost,limits=limits,
                                   modes=args.modes.split(','),prices=prices))
        if args.save:save_report(report)
        print(json.dumps(report,ensure_ascii=False,indent=2))
    except (ValueError,OSError,json.JSONDecodeError):parser.exit(2,'Invalid evaluation options/configuration; no report generated.\n')
    except Exception:parser.exit(1,'Evaluation setup failed; details omitted to protect local configuration.\n')


if __name__=='__main__':main()
