"""Offline ranking only; no real model or MCP connections."""
import json
from mybot.evaluation.tool_retrieval import evaluate


def main(): print(json.dumps(evaluate(),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
