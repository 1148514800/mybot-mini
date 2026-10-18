"""Real sandbox/Patch/tests, disposable calculator, reactive synthetic client only."""
import asyncio
import json
from mybot.evaluation.coding_agent import evaluate, CASES


def main():
    wanted = {'single_add', 'no_retest', 'repeat_read', 'denied', 'repatch', 'fake_success'}
    report = asyncio.run(evaluate(specs=[s for s in json.loads(CASES.read_text()) if s['id'] in wanted]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['task_success'] != report['total_cases'] or report['false_verified_count']:
        raise SystemExit(1)


if __name__ == '__main__': main()
