from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class PendingClarification:
    clarification_id: str
    session_key: str
    question: str
    created_at: str
    origin_run_id: str | None = None
    task_id: str | None = None
    browser_mode: str | None = None
    browser_session: str | None = None
    model_tool_call_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list, repr=False)
    remaining_tool_calls: list[dict[str, Any]] = field(
        default_factory=list,
        repr=False,
    )
    browser_snapshot: str = field(default="", repr=False)
    loaded_skills: list[str] = field(default_factory=list, repr=False)
    browser_initialized: bool = False
    status: str = "pending"


class ClarificationManager:
    """In-memory, session-scoped continuation state for ordinary questions."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingClarification] = {}

    def create(
        self,
        *,
        session_key: str,
        question: str,
        origin_run_id: str | None = None,
        task_id: str | None = None,
        browser_mode: str | None = None,
        browser_session: str | None = None,
        model_tool_call_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        remaining_tool_calls: list[dict[str, Any]] | None = None,
        browser_snapshot: str = "",
        loaded_skills: list[str] | None = None,
        browser_initialized: bool = False,
    ) -> PendingClarification:
        pending = PendingClarification(
            clarification_id=uuid.uuid4().hex,
            session_key=session_key,
            question=question.strip(),
            created_at=datetime.now(UTC).isoformat(),
            origin_run_id=origin_run_id,
            task_id=task_id,
            browser_mode=browser_mode,
            browser_session=browser_session,
            model_tool_call_id=model_tool_call_id,
            messages=copy.deepcopy(messages or []),
            remaining_tool_calls=copy.deepcopy(remaining_tool_calls or []),
            browser_snapshot=browser_snapshot,
            loaded_skills=list(loaded_skills or []),
            browser_initialized=browser_initialized,
        )
        self._pending[session_key] = pending
        return pending

    def get(self, session_key: str) -> PendingClarification | None:
        return self._pending.get(session_key)

    def resolve(
        self,
        session_key: str,
        clarification_id: str | None = None,
    ) -> PendingClarification | None:
        return self._consume(session_key, clarification_id, "answered")

    def cancel(
        self,
        session_key: str,
        clarification_id: str | None = None,
    ) -> PendingClarification | None:
        return self._consume(session_key, clarification_id, "cancelled")

    def clear(self, session_key: str) -> PendingClarification | None:
        return self._pending.pop(session_key, None)

    def _consume(
        self,
        session_key: str,
        clarification_id: str | None,
        status: str,
    ) -> PendingClarification | None:
        pending = self._pending.get(session_key)
        if pending is None:
            return None
        if (
            clarification_id is not None
            and pending.clarification_id != clarification_id
        ):
            return None
        self._pending.pop(session_key, None)
        pending.status = status
        return pending
