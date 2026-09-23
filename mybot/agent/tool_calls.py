"""Pure conversion helpers for model tool calls.

This module deliberately has no Runtime, Tool, or Browser imports.
"""
from __future__ import annotations

import json
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
