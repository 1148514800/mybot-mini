from __future__ import annotations

from typing import Any

from ..guardrails import PendingApproval, PendingClarification, RiskLevel
from .browser_reliability import RecentBrowserTask


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
