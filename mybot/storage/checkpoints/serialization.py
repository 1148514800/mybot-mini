"""Encode checkpoint payloads and rebuild runtime waiting-state representations."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .sanitizer import sanitize_browser_state, sanitize_messages

if TYPE_CHECKING:
    from ...agent.browser_reliability import RecentBrowserTask


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
