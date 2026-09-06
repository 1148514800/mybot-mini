"""Encode checkpoint payloads and rebuild runtime waiting-state representations."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...guardrails import PendingApproval, PendingClarification, RiskLevel
from ...tracing import REDACTED, redact_text
from .sanitizer import (
    sanitize_approval_snapshot,
    sanitize_browser_state,
    sanitize_messages,
    sanitize_policy_metadata,
    sanitize_tool_arguments,
    sanitize_tool_calls,
)

if TYPE_CHECKING:
    from ...agent.browser_reliability import RecentBrowserTask

_ALWAYS_NON_RESUMABLE_TOOLS = frozenset(
    {"browser_type", "memory_write", "write_file"}
)


def serialize_approval(pending: PendingApproval) -> dict[str, Any]:
    safe_arguments = sanitize_tool_arguments(
        pending.tool_name,
        pending.arguments,
    )
    snapshot = sanitize_approval_snapshot(pending)
    resumable = (
        pending.resumable
        and pending.tool_name not in _ALWAYS_NON_RESUMABLE_TOOLS
        and safe_arguments == pending.arguments
        and REDACTED not in snapshot
    )
    return {
        "approval_id": pending.approval_id,
        "session_key": pending.session_key,
        "tool_name": pending.tool_name,
        "arguments": safe_arguments,
        "risk_level": pending.risk_level.value,
        "reason": redact_text(pending.reason),
        "created_at": pending.created_at,
        "expires_at": pending.expires_at,
        "requester_sender_id": pending.requester_sender_id,
        "origin_run_id": pending.origin_run_id,
        "browser_mode": pending.browser_mode,
        "model_tool_call_id": pending.model_tool_call_id,
        "policy_rule": pending.policy_rule,
        "messages": sanitize_messages(pending.messages),
        "remaining_tool_calls": sanitize_tool_calls(
            pending.remaining_tool_calls
        ),
        "browser_snapshot": snapshot,
        "task_id": pending.task_id,
        "loaded_skills": list(pending.loaded_skills),
        "browser_initialized": False,
        "browser_state": sanitize_browser_state(
            pending.browser_state,
            snapshot=snapshot,
        ),
        "policy_metadata": sanitize_policy_metadata(
            pending.policy_metadata,
            snapshot,
        ),
        "resumable": resumable,
        "non_resumable_reason": (
            None if resumable else "sensitive_arguments"
        ),
    }


def serialize_clarification(
    pending: PendingClarification,
) -> dict[str, Any]:
    return {
        "clarification_id": pending.clarification_id,
        "session_key": pending.session_key,
        "question": redact_text(pending.question),
        "created_at": pending.created_at,
        "requester_sender_id": pending.requester_sender_id,
        "origin_run_id": pending.origin_run_id,
        "task_id": pending.task_id,
        "browser_mode": pending.browser_mode,
        "browser_session": pending.browser_session,
        "model_tool_call_id": pending.model_tool_call_id,
        "messages": sanitize_messages(pending.messages),
        "remaining_tool_calls": sanitize_tool_calls(
            pending.remaining_tool_calls
        ),
        "browser_snapshot": "",
        "loaded_skills": list(pending.loaded_skills),
        "browser_initialized": False,
        "browser_state": sanitize_browser_state(
            pending.browser_state
        ),
    }


def serialize_recent(
    task: RecentBrowserTask,
    expires_at: str,
) -> dict[str, Any]:
    return {
        "session_key": task.session_key,
        "task_id": task.task_id,
        "origin_run_id": task.origin_run_id,
        "browser_mode": task.browser_mode,
        "messages": sanitize_messages(task.messages),
        "browser_snapshot": "",
        "loaded_skills": list(task.loaded_skills),
        "browser_initialized": False,
        "browser_state": sanitize_browser_state(task.browser_state),
        "expires_at": expires_at,
    }


def recent_recovery_payload(
    payload: dict[str, Any], session_key: str, expires_at: str,
) -> dict[str, Any]:
    state = dict(payload.get("browser_state", {}))
    state["latest_snapshot"] = ""
    state["browser_initialized"] = False
    return {
        "session_key": session_key,
        "task_id": str(payload["task_id"]),
        "origin_run_id": str(payload["origin_run_id"]),
        "browser_mode": str(payload["browser_mode"]),
        "messages": list(payload.get("messages", [])),
        "browser_snapshot": "",
        "loaded_skills": list(payload.get("loaded_skills", [])),
        "browser_initialized": False,
        "browser_state": state,
        "expires_at": expires_at,
        "recovered_from_checkpoint": True,
    }


def approval_from_checkpoint(payload: dict[str, Any]) -> PendingApproval:
    return PendingApproval(
        approval_id=str(payload["approval_id"]),
        session_key=str(payload["session_key"]),
        tool_name=str(payload["tool_name"]),
        arguments=dict(payload["arguments"]),
        risk_level=RiskLevel(str(payload["risk_level"])),
        reason=str(payload["reason"]),
        created_at=str(payload["created_at"]),
        expires_at=str(payload["expires_at"]),
        requester_sender_id=payload.get("requester_sender_id"),
        origin_run_id=payload.get("origin_run_id"),
        browser_mode=payload.get("browser_mode"),
        model_tool_call_id=payload.get("model_tool_call_id"),
        policy_rule=payload.get("policy_rule"),
        messages=list(payload.get("messages", [])),
        remaining_tool_calls=list(payload.get("remaining_tool_calls", [])),
        browser_snapshot=str(payload.get("browser_snapshot", "")),
        task_id=payload.get("task_id"),
        loaded_skills=list(payload.get("loaded_skills", [])),
        browser_initialized=bool(payload.get("browser_initialized", False)),
        browser_state=dict(payload.get("browser_state", {})),
        policy_metadata=dict(payload.get("policy_metadata", {})),
        resumable=bool(payload.get("resumable", False)),
        non_resumable_reason=payload.get("non_resumable_reason"),
        recovered_from_checkpoint=True,
    )


def clarification_from_checkpoint(
    payload: dict[str, Any],
) -> PendingClarification:
    return PendingClarification(
        clarification_id=str(payload["clarification_id"]),
        session_key=str(payload["session_key"]),
        question=str(payload["question"]),
        created_at=str(payload["created_at"]),
        requester_sender_id=payload.get("requester_sender_id"),
        origin_run_id=payload.get("origin_run_id"),
        task_id=payload.get("task_id"),
        browser_mode=payload.get("browser_mode"),
        browser_session=payload.get("browser_session"),
        model_tool_call_id=payload.get("model_tool_call_id"),
        messages=list(payload.get("messages", [])),
        remaining_tool_calls=list(payload.get("remaining_tool_calls", [])),
        browser_snapshot="",
        loaded_skills=list(payload.get("loaded_skills", [])),
        browser_initialized=False,
        browser_state=dict(payload.get("browser_state", {})),
        recovered_from_checkpoint=True,
    )


def recent_task_from_checkpoint(payload: dict[str, Any]) -> RecentBrowserTask:
    # Defer the runtime model import: agent.__init__ also loads orchestration.
    from ...agent.browser_reliability import RecentBrowserTask

    return RecentBrowserTask(
        session_key=str(payload["session_key"]),
        task_id=str(payload["task_id"]),
        origin_run_id=str(payload["origin_run_id"]),
        browser_mode=str(payload["browser_mode"]),
        messages=list(payload.get("messages", [])),
        browser_snapshot="",
        loaded_skills=list(payload.get("loaded_skills", [])),
        browser_initialized=False,
        browser_state=dict(payload.get("browser_state", {})),
        expires_at=payload.get("expires_at"),
        recovered_from_checkpoint=True,
    )
