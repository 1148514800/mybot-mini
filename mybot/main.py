"""
User → CLI → AgentLoop → LLM
                    ↓
               ToolRegistry
                    ↓
             read_file / apply_patch
"""


from __future__ import annotations

import asyncio
from pathlib import Path
import sys

if __package__ in {None, ""}:
    # Running ``python mybot/main.py`` puts ``mybot/`` on sys.path, which makes
    # ``mybot/mcp.py`` shadow the third-party ``mcp`` SDK.  Import through the
    # repository root instead.
    package_dir = Path(__file__).resolve().parent
    repo_root = package_dir.parent
    cleaned_path: list[str] = []
    for entry in sys.path:
        try:
            resolved = Path(entry or ".").resolve()
        except (OSError, RuntimeError):
            cleaned_path.append(entry)
            continue
        if resolved in {package_dir, repo_root}:
            continue
        cleaned_path.append(entry)
    sys.path[:] = [str(repo_root), *cleaned_path]

from mybot import run_gateway


if __name__ == "__main__":
    import argparse
    import json
    from mybot.config import load_config, ConfigError
    parser = argparse.ArgumentParser(description='mybot-mini CLI')
    parser.add_argument('--workspace')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.check or args.workspace is not None:
            from mybot.web.launch import prepare_launch
            config, _, report = prepare_launch(args.workspace)
        else:
            config = load_config()
        if args.check:
            print(json.dumps(report, ensure_ascii=False))
        else:
            asyncio.run(run_gateway(config))
    except ConfigError as exc:
        print(json.dumps(exc.result, ensure_ascii=False))
        raise SystemExit(2) from None
