"""Run tracing: record one agent run, print a summary, optionally save JSON."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .tools.base import ToolResult


REDACTED = "***REDACTED***"
RESULT_PREVIEW_MAX_CHARS = 2000

_SENSITIVE_KEYS = (
    "password", "passwd", "token", "api_key", "apikey",
    "authorization", "cookie", "secret",
)
_SENSITIVE_TEXT = re.compile(
    r"(?i)(\b(?:password|passwd|token|api[_-]?key|apikey|authorization|"
    r"cookie|secret)\b[\"']?\s*[=:]\s*)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|bearer\s+[^\s,}\r\n]+|[^\s\"',}\r\n]+)"
)


def redact_text(value: str) -> str:
    """Hide values of secret-looking ``key=value`` pairs."""
    return _SENSITIVE_TEXT.sub(rf"\1{REDACTED}", value)


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Recursively copy a mapping, hiding sensitive keys and text values."""
    result: dict[str, Any] = {}
    for key, value in mapping.items():
        name = str(key)
        if any(part in name.lower().replace("-", "_") for part in _SENSITIVE_KEYS):
            result[name] = REDACTED
        elif isinstance(value, dict):
            result[name] = redact_mapping(value)
        elif isinstance(value, (list, tuple)):
            result[name] = [
                redact_mapping(item) if isinstance(item, dict)
                else redact_text(item) if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            result[name] = redact_text(value)
        else:
            result[name] = value
    return result


def redact_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Redact common keys plus values that are sensitive for specific tools."""
    redacted = redact_mapping(arguments)
    if tool_name == "browser_type" and "text" in redacted:
        redacted["text"] = REDACTED
    return redacted


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class StepTrace:
    index: int
    started_at: str
    status: str = "running"
    finished_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None


@dataclass(slots=True)
class LLMCallTrace:
    step_index: int
    started_at: str
    model: str
    message_count: int
    retry_count: int = 0
    finished_at: str | None = None
    duration_ms: float | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallTrace:
    step_index: int
    tool_name: str
    arguments: dict[str, Any]
    started_at: str
    finished_at: str | None = None
    duration_ms: float | None = None
    success: bool = False
    result_preview: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRunTrace:
    run_id: str
    started_at: str
    user_input: str
    finished_at: str | None = None
    duration_ms: float | None = None
    status: str = "running"
    final_output: str = ""
    steps: list[StepTrace] = field(default_factory=list)
    llm_calls: list[LLMCallTrace] = field(default_factory=list)
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary_text(self) -> str:
        duration = (self.duration_ms or 0.0) / 1000
        browser_calls = sum(call.tool_name.startswith("browser_") for call in self.tool_calls)
        retries = sum(call.retry_count for call in self.llm_calls)
        errors = sum(call.error is not None for call in self.llm_calls)
        errors += sum(not call.success for call in self.tool_calls)
        return "\n".join(
            [
                f"Run: {self.run_id}",
                f"Status: {self.status}",
                f"Duration: {duration:.2f}s",
                f"Steps: {len(self.steps)}",
                f"LLM Calls: {len(self.llm_calls)}",
                f"Tool Calls: {len(self.tool_calls)}",
                f"Browser Calls: {browser_calls}",
                f"Retries: {retries}",
                f"Errors: {errors or int(self.error is not None)}",
            ]
        )


class AgentTracer:
    """Collect one agent run in memory, and optionally persist it on completion."""

    def __init__(self, trace_dir: Path | None = None):
        self.trace_dir = trace_dir.resolve() if trace_dir else None
        self.run: AgentRunTrace | None = None
        self.step: StepTrace | None = None
        self._started: dict[int, float] = {}

    def start_run(self, user_input: str, metadata: dict[str, Any] | None = None) -> AgentRunTrace:
        self.run = AgentRunTrace(
            run_id=uuid.uuid4().hex,
            started_at=_now(),
            user_input=redact_text(user_input),
            metadata=redact_mapping(metadata or {}),
        )
        self.step = None
        self._started = {0: time.perf_counter()}
        return self.run

    def finish_run(self, final_output: str = "", status: str = "success", error: str | None = None) -> AgentRunTrace:
        run = self._run()
        unfinished = error or "run ended before this call completed"
        for call in run.llm_calls:
            if call.finished_at is None:
                self.finish_llm_call(call, error=unfinished)
        for call in run.tool_calls:
            if call.finished_at is None:
                self.finish_tool_call(call, error=unfinished)
        if self.step is not None and self.step.status == "running":
            self.finish_step(status="failed", error=error or "run ended")
        run.finished_at = _now()
        run.duration_ms = self._elapsed(0)
        run.status = status
        run.final_output = redact_text(final_output)
        run.error = redact_text(error) if error else None
        if self.trace_dir:
            self.save()
        return run

    def start_step(self, index: int) -> StepTrace:
        self._require_running()
        step = StepTrace(index=index, started_at=_now())
        self.run.steps.append(step)
        self.step = step
        self._started[id(step)] = time.perf_counter()
        return step

    def finish_step(self, status: str = "success", error: str | None = None) -> StepTrace | None:
        step = self.step
        if step is None:
            return None
        step.finished_at = _now()
        step.duration_ms = self._elapsed(id(step))
        step.status = status
        step.error = redact_text(error) if error else None
        self.step = None
        return step

    def start_llm_call(self, step: StepTrace | None, model: str, message_count: int, retry_count: int = 0) -> LLMCallTrace:
        call = LLMCallTrace(
            step_index=step.index if step else 0,
            started_at=_now(),
            model=model,
            message_count=message_count,
            retry_count=retry_count,
        )
        self._run().llm_calls.append(call)
        self._started[id(call)] = time.perf_counter()
        return call

    def finish_llm_call(
        self,
        call: LLMCallTrace,
        *,
        finish_reason: str | None = None,
        total_tokens: int | None = None,
        error: str | None = None,
    ) -> LLMCallTrace:
        call.finished_at = _now()
        call.duration_ms = self._elapsed(id(call))
        call.finish_reason = finish_reason
        call.total_tokens = total_tokens
        call.error = redact_text(error) if error else None
        return call

    def start_tool_call(
        self,
        step: StepTrace | None,
        tool_name: str,
        arguments: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> ToolCallTrace:
        call = ToolCallTrace(
            step_index=step.index if step else 0,
            tool_name=tool_name,
            arguments=redact_arguments(tool_name, arguments),
            started_at=_now(),
            metadata=redact_mapping(metadata or {}),
        )
        self._run().tool_calls.append(call)
        self._started[id(call)] = time.perf_counter()
        return call

    def finish_tool_call(
        self,
        call: ToolCallTrace,
        result: ToolResult | None = None,
        error: str | None = None,
    ) -> ToolCallTrace:
        call.finished_at = _now()
        call.duration_ms = self._elapsed(id(call))
        if result is None:
            call.error = redact_text(error or "tool call did not return a result")
            return call
        call.success = result.success
        call.result_preview = redact_text(result.output)[:RESULT_PREVIEW_MAX_CHARS]
        if result.error:
            call.error = redact_text(result.error)
        call.metadata.update(redact_mapping(result.metadata))
        return call

    def save(self) -> Path | None:
        """Write the finished run as JSON. Never raises."""
        run = self.run
        if run is None or not self.trace_dir:
            return None
        try:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            path = self.trace_dir / f"{run.run_id}.json"
            path.write_text(
                json.dumps(_json_safe(asdict(run)), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return path
        except Exception as exc:
            run.metadata["trace_persist_error"] = redact_text(f"{type(exc).__name__}: {exc}")
            return None

    def _run(self) -> AgentRunTrace:
        if self.run is None:
            raise RuntimeError("no agent run has been started")
        return self.run

    def _require_running(self) -> None:
        if self.run is None or self.run.status != "running":
            raise RuntimeError("no running agent run")

    def _elapsed(self, key: int) -> float:
        started = self._started.pop(key, time.perf_counter())
        return max(0.0, (time.perf_counter() - started) * 1000)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)
