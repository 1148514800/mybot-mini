"""Dynamic synthetic calculator: real Patch/sandbox, human-style review and Undo."""
import asyncio
import json
from mybot.evaluation.git_workflow import evaluate, CASES


def main():
    wanted={'dirty','external_edit','denied'}
    report=asyncio.run(evaluate([c for c in json.loads(CASES.read_text()) if c['id'] in wanted]))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['task_success']!=report['total_cases'] or report['false_owned_changes_count'] or report['unintended_file_changes_count']:
        raise SystemExit(1)


if __name__=='__main__':main()
