"""Pure conversion helpers for model tool calls.

This module deliberately has no Runtime, Tool, Approval, or Browser imports.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any


def tool_call_signature(tool_call: Any) -> str:
    """Return a stable signature used only for duplicate-call detection."""
    name = str(tool_call.function.name)
    raw_arguments = tool_call.function.arguments or "{}"
    try:
        arguments = json.loads(raw_arguments)
        normalized = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, json.JSONDecodeError):
        normalized = str(raw_arguments)
    return f"{name}:{normalized}"


def serialize_tool_call(tool_call: Any) -> dict[str, Any]:
    """Convert an SDK tool-call object to a checkpoint-safe mapping."""
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        },
    }


def deserialize_tool_call(value: dict[str, Any]) -> Any:
    """Rebuild the small SDK-compatible shape consumed by the loop."""
    function = value.get("function", {})
    return SimpleNamespace(
        id=str(value.get("id", "")),
        function=SimpleNamespace(
            name=str(function.get("name", "")),
            arguments=function.get("arguments", "{}"),
        ),
    )
