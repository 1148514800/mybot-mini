from __future__ import annotations

from typing import Any

from ..storage.artifacts import ArtifactStore
from .base import Tool
from .result import ToolResult


class ArtifactReadTool(Tool):
    def __init__(self, store: ArtifactStore, *, read_max_chars: int = 8000):
        self.store = store
        self.read_max_chars = max(1, int(read_max_chars))

    @property
    def name(self) -> str:
        return "artifact_read"

    @property
    def description(self) -> str:
        return "Read a bounded portion or query snippet from a large tool result artifact."

    @property
    def requires_runtime_identity(self) -> bool:
        return True

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "artifact_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "max_chars": {"type": "integer", "minimum": 1, "maximum": self.read_max_chars, "default": 4000},
                "query": {"type": "string", "default": ""},
            },
            "required": ["artifact_id"],
        }

    async def execute(
        self,
        artifact_id: str,
        offset: int = 0,
        max_chars: int = 4000,
        query: str = "",
        *,
        session_key: str = "",
        task_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        if not session_key or not session_key.strip():
            return ToolResult(False, error="Artifact read requires trusted runtime identity.", metadata={"error_type": "artifact_ownership_identity_missing", "recoverable": False})
        if offset < 0 or max_chars < 1 or max_chars > self.read_max_chars:
            return ToolResult(False, error="Invalid artifact read bounds.", metadata={"error_type": "artifact_read_bounds_invalid", "recoverable": True})
        result = self.store.read(session_key, artifact_id, offset=offset, max_chars=max_chars, query=query)
        if result is None:
            return ToolResult(False, error="Artifact is unavailable.", metadata={"error_type": "artifact_unavailable", "recoverable": True})
        content, record = result
        next_offset = offset + len(content) if not query else offset
        return ToolResult(True, output=content, metadata={"artifact_id": record.artifact_id, "offset": offset, "returned_chars": len(content), "next_offset": next_offset, "total_chars": record.stored_chars, "source_tool": record.source_tool, "query": bool(query)})
