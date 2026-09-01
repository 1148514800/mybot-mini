from __future__ import annotations


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
