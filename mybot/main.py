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
# from pathlib import Path
# import sys

# if __package__ in {None, ""}:
#     repo_root = Path(__file__).resolve().parent.parent
#     if str(repo_root) not in sys.path:
#         sys.path.insert(0, str(repo_root))

from mybot import run_gateway


if __name__ == "__main__":
    asyncio.run(run_gateway())
