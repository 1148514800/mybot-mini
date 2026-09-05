from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from ..tracing import (
    REDACTED,
    redact_mapping,
    redact_text,
    redact_tool_arguments,
    redact_tool_text,
)


CHECKPOINT_SCHEMA_VERSION = 1
DEFAULT_RECENT_TASK_TTL_SECONDS = 86_400
CHECKPOINT_DIRECTORY = "checkpoints"
CHECKPOINT_FILENAME = "active_tasks.sqlite3"

_ACTIVE_KINDS = frozenset({"approval", "clarification", "verification"})
_ALWAYS_NON_RESUMABLE_TOOLS = frozenset(
    {"browser_type", "memory_write", "write_file"}
)
_PAGE_URL_PATTERN = re.compile(r"(?m)^- Page URL:\s*(.+?)\s*$")
_SENSITIVE_ARGUMENT_TEXT_PATTERN = re.compile(
    r"(?i)(?:\b(?:password|passwd|token|api[_-]?key|apikey|authorization|"
    r"cookie|secret)\b|\bbearer\s+\S+)"
)


@dataclass(slots=True)
class RecoveredActiveCheckpoint:
    kind: str
    task_state: dict[str, Any]
    payload: dict[str, Any]


class ActiveTaskCheckpointStore:
    """Versioned SQLite storage for resumable waiting-state checkpoints."""

    def __init__(
        self,
        workspace: Path,
        *,
        enabled: bool = True,
        recent_task_ttl_seconds: int = DEFAULT_RECENT_TASK_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.recent_task_ttl_seconds = int(recent_task_ttl_seconds)
        if self.recent_task_ttl_seconds <= 0:
            raise ValueError("recent task checkpoint TTL must be positive")
        self._clock = clock or (lambda: datetime.now(UTC))
        self.path = Path(workspace).expanduser().resolve() / (
            f"{CHECKPOINT_DIRECTORY}/{CHECKPOINT_FILENAME}"
        )
        self.last_error: str | None = None
        self._available = False
        if self.enabled:
            self._initialize()

    @property
    def available(self) -> bool:
        return self.enabled and self._available

    def save_approval(
        self,
        task_state: Any,
        pending: Any,
    ) -> None:
        payload = self._serialize_approval(pending)
        self._save_active(
            task_state,
            "approval",
            payload,
            expires_at=pending.expires_at,
        )

    def save_clarification(
        self,
        task_state: Any,
        pending: Any,
    ) -> None:
        self._save_active(
            task_state,
            "clarification",
            self._serialize_clarification(pending),
        )

    def save_verification(self, task_state: Any) -> None:
        self._save_active(task_state, "verification", {})

    def save_recent(self, task: Any) -> None:
        if not self.available:
            return
        expires_at = task.expires_at or self._after(
            self.recent_task_ttl_seconds
        ).isoformat()
        document = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "kind": "recent_browser_task",
            "payload": self._serialize_recent(task, expires_at),
        }
        try:
            serialized = self._json_dump(document)
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO recent_browser_tasks(
                        session_key, schema_version, task_id, payload_json,
                        updated_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_key) DO UPDATE SET
                        schema_version=excluded.schema_version,
                        task_id=excluded.task_id,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at,
                        expires_at=excluded.expires_at
                    """,
                    (
                        task.session_key,
                        CHECKPOINT_SCHEMA_VERSION,
                        task.task_id,
                        serialized,
                        self._now().isoformat(),
                        expires_at,
                    ),
                )
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            self._record_error(exc)

    def load_active(self) -> list[RecoveredActiveCheckpoint]:
        if not self.available:
            return []
        recovered: list[RecoveredActiveCheckpoint] = []
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT session_key, schema_version, task_id, kind, "
                    "payload_json, resumable, expires_at FROM active_tasks"
                ).fetchall()
        except sqlite3.Error as exc:
            self._record_error(exc)
            return []
        for row in rows:
            session_key = str(row["session_key"])
            try:
                if int(row["schema_version"]) != CHECKPOINT_SCHEMA_VERSION:
                    raise ValueError("unsupported active checkpoint schema")
                expires_at = row["expires_at"]
                if expires_at and self._parse_time(str(expires_at)) <= self._now():
                    self.clear_active(session_key)
                    continue
                document = json.loads(str(row["payload_json"]))
                item = self._deserialize_active(document, session_key)
                if item.kind != str(row["kind"]):
                    raise ValueError("active checkpoint kind mismatch")
                if str(item.task_state.get("task_id", "")) != str(
                    row["task_id"]
                ):
                    raise ValueError("active checkpoint task mismatch")
                if item.kind == "approval" and bool(
                    item.payload.get("resumable", False)
                ) != bool(row["resumable"]):
                    raise ValueError("approval resumability mismatch")
                if item.kind == "approval" and str(
                    item.payload.get("expires_at", "")
                ) != str(expires_at or ""):
                    raise ValueError("approval expiry mismatch")
                if item.kind in {"approval", "clarification"} and (
                    item.payload.get("requester_sender_id")
                    != item.task_state.get("requester_sender_id")
                ):
                    raise ValueError("checkpoint requester mismatch")
                recovered.append(item)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.clear_active(session_key)
        return recovered

    def load_recent(self) -> list[dict[str, Any]]:
        if not self.available:
            return []
        recovered: list[dict[str, Any]] = []
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT session_key, schema_version, task_id, payload_json, "
                    "expires_at FROM recent_browser_tasks"
                ).fetchall()
        except sqlite3.Error as exc:
            self._record_error(exc)
            return []
        for row in rows:
            session_key = str(row["session_key"])
            try:
                if int(row["schema_version"]) != CHECKPOINT_SCHEMA_VERSION:
                    raise ValueError("unsupported recent checkpoint schema")
                expires_at = str(row["expires_at"])
                if self._parse_time(expires_at) <= self._now():
                    self.clear_recent(session_key)
                    continue
                document = json.loads(str(row["payload_json"]))
                item = self._deserialize_recent(
                    document,
                    session_key,
                    expires_at,
                )
                if item["task_id"] != str(row["task_id"]):
                    raise ValueError("recent checkpoint task mismatch")
                recovered.append(item)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.clear_recent(session_key)
        return recovered

    def clear_active(self, session_key: str) -> None:
        self._delete("active_tasks", session_key)

    def clear_recent(self, session_key: str) -> None:
        self._delete("recent_browser_tasks", session_key)

    def active_count(self) -> int:
        return self._count("active_tasks")

    def recent_count(self) -> int:
        return self._count("recent_browser_tasks")

    def _initialize(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS checkpoint_metadata ("
                    "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                existing = connection.execute(
                    "SELECT value FROM checkpoint_metadata WHERE key='schema_version'"
                ).fetchone()
                if existing is not None and int(existing["value"]) != (
                    CHECKPOINT_SCHEMA_VERSION
                ):
                    raise ValueError("unsupported checkpoint database schema")
                connection.execute(
                    "INSERT OR IGNORE INTO checkpoint_metadata(key, value) "
                    "VALUES ('schema_version', ?)",
                    (str(CHECKPOINT_SCHEMA_VERSION),),
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS active_tasks (
                        session_key TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL,
                        task_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        resumable INTEGER NOT NULL,
                        updated_at TEXT NOT NULL,
                        expires_at TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS recent_browser_tasks (
                        session_key TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL,
                        task_id TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                    """
                )
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self._available = True
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            self._record_error(exc)

    def _save_active(
        self,
        task_state: Any,
        kind: str,
        payload: dict[str, Any],
        *,
        expires_at: str | None = None,
    ) -> None:
        if not self.available or kind not in _ACTIVE_KINDS:
            return
        document = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "kind": kind,
            "task_state": task_state.to_dict(),
            "payload": payload,
        }
        resumable = bool(payload.get("resumable", True))
        try:
            serialized = self._json_dump(document)
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO active_tasks(
                        session_key, schema_version, task_id, kind,
                        payload_json, resumable, updated_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_key) DO UPDATE SET
                        schema_version=excluded.schema_version,
                        task_id=excluded.task_id,
                        kind=excluded.kind,
                        payload_json=excluded.payload_json,
                        resumable=excluded.resumable,
                        updated_at=excluded.updated_at,
                        expires_at=excluded.expires_at
                    """,
                    (
                        task_state.session_key,
                        CHECKPOINT_SCHEMA_VERSION,
                        task_state.task_id,
                        kind,
                        serialized,
                        int(resumable),
                        self._now().isoformat(),
                        expires_at,
                    ),
                )
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            self._record_error(exc)

    def _serialize_approval(self, pending: Any) -> dict[str, Any]:
        safe_arguments = self._safe_tool_arguments(
            pending.tool_name,
            pending.arguments,
        )
        snapshot = self._approval_snapshot(pending)
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
            "messages": self._sanitize_messages(pending.messages),
            "remaining_tool_calls": self._sanitize_tool_calls(
                pending.remaining_tool_calls
            ),
            "browser_snapshot": snapshot,
            "task_id": pending.task_id,
            "loaded_skills": list(pending.loaded_skills),
            "browser_initialized": False,
            "browser_state": self._sanitize_browser_state(
                pending.browser_state,
                snapshot=snapshot,
            ),
            "policy_metadata": self._sanitize_policy_metadata(
                pending.policy_metadata,
                snapshot,
            ),
            "resumable": resumable,
            "non_resumable_reason": (
                None if resumable else "sensitive_arguments"
            ),
        }

    def _serialize_clarification(
        self,
        pending: Any,
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
            "messages": self._sanitize_messages(pending.messages),
            "remaining_tool_calls": self._sanitize_tool_calls(
                pending.remaining_tool_calls
            ),
            "browser_snapshot": "",
            "loaded_skills": list(pending.loaded_skills),
            "browser_initialized": False,
            "browser_state": self._sanitize_browser_state(
                pending.browser_state
            ),
        }

    def _serialize_recent(
        self,
        task: Any,
        expires_at: str,
    ) -> dict[str, Any]:
        return {
            "session_key": task.session_key,
            "task_id": task.task_id,
            "origin_run_id": task.origin_run_id,
            "browser_mode": task.browser_mode,
            "messages": self._sanitize_messages(task.messages),
            "browser_snapshot": "",
            "loaded_skills": list(task.loaded_skills),
            "browser_initialized": False,
            "browser_state": self._sanitize_browser_state(task.browser_state),
            "expires_at": expires_at,
        }

    def _deserialize_active(
        self,
        document: dict[str, Any],
        session_key: str,
    ) -> RecoveredActiveCheckpoint:
        self._validate_document(document)
        kind = str(document["kind"])
        if kind not in _ACTIVE_KINDS:
            raise ValueError("unsupported active checkpoint kind")
        task_state = document["task_state"]
        if not isinstance(task_state, dict):
            raise ValueError("checkpoint task state must be an object")
        if str(task_state.get("session_key", "")) != session_key:
            raise ValueError("checkpoint session mismatch")
        expected_status = {
            "approval": "waiting_approval",
            "clarification": "waiting_clarification",
            "verification": "waiting_verification",
        }[kind]
        if str(task_state.get("status", "")) != expected_status:
            raise ValueError("checkpoint task status mismatch")
        payload = document["payload"]
        if not isinstance(payload, dict):
            raise ValueError("checkpoint payload must be an object")
        if kind == "approval":
            if str(payload.get("session_key", "")) != session_key or str(
                payload.get("task_id", "")
            ) != str(task_state.get("task_id", "")):
                raise ValueError("approval checkpoint identity mismatch")
            return RecoveredActiveCheckpoint(kind, task_state, payload)
        if kind == "clarification":
            if str(payload.get("session_key", "")) != session_key or str(
                payload.get("task_id", "")
            ) != str(task_state.get("task_id", "")):
                raise ValueError("clarification checkpoint identity mismatch")
        return RecoveredActiveCheckpoint(kind, task_state, payload)

    def _deserialize_recent(
        self,
        document: dict[str, Any],
        session_key: str,
        expires_at: str,
    ) -> dict[str, Any]:
        self._validate_document(document, kind="recent_browser_task")
        payload = document["payload"]
        if not isinstance(payload, dict):
            raise ValueError("recent checkpoint payload must be an object")
        if str(payload["session_key"]) != session_key:
            raise ValueError("recent checkpoint session mismatch")
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

    @staticmethod
    def _validate_document(
        document: dict[str, Any],
        *,
        kind: str | None = None,
    ) -> None:
        if not isinstance(document, dict):
            raise ValueError("checkpoint document must be an object")
        if int(document.get("schema_version", -1)) != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError("unsupported checkpoint payload schema")
        if kind is not None and document.get("kind") != kind:
            raise ValueError("checkpoint kind mismatch")

    @classmethod
    def _approval_snapshot(cls, pending: Any) -> str:
        url_match = _PAGE_URL_PATTERN.search(pending.browser_snapshot or "")
        lines = (
            [
                "- Page URL: "
                + cls._scrub_sensitive_argument_text(
                    url_match.group(1).strip()
                )
            ]
            if url_match
            else []
        )
        target = str(pending.arguments.get("target", "")).strip()
        if target and re.fullmatch(r"e\d+", target, re.I):
            ref_pattern = re.compile(
                rf"\[ref\s*=\s*['\"]?{re.escape(target)}['\"]?\]",
                re.I,
            )
            for line in pending.browser_snapshot.splitlines():
                if ref_pattern.search(line):
                    lines.append(
                        redact_tool_text(
                            pending.tool_name,
                            line,
                            pending.arguments,
                        )
                    )
                    break
        return "\n".join(lines)

    @classmethod
    def _sanitize_policy_metadata(
        cls,
        metadata: dict[str, Any],
        snapshot: str,
    ) -> dict[str, Any]:
        url_match = _PAGE_URL_PATTERN.search(snapshot)
        safe: dict[str, Any] = {}
        if url_match:
            safe["current_url"] = cls._scrub_sensitive_argument_text(
                url_match.group(1).strip()
            )
        target_text = metadata.get("target_text")
        if target_text:
            safe["target_text"] = cls._scrub_sensitive_argument_text(
                str(target_text)
            )[:500]
        return safe

    @classmethod
    def _sanitize_messages(
        cls,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        sensitive_values = cls._sensitive_values_from_messages(messages)
        call_context: dict[str, tuple[str, dict[str, Any]]] = {}
        sanitized: list[dict[str, Any]] = []
        for raw_message in messages:
            message = redact_mapping(copy.deepcopy(raw_message))
            calls = message.get("tool_calls")
            if isinstance(calls, list):
                message["tool_calls"] = cls._sanitize_tool_calls(
                    calls,
                    call_context,
                )
            content = message.get("content")
            if isinstance(content, str):
                call_id = str(message.get("tool_call_id", ""))
                tool_name, arguments = call_context.get(call_id, ("", {}))
                if tool_name.startswith("browser_"):
                    message["content"] = (
                        "[stale browser result omitted from restart checkpoint; "
                        "read fresh browser state before acting]"
                    )
                elif tool_name:
                    message["content"] = redact_tool_text(
                        tool_name,
                        content,
                        arguments,
                    )
                else:
                    message["content"] = redact_text(content)
                for sensitive_value in sensitive_values:
                    message["content"] = message["content"].replace(
                        sensitive_value,
                        REDACTED,
                    )
            sanitized.append(message)
        return sanitized

    @classmethod
    def _sensitive_values_from_messages(
        cls,
        messages: list[dict[str, Any]],
    ) -> set[str]:
        values: set[str] = set()
        for message in messages:
            calls = message.get("tool_calls", [])
            if not isinstance(calls, list):
                continue
            for call in calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function", {})
                if not isinstance(function, dict):
                    continue
                name = str(function.get("name", ""))
                arguments = function.get("arguments", {})
                try:
                    parsed = (
                        json.loads(arguments)
                        if isinstance(arguments, str)
                        else arguments
                    )
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(parsed, dict):
                    safe = cls._safe_tool_arguments(name, parsed)
                    cls._collect_redacted_values(parsed, safe, values)
        return values

    @classmethod
    def _collect_redacted_values(
        cls,
        original: Any,
        redacted: Any,
        values: set[str],
    ) -> None:
        if redacted == REDACTED and isinstance(original, str) and original:
            values.add(original)
            return
        if isinstance(original, dict) and isinstance(redacted, dict):
            for key, value in original.items():
                if key in redacted:
                    cls._collect_redacted_values(value, redacted[key], values)
        elif isinstance(original, (list, tuple)) and isinstance(redacted, list):
            for value, safe_value in zip(original, redacted):
                cls._collect_redacted_values(value, safe_value, values)

    @classmethod
    def _sanitize_tool_calls(
        cls,
        calls: list[dict[str, Any]],
        context: dict[str, tuple[str, dict[str, Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        for raw_call in calls:
            call = redact_mapping(copy.deepcopy(raw_call))
            function = call.get("function")
            if not isinstance(function, dict):
                sanitized.append(call)
                continue
            name = str(function.get("name", ""))
            raw_arguments = function.get("arguments", {})
            was_string = isinstance(raw_arguments, str)
            try:
                arguments = (
                    json.loads(raw_arguments) if was_string else raw_arguments
                )
            except (TypeError, json.JSONDecodeError):
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            safe_arguments = cls._safe_tool_arguments(name, arguments)
            function["arguments"] = (
                cls._json_dump(safe_arguments)
                if was_string
                else safe_arguments
            )
            call_id = str(call.get("id", ""))
            if context is not None and call_id:
                context[call_id] = (name, arguments)
            sanitized.append(call)
        return sanitized

    @classmethod
    def _sanitize_browser_state(
        cls,
        raw_state: dict[str, Any],
        *,
        snapshot: str = "",
    ) -> dict[str, Any]:
        state = cls._scrub_sensitive_argument_text(
            redact_mapping(copy.deepcopy(raw_state or {}))
        )
        state["latest_snapshot"] = snapshot
        state["browser_initialized"] = False
        for key in ("failed_action_counts", "blocked_actions"):
            state[key] = {} if key == "failed_action_counts" else []
        for record_name in ("pending_verification", "completion_evidence"):
            record = state.get(record_name)
            if not isinstance(record, dict):
                continue
            name = str(record.get("tool_name", ""))
            arguments = record.get("arguments", {})
            if isinstance(arguments, dict):
                record["arguments"] = cls._safe_tool_arguments(
                    name,
                    arguments,
                )
        return state

    @staticmethod
    def _safe_tool_arguments(
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        safe = redact_tool_arguments(tool_name, arguments)
        safe = ActiveTaskCheckpointStore._scrub_sensitive_argument_text(safe)
        normalized_name = tool_name.strip().lower()
        if normalized_name == "write_file" and "content" in safe:
            safe["content"] = REDACTED
        elif normalized_name == "memory_write" and "value" in safe:
            safe["value"] = REDACTED
        return safe

    @staticmethod
    def _scrub_sensitive_argument_text(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): ActiveTaskCheckpointStore._scrub_sensitive_argument_text(
                    item
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                ActiveTaskCheckpointStore._scrub_sensitive_argument_text(item)
                for item in value
            ]
        if isinstance(value, str):
            redacted = redact_text(value)
            if redacted != value:
                return redacted
            if _SENSITIVE_ARGUMENT_TEXT_PATTERN.search(value):
                return REDACTED
        return value

    def _delete(self, table: str, session_key: str) -> None:
        if not self.available or table not in {
            "active_tasks",
            "recent_browser_tasks",
        }:
            return
        try:
            with self._connect() as connection:
                connection.execute(
                    f"DELETE FROM {table} WHERE session_key=?",
                    (session_key,),
                )
        except sqlite3.Error as exc:
            self._record_error(exc)

    def _count(self, table: str) -> int:
        if not self.available or table not in {
            "active_tasks",
            "recent_browser_tasks",
        }:
            return 0
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT COUNT(*) AS count FROM {table}"
                ).fetchone()
            return int(row["count"])
        except sqlite3.Error as exc:
            self._record_error(exc)
            return 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("checkpoint clock must be timezone-aware")
        return value

    def _after(self, seconds: int) -> datetime:
        return self._now() + timedelta(seconds=seconds)

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("checkpoint timestamp must be timezone-aware")
        return parsed

    @staticmethod
    def _json_dump(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _record_error(self, exc: BaseException) -> None:
        self.last_error = redact_text(f"{type(exc).__name__}: {exc}")
        self._available = False
