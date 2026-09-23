"""
                       User
                         │
                        CLI
                         │
                         ↓
                    AgentLoop ────── Tracer
                         │
             ┌───────────┴───────────┐
             │                       │
        ContextBuilder              LLM
             │                       │
      Instructions                   │
                                      ↓
                                 Tool Calling
                                      │
                               ToolRegistry
                                      │
                  ┌──────────────────┴──────────────────┐
                   ↓                                     ↓
              Native Tools                          MCP Tools
                   │                                     │
          File / Exec / Browser                       MCPTool
                                                         │
                                                   MCPManager
                                                        │
                                             stdio / Streamable HTTP
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
    asyncio.run(run_gateway())
