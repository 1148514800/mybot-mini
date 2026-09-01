from __future__ import annotations

from pathlib import Path

from .models import AgentRunTrace
from .serializer import load_trace


def replay_trace(trace: AgentRunTrace) -> str:
    """Render a trace timeline without invoking an LLM or a real tool."""
    llm_by_id = {call.call_id: call for call in trace.llm_calls}
    tools_by_id = {call.call_id: call for call in trace.tool_calls}
    lines = [f"RUN {trace.run_id} status={trace.status}"]

    for step in sorted(trace.steps, key=lambda item: item.step_index):
        duration = step.duration_ms or 0.0
        lines.extend(
            [
                "",
                f"STEP {step.step_index} status={step.status} duration={duration:.1f}ms",
            ]
        )
        llm_call = llm_by_id.get(step.llm_call_id or "")
        tool_calls = [
            tools_by_id[call_id]
            for call_id in step.tool_call_ids
            if call_id in tools_by_id
        ]
        targets = ", ".join(call.tool_name for call in tool_calls)
        if llm_call:
            lines.append(f"LLM -> {targets or 'final response'}")
        for call in tool_calls:
            call_duration = call.duration_ms or 0.0
            lines.extend(
                [
                    f"TOOL {call.tool_name}",
                    f"success={call.success} duration={call_duration:.1f}ms",
                ]
            )
            if call.error:
                lines.append(f"error={call.error}")
    return "\n".join(lines)


def replay_trace_file(path: Path) -> str:
    return replay_trace(load_trace(path))
