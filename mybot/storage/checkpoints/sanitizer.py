"""Checkpoint data minimization and secret scrubbing, independent of storage."""
from __future__ import annotations

import copy
import json
import re
from typing import Any

from ...tracing import (
    REDACTED,
    redact_mapping,
    redact_text,
    redact_tool_arguments,
    redact_tool_text,
)


_SENSITIVE_ARGUMENT_TEXT_PATTERN = re.compile(
    r"(?i)(?:\b(?:password|passwd|token|api[_-]?key|apikey|authorization|"
    r"cookie|secret)\b|\bbearer\s+\S+)"
)


def sanitize_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sensitive_values = sensitive_values_from_messages(messages)
    call_context: dict[str, tuple[str, dict[str, Any]]] = {}
    sanitized: list[dict[str, Any]] = []
    for raw_message in messages:
        message = redact_mapping(copy.deepcopy(raw_message))
        calls = message.get("tool_calls")
        if isinstance(calls, list):
            message["tool_calls"] = sanitize_tool_calls(
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


def sensitive_values_from_messages(
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
                safe = sanitize_tool_arguments(name, parsed)
                collect_redacted_values(parsed, safe, values)
    return values


def collect_redacted_values(
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
                collect_redacted_values(value, redacted[key], values)
    elif isinstance(original, (list, tuple)) and isinstance(redacted, list):
        for value, safe_value in zip(original, redacted):
            collect_redacted_values(value, safe_value, values)


def sanitize_tool_calls(
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
        safe_arguments = sanitize_tool_arguments(name, arguments)
        function["arguments"] = (
            json.dumps(
                safe_arguments, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )
            if was_string
            else safe_arguments
        )
        call_id = str(call.get("id", ""))
        if context is not None and call_id:
            context[call_id] = (name, arguments)
        sanitized.append(call)
    return sanitized


def sanitize_browser_state(
    raw_state: dict[str, Any],
    *,
    snapshot: str = "",
) -> dict[str, Any]:
    state = scrub_sensitive_argument_text(
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
            record["arguments"] = sanitize_tool_arguments(
                name,
                arguments,
            )
    return state


def sanitize_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    safe = redact_tool_arguments(tool_name, arguments)
    safe = scrub_sensitive_argument_text(safe)
    normalized_name = tool_name.strip().lower()
    if normalized_name == "write_file" and "content" in safe:
        safe["content"] = REDACTED
    return safe


def scrub_sensitive_argument_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): scrub_sensitive_argument_text(
                item
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            scrub_sensitive_argument_text(item)
            for item in value
        ]
    if isinstance(value, str):
        redacted = redact_text(value)
        if redacted != value:
            return redacted
        if _SENSITIVE_ARGUMENT_TEXT_PATTERN.search(value):
            return REDACTED
    return value
