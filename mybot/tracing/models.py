from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RUN_STATUSES = frozenset({"running", "success", "failed", "max_steps"})


@dataclass(slots=True)
class AgentStepTrace:
    step_id: str
    step_index: int
    started_at: str
    finished_at: str | None = None
    duration_ms: float | None = None
    llm_call_id: str | None = None
    tool_call_ids: list[str] = field(default_factory=list)
    status: str = "running"
    error: str | None = None


@dataclass(slots=True)
class LLMCallTrace:
    call_id: str
    step_id: str
    started_at: str
    model: str
    provider: str
    message_count: int
    retry_count: int = 0
    finished_at: str | None = None
    duration_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None


@dataclass(slots=True)
class ToolCallTrace:
    call_id: str
    step_id: str
    tool_name: str
    arguments: dict[str, Any]
    started_at: str
    finished_at: str | None = None
    duration_ms: float | None = None
    success: bool | None = None
    result_type: str | None = None
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
    steps: list[AgentStepTrace] = field(default_factory=list)
    llm_calls: list[LLMCallTrace] = field(default_factory=list)
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        browser_calls = sum(
            call.tool_name.startswith("browser_") for call in self.tool_calls
        )
        retries = sum(call.retry_count > 0 for call in self.llm_calls)
        call_errors = sum(call.error is not None for call in self.llm_calls)
        call_errors += sum(call.success is False for call in self.tool_calls)
        errors = call_errors or int(self.error is not None)
        return {
            "run_id": self.run_id,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "steps": len(self.steps),
            "llm_calls": len(self.llm_calls),
            "tool_calls": len(self.tool_calls),
            "browser_calls": browser_calls,
            "retries": retries,
            "errors": errors,
        }

    def summary_text(self) -> str:
        summary = self.summary()
        duration = (summary["duration_ms"] or 0.0) / 1000
        return "\n".join(
            [
                f"Run: {self.run_id}",
                f"Status: {self.status}",
                f"Duration: {duration:.2f}s",
                f"Steps: {summary['steps']}",
                f"LLM Calls: {summary['llm_calls']}",
                f"Tool Calls: {summary['tool_calls']}",
                f"Browser Calls: {summary['browser_calls']}",
                f"Retries: {summary['retries']}",
                f"Errors: {summary['errors']}",
            ]
        )
