"""Run with: uv run python -m scripts.eval_agent [--live]."""
import argparse
import asyncio
from pathlib import Path

from mybot.evaluation.runner import evaluate, save_report
from mybot.evaluation.history import analyze_report


def parser():
    p = argparse.ArgumentParser(description='Isolated Agent evaluation. Offline scores test mechanisms only.')
    p.add_argument('--case-ids',help='Comma-separated unique case IDs; selects in the given order.')
    p.add_argument('--groups',default='off,auto',help='Comma-separated unique groups: off,auto,guided.')
    p.add_argument('--analyze-report',type=Path,help='Read-only reinterpretation of a Phase 8/9 JSON report; no API.')
    p.add_argument('--live',action='store_true',help='Explicitly call the configured real API; may incur charges.')
    p.add_argument('--max-cases',type=int,default=10,help='Maximum distinct tasks (each tested in both groups).')
    p.add_argument('--max-requests',type=int,default=200,help='Global API/model request budget across all cases/groups/repeats.')
    p.add_argument('--timeout',type=float,default=30,help='Whole case timeout in seconds.')
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--output',type=Path,default=None,help='Report directory; synthetic metadata only.')
    return p


def main():
    args = parser().parse_args()
    if args.analyze_report and args.live:
        raise SystemExit('--analyze-report cannot be combined with --live')
    if args.live:
        print('LIVE: 将调用配置中的真实模型 API，可能产生费用。使用隔离工作区，不使用真实聊天历史。')
    elif not args.analyze_report:
        print('OFFLINE: 固定模拟响应，仅验证评测机制，不代表真实模型能力。')
    try:
        report = analyze_report(args.analyze_report) if args.analyze_report else asyncio.run(
            evaluate(live=args.live,max_cases=args.max_cases,max_requests=args.max_requests,
                     timeout=args.timeout,repeats=args.repeats,case_ids=args.case_ids,groups=args.groups))
        path = (save_report(report,args.output) if args.output else None) if args.analyze_report else (save_report(report,args.output) if args.output else save_report(report))
    except (ValueError, RuntimeError) as exc:
        # Config/provider errors may include private data; show type only.
        raise SystemExit(f'Evaluation setup failed ({type(exc).__name__}); check configuration and limits.') from None
    for name, stats in report['overall'].items():
        print(f"{name}: tasks={stats['task_success_count']}/{stats['cases']}; clean={stats['process_clean_count']}/{stats['cases']}; instructions={stats['instruction_followed_count']}/{stats['cases']}; strict={stats['strict_pass_count']}/{stats['cases']}; skills={stats['skill_selections']}; tools={stats['tool_calls']}; requests={stats['llm_requests']}")
    print(f'Report: {path}' if path else 'Read-only analysis; original report unchanged.')


if __name__ == '__main__':
    main()
