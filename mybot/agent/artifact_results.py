from __future__ import annotations

from typing import Any

from ..storage.artifacts import ArtifactRecord, ArtifactStore
from ..tools.result import BrowserResult, ToolResult


_EXCLUDED_PREFIXES = ("browser_",)
_PREVIEW_CHARS = 1600


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
        or len(result.output) <= threshold_chars
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
        return rendered, None
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
