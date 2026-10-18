"""Offline Git Workflow evaluation, synthetic temporary repositories only."""
import asyncio
import json
from mybot.evaluation.git_workflow import evaluate


def main():
    report=asyncio.run(evaluate())
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if (report['task_success']!=report['total_cases'] or report['false_owned_changes_count']
            or report['unintended_file_changes_count']):raise SystemExit(1)


if __name__=='__main__':main()
