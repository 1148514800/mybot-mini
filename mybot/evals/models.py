from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EvalCase:
    id: str
    name: str
    input: str
    expected_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    max_steps: int | None = None
    follow_up_inputs: list[str] = field(default_factory=list)
    follow_up_session_keys: list[str] = field(default_factory=list)
    expected_status: str = "success"
    expected_policy_decisions: list[str] = field(default_factory=list)
    expected_risk_levels: list[str] = field(default_factory=list)
    expected_approval_statuses: list[str] = field(default_factory=list)
    expected_tool_executions: int | None = None
    expected_tool_call_counts: dict[str, int] = field(default_factory=dict)
    expected_tool_execution_counts: dict[str, int] = field(default_factory=dict)
    expected_shared_task_id: bool = False
    expected_trace_metadata: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalCase:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            input=str(data["input"]),
            expected_tools=list(data.get("expected_tools", [])),
            forbidden_tools=list(data.get("forbidden_tools", [])),
            must_contain=list(data.get("must_contain", [])),
            must_not_contain=list(data.get("must_not_contain", [])),
            max_steps=data.get("max_steps"),
            follow_up_inputs=list(data.get("follow_up_inputs", [])),
            follow_up_session_keys=list(
                data.get("follow_up_session_keys", [])
            ),
            expected_status=str(data.get("expected_status", "success")),
            expected_policy_decisions=list(
                data.get("expected_policy_decisions", [])
            ),
            expected_risk_levels=list(data.get("expected_risk_levels", [])),
            expected_approval_statuses=list(
                data.get("expected_approval_statuses", [])
            ),
            expected_tool_executions=data.get("expected_tool_executions"),
            expected_tool_call_counts={
                str(key): int(value)
                for key, value in dict(
                    data.get("expected_tool_call_counts", {})
                ).items()
            },
            expected_tool_execution_counts={
                str(key): int(value)
                for key, value in dict(
                    data.get("expected_tool_execution_counts", {})
                ).items()
            },
            expected_shared_task_id=bool(
                data.get("expected_shared_task_id", False)
            ),
            expected_trace_metadata={
                str(key): [str(item) for item in values]
                for key, values in dict(
                    data.get("expected_trace_metadata", {})
                ).items()
            },
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class EvalResult:
    case_id: str
    passed: bool
    checks: dict[str, bool]
    run_id: str | None = None
    duration_ms: float = 0.0
    error: str | None = None
    check_errors: dict[str, str] = field(default_factory=dict)
