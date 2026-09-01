from __future__ import annotations

import time
import uuid
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..tools.result import BrowserResult, ToolResult
from .models import (
    RUN_STATUSES,
    AgentRunTrace,
    AgentStepTrace,
    LLMCallTrace,
    ToolCallTrace,
)
from .serializer import save_trace


RESULT_PREVIEW_MAX_CHARS = 2000
REDACTED = "***REDACTED***"
SENSITIVE_KEYS = (
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "secret",
)
SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(\b(?:password|passwd|token|api[_-]?key|apikey|authorization|"
    r"cookie|secret)\b\s*[=:]\s*[\"']?)([^\s\"',;}]+)"
)


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(sensitive in normalized for sensitive in SENSITIVE_KEYS)


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def redact_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    """Return a recursively copied mapping with common secret fields hidden."""
    return {
        str(key): REDACTED if _is_sensitive_key(key) else _redact_value(value)
        for key, value in mapping.items()
    }


def redact_text(value: str) -> str:
    return SENSITIVE_TEXT_PATTERN.sub(rf"\1{REDACTED}", value)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class AgentTracer:
    """Collect one agent run in memory and optionally persist it on completion."""

    def __init__(self, trace_dir: Path | None = None):
        self.trace_dir = trace_dir.resolve() if trace_dir else None
        self._current_run: AgentRunTrace | None = None
        self._current_step: AgentStepTrace | None = None
        self._started: dict[str, float] = {}

    def start_run(
        self,
        user_input: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRunTrace:
        if self._current_run and self._current_run.status == "running":
            raise RuntimeError("an agent run is already active")
        run = AgentRunTrace(
            run_id=uuid.uuid4().hex,
            started_at=_now(),
            user_input=redact_text(user_input),
            metadata=redact_mapping(metadata or {}),
        )
        self._current_run = run
        self._current_step = None
        self._started = {run.run_id: time.perf_counter()}
        return run

    def finish_run(
        self,
        final_output: str = "",
        status: str = "success",
        error: str | None = None,
    ) -> AgentRunTrace:
        run = self._require_run()
        if status not in RUN_STATUSES - {"running"}:
            raise ValueError(f"unsupported run status: {status}")
        unfinished_error = error or "run ended before trace item completed"
        for call in run.llm_calls:
            if call.finished_at is None:
                self.finish_llm_call(call, error=unfinished_error)
        for call in run.tool_calls:
            if call.finished_at is None:
                self.finish_tool_call(call, error=unfinished_error)
        if self._current_step and self._current_step.status == "running":
            self.finish_step(status="failed", error=error or "run ended")
        run.finished_at = _now()
        run.duration_ms = self._finish_timer(run.run_id)
        run.status = status
        run.final_output = redact_text(final_output)
        run.error = redact_text(error) if error else None
        if self.trace_dir:
            try:
                save_trace(run, self.trace_dir)
            except Exception as exc:
                run.metadata["trace_persist_error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
        return run

    def start_step(self, step_index: int) -> AgentStepTrace:
        run = self._require_running_run()
        if self._current_step and self._current_step.status == "running":
            raise RuntimeError("an agent step is already active")
        step = AgentStepTrace(
            step_id=uuid.uuid4().hex,
            step_index=step_index,
            started_at=_now(),
        )
        run.steps.append(step)
        self._current_step = step
        self._started[step.step_id] = time.perf_counter()
        return step

    def finish_step(
        self,
        status: str = "success",
        error: str | None = None,
    ) -> AgentStepTrace:
        step = self._require_step()
        step.finished_at = _now()
        step.duration_ms = self._finish_timer(step.step_id)
        step.status = status
        step.error = error
        self._current_step = None
        return step

    def start_llm_call(
        self,
        *,
        step_id: str,
        model: str,
        provider: str,
        message_count: int,
        retry_count: int = 0,
    ) -> LLMCallTrace:
        run = self._require_running_run()
        step = self._step_by_id(step_id)
        call = LLMCallTrace(
            call_id=uuid.uuid4().hex,
            step_id=step_id,
            started_at=_now(),
            model=model,
            provider=provider,
            message_count=message_count,
            retry_count=retry_count,
        )
        run.llm_calls.append(call)
        step.llm_call_id = call.call_id
        self._started[call.call_id] = time.perf_counter()
        return call

    def finish_llm_call(
        self,
        call: LLMCallTrace,
        *,
        finish_reason: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        error: str | None = None,
    ) -> LLMCallTrace:
        call.finished_at = _now()
        call.duration_ms = self._finish_timer(call.call_id)
        call.finish_reason = finish_reason
        call.input_tokens = input_tokens
        call.output_tokens = output_tokens
        call.total_tokens = total_tokens
        call.error = redact_text(error) if error else None
        return call

    def record_llm_call(
        self,
        *,
        step_id: str,
        model: str,
        provider: str,
        message_count: int,
        retry_count: int = 0,
        finish_reason: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        error: str | None = None,
        duration_ms: float | None = None,
    ) -> LLMCallTrace:
        call = self.start_llm_call(
            step_id=step_id,
            model=model,
            provider=provider,
            message_count=message_count,
            retry_count=retry_count,
        )
        self.finish_llm_call(
            call,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error=error,
        )
        if duration_ms is not None:
            call.duration_ms = max(0.0, duration_ms)
        return call

    def start_tool_call(
        self,
        *,
        step_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> ToolCallTrace:
        run = self._require_running_run()
        step = self._step_by_id(step_id)
        call = ToolCallTrace(
            call_id=uuid.uuid4().hex,
            step_id=step_id,
            tool_name=tool_name,
            arguments=redact_mapping(arguments),
            started_at=_now(),
            metadata=redact_mapping(metadata or {}),
        )
        run.tool_calls.append(call)
        step.tool_call_ids.append(call.call_id)
        self._started[call.call_id] = time.perf_counter()
        return call

    def finish_tool_call(
        self,
        call: ToolCallTrace,
        result: ToolResult | None = None,
        error: str | None = None,
    ) -> ToolCallTrace:
        call.finished_at = _now()
        call.duration_ms = self._finish_timer(call.call_id)
        if result is None:
            call.success = False
            raw_error = error or "tool call did not return a result"
            call.error = redact_text(raw_error)
            return call

        call.success = result.success
        call.result_type = type(result).__name__
        call.result_preview = redact_text(result.output)[
            :RESULT_PREVIEW_MAX_CHARS
        ]
        raw_error = result.error or error
        call.error = redact_text(raw_error) if raw_error else None
        call.metadata.update(redact_mapping(result.metadata))
        if isinstance(result, BrowserResult):
            call.metadata.update(
                {
                    key: value
                    for key, value in {
                        "action": result.action,
                        "session": result.session,
                        "url": result.url,
                        "title": result.title,
                    }.items()
                    if value is not None and value != ""
                }
            )
        return call

    def record_tool_call(
        self,
        *,
        step_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        metadata: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> ToolCallTrace:
        call = self.start_tool_call(
            step_id=step_id,
            tool_name=tool_name,
            arguments=arguments,
            metadata=metadata,
        )
        self.finish_tool_call(call, result=result)
        if duration_ms is not None:
            call.duration_ms = max(0.0, duration_ms)
        return call

    def get_current_run(self) -> AgentRunTrace | None:
        return self._current_run

    def _finish_timer(self, trace_id: str) -> float:
        started = self._started.pop(trace_id, time.perf_counter())
        return max(0.0, (time.perf_counter() - started) * 1000)

    def _require_run(self) -> AgentRunTrace:
        if self._current_run is None:
            raise RuntimeError("no agent run has been started")
        return self._current_run

    def _require_running_run(self) -> AgentRunTrace:
        run = self._require_run()
        if run.status != "running":
            raise RuntimeError("the current agent run has already finished")
        return run

    def _require_step(self) -> AgentStepTrace:
        if self._current_step is None:
            raise RuntimeError("no agent step has been started")
        return self._current_step

    def _step_by_id(self, step_id: str) -> AgentStepTrace:
        run = self._require_running_run()
        for step in run.steps:
            if step.step_id == step_id:
                return step
        raise ValueError(f"unknown step_id: {step_id}")
