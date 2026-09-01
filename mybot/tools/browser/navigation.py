from __future__ import annotations

from pathlib import Path

from ..result import BrowserResult
from .base import PlaywrightCliTool
from .session import MANAGED_BROWSER_SESSION, BrowserSessionManager


MANAGED_PROFILE_DIRECTORY = "managed_browser"


class BrowserOpenTool(PlaywrightCliTool):
    def __init__(
        self,
        workspace: Path,
        session_manager: BrowserSessionManager,
    ):
        super().__init__(session_manager)
        self._workspace = workspace.resolve()
        self._profile_directory = (
            self._workspace / "browser_profiles" / MANAGED_PROFILE_DIRECTORY
        ).resolve()
        if not self._profile_directory.is_relative_to(self._workspace):
            raise ValueError("managed browser profile must stay inside workspace")

    @property
    def name(self) -> str:
        return "browser_open"

    @property
    def description(self) -> str:
        return (
            "Open a separate visible Chrome with MyBot's persistent profile. "
            "Login state is retained across sessions. This is the default browser "
            "mode unless the user explicitly requests their local, current, or "
            "already-open browser."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Optional URL to open",
                    "default": "",
                },
            },
        }

    @property
    def profile_directory(self) -> Path:
        return self._profile_directory

    async def execute(self, url: str = "", **kwargs) -> BrowserResult:
        self._profile_directory.mkdir(parents=True, exist_ok=True)
        parts = [
            "playwright-cli",
            f"-s={MANAGED_BROWSER_SESSION}",
            "open",
        ]
        if url.strip():
            parts.append(url.strip())
        parts.extend(
            [
                "--browser=chrome",
                "--headed",
                f"--profile={self._profile_directory}",
            ]
        )

        return await self._run_parts(parts)


class BrowserGotoTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_goto"

    @property
    def description(self) -> str:
        return "Navigate the current page in an existing browser session to a URL."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        resolved_session = self._resolve_session(session)
        resolved_url = url.strip()
        return await self._run_parts(
            self._session_prefix(resolved_session) + ["goto", resolved_url]
        )


class BrowserTabTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_tab"

    @property
    def description(self) -> str:
        return (
            "List, create, select, or close tabs in an existing browser session. "
            "Use list/select after an action opens a new tab."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Tab operation",
                    "enum": ["list", "new", "select", "close"],
                },
                "index": {
                    "type": "integer",
                    "description": "Zero-based tab index for select or close",
                    "minimum": 0,
                },
                "url": {
                    "type": "string",
                    "description": "Optional URL for a new tab",
                    "default": "",
                },
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        index: int | None = None,
        url: str = "",
        session: str = "",
        **kwargs,
    ) -> BrowserResult:
        resolved_action = action.strip().lower()
        if resolved_action not in {"list", "new", "select", "close"}:
            raise ValueError("action must be list, new, select, or close")

        parts = self._session_prefix(session)
        if resolved_action == "list":
            parts.append("tab-list")
        elif resolved_action == "new":
            parts.append("tab-new")
            if url.strip():
                parts.append(url.strip())
        else:
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                raise ValueError(f"index is required for tab {resolved_action}")
            parts.extend([f"tab-{resolved_action}", str(index)])

        return await self._run_parts(parts)


class BrowserCloseTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_close"

    @property
    def description(self) -> str:
        return "Close the current browser session."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "session": {
                    "type": "string",
                    "description": "Browser session name",
                    "default": "",
                },
            },
        }

    async def execute(self, session: str = "", **kwargs) -> BrowserResult:
        resolved_session = self._resolve_session(session)
        result = await self._run_parts(
            self._session_prefix(resolved_session) + ["close"]
        )
        if result.success:
            self._forget_session(resolved_session)
        return result
