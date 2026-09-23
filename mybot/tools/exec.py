from __future__ import annotations

import asyncio
from pathlib import Path

from .base import Tool
from .result import ToolResult


class ExecTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace.expanduser().resolve()

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command"},
            },
            "required": ["command"],
        }

    async def execute(self, command: str, **kwargs) -> ToolResult:
        normalized_command = command.lower()
        if (
            "playwright-cli" in normalized_command
            or "@playwright/cli" in normalized_command
        ):
            return ToolResult(
                success=False,
                error=(
                    "Browser CLI commands are blocked in exec. Use the "
                    "browser_* tools, which enforce approved browser profiles."
                ),
            )
        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
            result = out.decode(errors="replace")
            if err:
                result += f"\nSTDERR:\n{err.decode(errors='replace')}"
            result = result or "(no output)"
            if proc.returncode:
                return ToolResult(
                    success=False,
                    error=(
                        f"command exited with code {proc.returncode}\n{result}"
                    )[:10000],
                    metadata={"returncode": proc.returncode},
                )
            return ToolResult(
                success=True,
                output=result[:10000],
                metadata={"returncode": proc.returncode},
            )
        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            return ToolResult(
                success=False,
                error="command timed out after 30 seconds.",
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
