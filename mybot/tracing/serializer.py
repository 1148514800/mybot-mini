from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import (
    AgentRunTrace,
    AgentStepTrace,
    LLMCallTrace,
    ToolCallTrace,
)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def trace_to_dict(trace: AgentRunTrace) -> dict[str, Any]:
    return _json_safe(asdict(trace))


def trace_to_json(trace: AgentRunTrace, *, indent: int | None = 2) -> str:
    return json.dumps(
        trace_to_dict(trace),
        ensure_ascii=False,
        indent=indent,
    )


def trace_from_dict(data: dict[str, Any]) -> AgentRunTrace:
    run_data = dict(data)
    run_data["steps"] = [
        AgentStepTrace(**step) for step in run_data.get("steps", [])
    ]
    run_data["llm_calls"] = [
        LLMCallTrace(**call) for call in run_data.get("llm_calls", [])
    ]
    run_data["tool_calls"] = [
        ToolCallTrace(**call) for call in run_data.get("tool_calls", [])
    ]
    return AgentRunTrace(**run_data)


def save_trace(trace: AgentRunTrace, trace_dir: Path) -> Path:
    destination = trace_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"{trace.run_id}.json"
    temporary_path = destination / f".{trace.run_id}.tmp"
    temporary_path.write_text(trace_to_json(trace) + "\n", encoding="utf-8")
    temporary_path.replace(path)
    return path


def load_trace(path: Path) -> AgentRunTrace:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("trace file must contain a JSON object")
    return trace_from_dict(data)
