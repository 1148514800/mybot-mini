from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
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


class SessionStore:
    """Versioned JSON and atomic replacement; no concurrent writers supported."""

    def __init__(self, path: Path, workspace: Path):
        self.path = Path(path).resolve()
        self.workspace = Path(workspace).resolve()
        self._check_path()

    def _check_path(self) -> None:
        if self.path.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError("Session storage must be outside the agent workspace")

    def load(self) -> list[list[dict[str, Any]]]:
        self._check_path()
        try:
            with self.path.open(encoding="utf-8") as stream:
                data = json.load(stream)
            _require(isinstance(data, dict) and set(data) == {"version", "turns"}, "Invalid Session document")
            _require(type(data["version"]) is int and data["version"] == 1, "Unsupported Session version")
            validate_turns(data["turns"])
            return data["turns"]
        except FileNotFoundError:
            return []
        except (OSError, ValueError, UnicodeError) as exc:
            detail = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, UnicodeError) else type(exc).__name__
            raise RuntimeError(f"Session load failed: {self.path}; original file preserved ({detail})") from None

    def save(self, turns: list[list[dict[str, Any]]]) -> None:
        self._check_path()
        validate_turns(turns)
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".session-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump({"version": 1, "turns": turns}, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except OSError as exc:
            raise RuntimeError(f"Session save failed: {self.path} ({type(exc).__name__}); memory not updated") from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def clear(self) -> None:
        self.save([])
