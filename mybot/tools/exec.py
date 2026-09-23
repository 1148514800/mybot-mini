from __future__ import annotations

import asyncio
from pathlib import Path

from .base import Tool, ToolResult


COMMAND_TIMEOUT_SECONDS = 30
MAX_OUTPUT_CHARS = 10000


class ExecTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Run a shell command inside the workspace."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "Shell command"}},
            "required": ["command"],
        }

    async def execute(self, command: str, **kwargs) -> ToolResult:
        lowered = command.lower()
        if "playwright-cli" in lowered or "@playwright/cli" in lowered:
            return ToolResult(
                success=False,
                error="running playwright-cli through exec is blocked; use the browser_* tools",
            )
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace,
            )
            out, err = await asyncio.wait_for(
                proc.communicate(), timeout=COMMAND_TIMEOUT_SECONDS
            )
            output = out.decode(errors="replace")
            if err:
                output += f"\nSTDERR:\n{err.decode(errors='replace')}"
            output = (output or "(no output)")[:MAX_OUTPUT_CHARS]
            return ToolResult(
                success=proc.returncode == 0,
                output=output,
                error=f"command exited with code {proc.returncode}" if proc.returncode else None,
                metadata={"returncode": proc.returncode},
            )
        except TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            return ToolResult(
                success=False,
                error=f"command timed out after {COMMAND_TIMEOUT_SECONDS} seconds",
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
