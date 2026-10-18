"""Disposable offline coding evaluation; no live/API option or third-party MCP."""
import argparse
import asyncio
import json
from mybot.evaluation.coding_agent import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('macos_readonly', 'host_confirm'), default='macos_readonly')
    args = parser.parse_args()
    report = asyncio.run(evaluate(mode=args.mode))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['task_success'] != report['total_cases'] or report['false_verified_count']:
        raise SystemExit(1)


if __name__ == '__main__': main()
