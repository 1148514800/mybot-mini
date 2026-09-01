from __future__ import annotations

import asyncio

from .base import Tool


class ExecTool(Tool):
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

    async def execute(self, command: str, **kwargs) -> str:
        normalized_command = command.lower()
        if (
            "playwright-cli" in normalized_command
            or "@playwright/cli" in normalized_command
        ):
            return (
                "Error: Browser CLI commands are blocked in exec. Use the "
                "browser_* tools, which enforce approved browser profiles."
            )

        for bad in ["rm -rf", "mkfs", "dd if=", "shutdown"]:
            if bad in normalized_command:
                return f"Error: Blocked ({bad})"

        proc = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
            result = out.decode(errors="replace")
            if err:
                result += f"\nSTDERR:\n{err.decode(errors='replace')}"
            result = result or "(no output)"
            if proc.returncode:
                return f"Error: command exited with code {proc.returncode}\n{result}"[:10000]
            return result[:10000]
        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            return "Error: command timed out after 30 seconds."
        except Exception as exc:
            return f"Error: {exc}"
