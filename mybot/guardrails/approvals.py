from __future__ import annotations

import copy
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from .models import PendingApproval, PolicyResult


DEFAULT_APPROVAL_TTL_SECONDS = 600


class ApprovalIntent(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    UNKNOWN = "unknown"


APPROVAL_INPUTS = frozenset(
    {"确认", "继续", "同意", "执行", "yes", "y", "approve"}
)
REJECTION_INPUTS = frozenset(
    {"取消", "拒绝", "不要执行", "停止", "no", "n", "deny"}
)


def classify_approval_intent(value: str) -> ApprovalIntent:
    normalized = value.strip().lower().rstrip("。.!！")
    if normalized in APPROVAL_INPUTS:
        return ApprovalIntent.APPROVE
    if normalized in REJECTION_INPUTS:
        return ApprovalIntent.REJECT
    return ApprovalIntent.UNKNOWN


class ApprovalManager:
    """In-memory, session-scoped, single-use pending approval storage."""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise ValueError("approval ttl must be a positive integer")
        if ttl_seconds <= 0:
            raise ValueError("approval ttl must be greater than 0")
        self.ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._pending: dict[str, PendingApproval] = {}

    def create(
        self,
        *,
        session_key: str,
        tool_name: str,
        arguments: dict[str, Any],
        policy: PolicyResult,
        requester_sender_id: str | None = None,
        origin_run_id: str | None = None,
        browser_mode: str | None = None,
        model_tool_call_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        remaining_tool_calls: list[dict[str, Any]] | None = None,
        browser_snapshot: str = "",
        task_id: str | None = None,
        loaded_skills: list[str] | None = None,
        browser_initialized: bool = False,
        browser_state: dict[str, Any] | None = None,
    ) -> PendingApproval:
        now = self._now()
        pending = PendingApproval(
            approval_id=uuid.uuid4().hex,
            session_key=session_key,
            tool_name=tool_name,
            arguments=copy.deepcopy(arguments),
            risk_level=policy.risk_level,
            reason=policy.reason,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(seconds=self.ttl_seconds)).isoformat(),
            requester_sender_id=requester_sender_id,
            origin_run_id=origin_run_id,
            browser_mode=browser_mode,
            model_tool_call_id=model_tool_call_id,
            policy_rule=policy.rule,
            messages=copy.deepcopy(messages or []),
            remaining_tool_calls=copy.deepcopy(remaining_tool_calls or []),
            browser_snapshot=browser_snapshot,
            task_id=task_id,
            loaded_skills=list(loaded_skills or []),
            browser_initialized=browser_initialized,
            browser_state=copy.deepcopy(browser_state or {}),
            policy_metadata=copy.deepcopy(policy.metadata),
        )
        self._pending[session_key] = pending
        return pending

    def get(self, session_key: str) -> PendingApproval | None:
        return self._pending.get(session_key)

    def expire(self, session_key: str) -> PendingApproval | None:
        pending = self._pending.get(session_key)
        if pending is None:
            return None
        if self._now() < datetime.fromisoformat(pending.expires_at):
            return None
        self._pending.pop(session_key, None)
        pending.status = "expired"
        return pending

    def approve(
        self,
        session_key: str,
        approval_id: str | None = None,
        sender_id: str | None = None,
    ) -> PendingApproval | None:
        return self._consume(session_key, approval_id, sender_id, "approved")

    def reject(
        self,
        session_key: str,
        approval_id: str | None = None,
        sender_id: str | None = None,
    ) -> PendingApproval | None:
        return self._consume(session_key, approval_id, sender_id, "rejected")

    def clear(self, session_key: str) -> PendingApproval | None:
        return self._pending.pop(session_key, None)

    def _consume(
        self,
        session_key: str,
        approval_id: str | None,
        sender_id: str | None,
        status: str,
    ) -> PendingApproval | None:
        if self.expire(session_key) is not None:
            return None
        pending = self._pending.get(session_key)
        if pending is None:
            return None
        if approval_id is not None and pending.approval_id != approval_id:
            return None
        if (
            pending.requester_sender_id is not None
            and sender_id != pending.requester_sender_id
        ):
            return None
        self._pending.pop(session_key, None)
        pending.status = status
        return pending

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approval clock must return a timezone-aware datetime")
        return value
