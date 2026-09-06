from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .models import ArtifactRecord


MAX_ARTIFACT_CHARS = 1_000_000
_ARTIFACT_ID = re.compile(r"^art_[0-9a-f]{32}$")


class ArtifactStore:
    """Text-only, session-bound storage for large model tool results."""

    def __init__(self, workspace: Path, *, max_chars: int = MAX_ARTIFACT_CHARS):
        self.workspace = workspace.expanduser().resolve()
        self.root = self.workspace / "artifacts"
        self.data_dir = self.root / "data"
        self.meta_dir = self.root / "meta"
        self.max_chars = max(1, min(int(max_chars), MAX_ARTIFACT_CHARS))

    def _paths(self, artifact_id: str) -> tuple[Path, Path] | None:
        if not _ARTIFACT_ID.fullmatch(str(artifact_id)):
            return None
        return (
            self.data_dir / f"{artifact_id}.txt",
            self.meta_dir / f"{artifact_id}.json",
        )

    @staticmethod
    def _bounded(text: str, limit: int) -> tuple[str, bool]:
        if len(text) <= limit:
            return text, False
        head = limit // 2
        tail = limit - head
        marker = "\n...[storage truncated]...\n"
        available = max(0, limit - len(marker))
        head = available // 2
        tail = available - head
        return text[:head] + marker + text[-tail:], True

    def put(
        self,
        session_key: str,
        task_id: str | None,
        source_tool: str,
        output: str,
        arguments: dict | None = None,
    ) -> ArtifactRecord:
        if not session_key or not session_key.strip():
            raise ValueError("artifact session identity is required")
        from ...tracing import redact_text, redact_tool_text

        raw = str(output)
        redacted = redact_tool_text(source_tool, raw, arguments or {})
        redacted = redact_text(redacted)
        was_redacted = redacted != raw
        stored, storage_truncated = self._bounded(redacted, self.max_chars)
        artifact_id = f"art_{uuid.uuid4().hex}"
        data_path, meta_path = self._paths(artifact_id)  # type: ignore[misc]
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        record = ArtifactRecord(
            artifact_id=artifact_id,
            session_key=session_key,
            task_id=task_id,
            source_tool=source_tool,
            created_at=datetime.now(UTC).isoformat(),
            original_chars=len(raw),
            stored_chars=len(stored),
            sha256=hashlib.sha256(stored.encode("utf-8")).hexdigest(),
            redacted=was_redacted,
            storage_truncated=storage_truncated,
        )
        self._atomic_write(data_path, stored, binary=False)
        self._atomic_write(
            meta_path,
            json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")),
            binary=False,
        )
        return record

    @staticmethod
    def _atomic_write(path: Path, value: str, *, binary: bool) -> None:
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            if binary:
                temp.write_bytes(value)  # type: ignore[arg-type]
            else:
                temp.write_text(value, encoding="utf-8")
            try:
                os.chmod(temp, 0o600)
            except OSError:
                pass
            os.replace(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def read(
        self,
        session_key: str,
        artifact_id: str,
        *,
        offset: int = 0,
        max_chars: int = 4000,
        query: str = "",
    ) -> tuple[str, ArtifactRecord] | None:
        if not session_key or not session_key.strip() or offset < 0 or max_chars < 1:
            return None
        paths = self._paths(artifact_id)
        if paths is None:
            return None
        data_path, meta_path = paths
        try:
            record = ArtifactRecord.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
            if record.session_key != session_key:
                return None
            content = data_path.read_text(encoding="utf-8")
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None
        if query:
            snippets: list[str] = []
            start = 0
            while len(snippets) < 8:
                found = content.find(query, start)
                if found < 0:
                    break
                left = max(0, found - max_chars // 2)
                right = min(len(content), found + len(query) + max_chars // 2)
                snippets.append(content[left:right])
                start = found + max(1, len(query))
            return ("\n...\n".join(snippets)[:max_chars], record) if snippets else ("", record)
        return content[offset : offset + max_chars], record
