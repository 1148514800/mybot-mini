from __future__ import annotations

from ..result import BrowserResult
from .base import PlaywrightCliTool
from .session import LOCAL_BROWSER_SESSION


class BrowserAttachTool(PlaywrightCliTool):
    @property
    def name(self) -> str:
        return "browser_attach"

    @property
    def description(self) -> str:
        return (
            "Attach to the user's already-open local Chrome through CDP, reusing "
            "its current profile, tabs, and login state. This never launches a "
            "separate browser."
        )

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(
        self,
        **kwargs,
    ) -> BrowserResult:
        return await self._run_parts(
            [
                "playwright-cli",
                "attach",
                "--cdp=chrome",
                f"-s={LOCAL_BROWSER_SESSION}",
            ]
        )
