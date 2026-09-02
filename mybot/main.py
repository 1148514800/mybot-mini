"""
                       User
                         │
               ┌─────────┴─────────┐
               │                   │
              CLI                Feishu
               │                   │
               └─────────┬─────────┘
                         │
                    MessageBus
                         │
                         ↓
                    AgentLoop
                         │
             ┌───────────┴───────────┐
             │                       │
        ContextBuilder              LLM
             │                       │
      ┌──────┼──────┐                │
      │      │      │                │
Instructions Skills Memory           │
                                     ↓
                                Tool Calling
                                     │
                                ToolPolicy
                                     │
                           ALLOW / CONFIRM / BLOCK
                                     │
                               ToolRegistry
                                     │
                  ┌──────────────────┴──────────────────┐
                  ↓                                     ↓
             Native Tools                          MCP Tools
                  │                                     │
          File / Exec / Memory / Browser         MCPToolAdapter
                                                        │
                                               MCPClientManager
                                                        │
                                             stdio / Streamable HTTP

                     AgentLoop
                         │
                         ↓
                      Tracer
                         │
          ┌──────────────┼───────────────┐
          ↓              ↓               ↓
        Run            Step         LLM / Tool Call
          │
          ↓
     JSON / Replay
          │
          ↓
        Evals
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

if __package__ in {None, ""}:
    # Running ``python mybot/main.py`` puts ``mybot/`` at sys.path[0].  That
    # makes the internal ``mybot/mcp`` package shadow the third-party ``mcp``
    # SDK.  Remove the package directory as a top-level import root and import
    # the application through the repository root instead.
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
