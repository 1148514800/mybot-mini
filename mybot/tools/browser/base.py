from __future__ import annotations

import asyncio
import os
import re
import subprocess

from ..base import Tool
from ..result import BrowserResult
from .session import DEFAULT_SESSION, BrowserSessionManager


COMMAND_TIMEOUT_SECONDS = 60
MAX_OUTPUT_CHARS = 12000
SNAPSHOT_MAX_OUTPUT_CHARS = 30000
_CLI_ERROR_BLOCK = re.compile(
    r"(?ms)^### Error[ \t]*\r?\n(.*?)(?=^### [^\r\n]+[ \t]*\r?$|\Z)"
)


class PlaywrightCliTool(Tool):
    def __init__(self, session_manager: BrowserSessionManager):
        self.session_manager = session_manager

    def _resolve_session(self, session: str = "") -> str:
        return self.session_manager.resolve(session)

    def _set_active_session(self, session: str) -> None:
        self.session_manager.set_active(session)

    def _session_prefix(self, session: str) -> list[str]:
        resolved = self._resolve_session(session)
        return ["playwright-cli", f"-s={resolved}"]

    def _record_session(
        self,
        session: str,
    ) -> None:
        self._set_active_session(session)

    def _forget_session(self, session: str) -> None:
        self.session_manager.clear(session)

    def _result_context(self, parts: list[str]) -> tuple[str, str]:
        action = self.name.removeprefix("browser_")
        session = next(
            (
                part.removeprefix("-s=")
                for part in parts
                if part.startswith("-s=") and part.removeprefix("-s=")
            ),
            self._resolve_session(),
        )
        return action, session

    def _spawn_command(self, parts: list[str]) -> tuple[list[str], dict]:
        if os.name == "nt":
            kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            return ["cmd", "/c", *parts], kwargs
        return parts, {}

    def _truncate_output(self, result: str, max_output_chars: int) -> str:
        if len(result) <= max_output_chars:
            return result

        omitted = len(result) - max_output_chars
        marker = (
            f"\n\n...[output truncated; at least {omitted} characters omitted. "
            "Narrow the browser snapshot with target or a smaller depth.]"
        )
        if len(marker) >= max_output_chars:
            return marker[:max_output_chars]
        return result[: max_output_chars - len(marker)] + marker

    @staticmethod
    def _explicit_cli_error(output: str) -> str | None:
        """Return a playwright-cli Error block, excluding page console errors."""
        match = _CLI_ERROR_BLOCK.search(output)
        if not match:
            return None
        detail = match.group(1).strip()
        return detail[:2_000] or "playwright-cli reported an unspecified error"

    async def _run_parts(
        self,
        parts: list[str],
        max_output_chars: int = MAX_OUTPUT_CHARS,
    ) -> BrowserResult:
        proc = None
        action, session = self._result_context(parts)
        try:
            command, extra_kwargs = self._spawn_command(parts)
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **extra_kwargs,
            )
            out, err = await asyncio.wait_for(
                proc.communicate(), timeout=COMMAND_TIMEOUT_SECONDS
            )
            output = out.decode(errors="replace")
            if err:
                output += f"\nSTDERR:\n{err.decode(errors='replace')}"
            output = output or "(no output)"
            explicit_error = self._explicit_cli_error(output)
            output_truncated = len(output) > max_output_chars
            output = self._truncate_output(output, max_output_chars)
            metadata = {
                "exit_code": proc.returncode,
                "output_truncated": output_truncated,
            }
            if proc.returncode:
                return BrowserResult(
                    success=False,
                    action=action,
                    session=session,
                    error=f"playwright-cli exited with code {proc.returncode}",
                    output=output,
                    metadata=metadata,
                )
            if explicit_error:
                metadata["cli_error_block"] = True
                return BrowserResult(
                    success=False,
                    action=action,
                    session=session,
                    error=f"playwright-cli reported an error: {explicit_error}",
                    output=output,
                    metadata=metadata,
                )
            self._record_session(session)
            return BrowserResult(
                success=True,
                action=action,
                session=session,
                output=output,
                metadata=metadata,
            )
        except FileNotFoundError:
            return BrowserResult(
                success=False,
                action=action,
                session=session,
                error=(
                    "playwright-cli was not found in PATH. Install Node.js and "
                    "playwright-cli in this environment first."
                ),
                metadata={"missing_cli": True},
            )
        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.communicate()
            return BrowserResult(
                success=False,
                action=action,
                session=session,
                error=(
                    "playwright-cli timed out after "
                    f"{COMMAND_TIMEOUT_SECONDS} seconds."
                ),
                metadata={"timed_out": True},
            )
        except Exception as exc:
            return BrowserResult(
                success=False,
                action=action,
                session=session,
                error=f"{type(exc).__name__}: {exc}",
            )
