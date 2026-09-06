from __future__ import annotations

from typing import Any

from ..storage.artifacts import ArtifactRecord, ArtifactStore
from ..tools.result import BrowserResult, ToolResult


_EXCLUDED_PREFIXES = ("browser_",)
_PREVIEW_CHARS = 1600


def _bounded_preview(value: str, arguments: dict[str, Any] | None) -> str:
    from ..tracing import redact_text, redact_tool_text

    sanitized = redact_tool_text("tool_result", value, arguments or {})
    sanitized = redact_text(sanitized)
    if len(sanitized) <= _PREVIEW_CHARS:
        return sanitized
    marker = "\n...[preview truncated]...\n"
    available = _PREVIEW_CHARS - len(marker)
    head = max(0, available // 2)
    return sanitized[:head] + marker + sanitized[-(available - head):]


def externalize_tool_result(
    result: ToolResult,
    *,
    tool_name: str,
    arguments: dict[str, Any] | None,
    session_key: str,
    task_id: str | None,
    store: ArtifactStore | None,
    enabled: bool,
    threshold_chars: int,
) -> tuple[str, ArtifactRecord | None]:
    rendered = result.to_text()
    normalized_name = tool_name.strip().lower()
    if (
        not enabled
        or store is None
        or isinstance(result, BrowserResult)
        or normalized_name.startswith(_EXCLUDED_PREFIXES)
        or normalized_name in {"artifact_read", "request_user_input"}
        or len(rendered) <= threshold_chars
    ):
        return rendered, None
    try:
        record = store.put(
            session_key,
            task_id,
            tool_name,
            rendered,
            arguments,
        )
    except Exception:
        preview = _bounded_preview(rendered, arguments)
        return (
            "[large tool output could not be externalized]\n"
            f"original_chars={len(rendered)}\n\n"
            "Preview:\n"
            f"{preview}\n\n"
            "The omitted content is unavailable. Do not guess it.",
            None,
        )
    content_result = store.read(
        session_key,
        record.artifact_id,
        offset=0,
        max_chars=_PREVIEW_CHARS,
    )
    preview = content_result[0] if content_result else ""
    return (
        "[large tool output externalized]\n"
        f"artifact_id={record.artifact_id}\n"
        f"source_tool={record.source_tool}\n"
        f"original_chars={record.original_chars}\n"
        f"stored_chars={record.stored_chars}\n"
        f"storage_truncated={str(record.storage_truncated).lower()}\n"
        "Preview:\n"
        f"{preview}\n"
        "Use artifact_read with this artifact_id and bounded offset/max_chars "
        "or query to retrieve more content.",
        record,
    )
