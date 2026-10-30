from __future__ import annotations

from typing import Any


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_turns(turns: Any) -> None:
    """Reject incomplete turns, unknown fields and unpaired tool messages."""
    _require(isinstance(turns, list), "turns must be a list")
    for turn in turns:
        _require(isinstance(turn, list) and len(turn) >= 2, "Each turn must be a complete message list")
        _require(all(isinstance(m, dict) for m in turn), "Messages must be objects")
        _require(turn[0].get("role") == "user", "Turn must start with user")
        pending, seen = set(), set()
        for index, message in enumerate(turn):
            role = message.get("role")
            content = message.get("content")
            if role == "user":
                _require(index == 0 and set(message) == {"role", "content"}
                         and isinstance(content, str), "Invalid user message")
            elif role == "assistant":
                _require(index > 0 and not pending, "Assistant before all tool results")
                _require(set(message) <= {"role", "content", "tool_calls"}, "Unknown assistant fields")
                calls = message.get("tool_calls")
                if calls is not None:
                    _require(isinstance(calls, list) and bool(calls), "tool_calls must be non-empty")
                    _require(content is None or isinstance(content, str), "Invalid assistant content")
                    for call in calls:
                        _require(isinstance(call, dict) and set(call) == {"id", "type", "function"}, "Invalid tool call")
                        identifier = call["id"]
                        _require(isinstance(identifier, str) and bool(identifier) and identifier not in seen,
                                 "Duplicate or invalid tool call ID")
                        function = call["function"]
                        _require(call["type"] == "function" and isinstance(function, dict)
                                 and set(function) == {"name", "arguments"}, "Invalid tool function")
                        _require(isinstance(function["name"], str) and bool(function["name"])
                                 and isinstance(function["arguments"], str), "Invalid function parameters")
                        pending.add(identifier)
                        seen.add(identifier)
                else:
                    _require(index == len(turn) - 1 and isinstance(content, str), "Unfinished or invalid assistant reply")
            elif role == "tool":
                identifier = message.get("tool_call_id")
                _require(set(message) == {"role", "tool_call_id", "content"}
                         and isinstance(identifier, str) and identifier in pending
                         and isinstance(content, str), "Unpaired or invalid tool result")
                pending.remove(identifier)
            else:
                raise ValueError("Session accepts only user/assistant/tool messages")
        _require(not pending and turn[-1].get("role") == "assistant"
                 and not turn[-1].get("tool_calls"), "Turn must end with a final assistant reply")
