from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from ...tracing import redact_text
from .models import (
    CHECKPOINT_SCHEMA_VERSION,
    DEFAULT_RECENT_TASK_TTL_SECONDS,
    RecoveredActiveCheckpoint,
)
from .serialization import (
    recent_recovery_payload,
    serialize_approval,
    serialize_clarification,
    serialize_recent,
)


CHECKPOINT_DIRECTORY = "checkpoints"
CHECKPOINT_FILENAME = "active_tasks.sqlite3"


class _CheckpointConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()

_ACTIVE_KINDS = frozenset({"approval", "clarification", "verification"})


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
        payload = serialize_approval(pending)
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
            serialize_clarification(pending),
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
            "payload": serialize_recent(task, expires_at),
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
                item = self._validate_active_row_payload(document, session_key)
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
                item = self._validate_recent_row_payload(
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

    def clear_active(self, session_key: str) -> bool:
        return self._delete("active_tasks", session_key)

    def consume_active(self, session_key: str) -> bool:
        """Delete exactly one durable active row before a side effect."""
        if not self.available:
            return not self.enabled
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM active_tasks WHERE session_key=?",
                    (session_key,),
                )
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            self._record_error(exc)
            return False

    def clear_recent(self, session_key: str) -> bool:
        return self._delete("recent_browser_tasks", session_key)

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

    def _validate_active_row_payload(
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

    def _validate_recent_row_payload(
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
        return recent_recovery_payload(payload, session_key, expires_at)

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

    def _delete(self, table: str, session_key: str) -> bool:
        if not self.available or table not in {
            "active_tasks",
            "recent_browser_tasks",
        }:
            return not self.enabled
        try:
            with self._connect() as connection:
                connection.execute(
                    f"DELETE FROM {table} WHERE session_key=?",
                    (session_key,),
                )
            return True
        except sqlite3.Error as exc:
            self._record_error(exc)
            return False

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
        connection = sqlite3.connect(self.path, factory=_CheckpointConnection)
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
