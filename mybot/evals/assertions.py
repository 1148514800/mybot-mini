from __future__ import annotations

from ..tracing.models import AgentRunTrace


def _called_tools(trace: AgentRunTrace) -> list[str]:
    return [call.tool_name for call in trace.tool_calls]


def assert_expected_tools(
    trace: AgentRunTrace,
    expected_tools: list[str],
) -> bool:
    called = set(_called_tools(trace))
    return all(tool in called for tool in expected_tools)


def assert_forbidden_tools(
    trace: AgentRunTrace,
    forbidden_tools: list[str],
) -> bool:
    called = set(_called_tools(trace))
    return all(tool not in called for tool in forbidden_tools)


def assert_must_contain(output: str, expected: list[str]) -> bool:
    return all(fragment in output for fragment in expected)


def assert_must_not_contain(output: str, forbidden: list[str]) -> bool:
    return all(fragment not in output for fragment in forbidden)


def assert_max_steps(trace: AgentRunTrace, max_steps: int | None) -> bool:
    return max_steps is None or len(trace.steps) <= max_steps


def assert_trace_metadata_values(
    trace: AgentRunTrace,
    key: str,
    expected: list[str],
) -> bool:
    observed = {
        str(call.metadata[key])
        for call in trace.tool_calls
        if key in call.metadata
    }
    return all(value in observed for value in expected)
