from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

MANAGED_BROWSER_SESSION = "managed_browser"
LOCAL_BROWSER_SESSION = "local_browser"
DEFAULT_SESSION = MANAGED_BROWSER_SESSION


class BrowserSessionManager:
    """Owns browser session selection for one assembled tool registry."""

    def __init__(self, default_session: str = DEFAULT_SESSION):
        normalized_default = default_session.strip()
        if not normalized_default:
            raise ValueError("default_session must not be empty")
        self._default_session = normalized_default
        self._active_session: str | None = None

    @property
    def default_session(self) -> str:
        return self._default_session

    @property
    def active_session(self) -> str:
        return self._active_session or self._default_session

    def resolve(self, session: str = "") -> str:
        return session.strip() or self.active_session

    def set_active(self, session: str) -> str:
        resolved = session.strip() or self._default_session
        self._active_session = resolved
        return resolved

    def clear(self, session: str = "") -> None:
        if not session.strip() or self.resolve(session) == self.active_session:
            self._active_session = None


@dataclass(frozen=True, slots=True)
class BrowserLease:
    owner_session_key: str
    owner_task_id: str | None = None
    browser_mode: str | None = None
    acquired_at: str = ""


class BrowserOwnershipManager:
    """Process-local exclusive lease for the shared Playwright resource."""

    def __init__(self) -> None:
        self._lease: BrowserLease | None = None
        self._lock = asyncio.Lock()

    @property
    def lease(self) -> BrowserLease | None:
        return self._lease

    async def authorize(
        self,
        session_key: str,
        *,
        entry: bool = False,
        browser_mode: str | None = None,
        task_id: str | None = None,
    ) -> tuple[bool, bool]:
        """Return (allowed, newly_acquired), atomically claiming entry calls."""
        requester = session_key.strip()
        if not requester:
            return False, False
        async with self._lock:
            if self._lease is not None:
                return self._lease.owner_session_key == requester, False
            if not entry:
                return False, False
            self._lease = BrowserLease(
                owner_session_key=requester,
                owner_task_id=task_id,
                browser_mode=browser_mode,
                acquired_at=datetime.now(UTC).isoformat(),
            )
            return True, True

    async def release_if_owner(self, session_key: str) -> bool:
        requester = session_key.strip()
        if not requester:
            return False
        async with self._lock:
            if self._lease is None or self._lease.owner_session_key != requester:
                return False
            self._lease = None
            return True

    async def release_claim(self, session_key: str) -> bool:
        return await self.release_if_owner(session_key)
