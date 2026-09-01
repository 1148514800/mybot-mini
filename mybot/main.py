"""Compatibility entrypoint for the mini agent gateway."""

from __future__ import annotations

import asyncio
# from pathlib import Path
# import sys

# if __package__ in {None, ""}:
#     repo_root = Path(__file__).resolve().parent.parent
#     if str(repo_root) not in sys.path:
#         sys.path.insert(0, str(repo_root))

from mybot import run_gateway


if __name__ == "__main__":
    asyncio.run(run_gateway())
