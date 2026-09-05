from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

from ..agent.context import ContextBuilder
from ..agent.loop import AgentLoop
from .assertions import (
    assert_expected_tools,
    assert_forbidden_tools,
    assert_max_steps,
    assert_must_contain,
    assert_must_not_contain,
    assert_trace_metadata_values,
)
from ..guardrails import ApprovalIntent, classify_approval_intent
from ..agent.browser_reliability import is_recent_task_continuation
from .fakes import build_fake_agent
from .models import EvalCase, EvalResult
from .reporter import format_eval_report


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_DIR = PROJECT_DIR / "evals"


def load_eval_cases(path: Path) -> list[EvalCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("cases", [])
    if not isinstance(data, list):
        raise ValueError(f"eval file must contain a list of cases: {path}")
    return [EvalCase.from_dict(item) for item in data]


def load_eval_suite(eval_dir: Path = DEFAULT_EVAL_DIR) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for path in sorted(eval_dir.glob("*.json")):
        cases.extend(load_eval_cases(path))
    return cases


class EvalRunner:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def run_case(self, case: EvalCase) -> EvalResult:
        started = time.perf_counter()
        messages = [{"role": "user", "content": case.input}]
        browser_mode = ContextBuilder.resolve_browser_mode(case.input)
        session_key = f"eval:{case.id}"
        traces = []
        try:
            output, trace = await self.agent.run_traced(
                case.input,
                messages,
                browser_mode,
                session_key=session_key,
            )
            traces.append(trace)
            for index, follow_up in enumerate(case.follow_up_inputs):
                follow_session = (
                    case.follow_up_session_keys[index]
                    if index < len(case.follow_up_session_keys)
                    else session_key
                )
                pending = self.agent.approvals.get(follow_session)
                pending_clarification = self.agent.clarifications.get(
                    follow_session
                )
                intent = classify_approval_intent(follow_up)
                if pending_clarification is not None:
                    output, trace = await self.agent.resume_clarification(
                        follow_session,
                        follow_up,
                    )
                elif pending and intent in {
                    ApprovalIntent.APPROVE,
                    ApprovalIntent.REJECT,
                }:
                    output, trace = await self.agent.resume_pending(
                        follow_session,
                        follow_up,
                    )
                elif pending:
                    self.agent.approvals.reject(
                        follow_session,
                        pending.approval_id,
                    )
                    output, trace = await self.agent.run_traced(
                        follow_up,
                        [{"role": "user", "content": follow_up}],
                        ContextBuilder.resolve_browser_mode(follow_up),
                        session_key=follow_session,
                        metadata={
                            "cancelled_approval_id": pending.approval_id
                        },
                    )
                elif (
                    is_recent_task_continuation(follow_up)
                    and self.agent.recent_tasks.get(follow_session) is not None
                ):
                    output, trace = await self.agent.resume_recent_task(
                        follow_session,
                        follow_up,
                    )
                elif intent in {
                    ApprovalIntent.APPROVE,
                    ApprovalIntent.REJECT,
                }:
                    output, trace = await self.agent.resume_pending(
                        follow_session,
                        follow_up,
                    )
                else:
                    output, trace = await self.agent.run_traced(
                        follow_up,
                        [{"role": "user", "content": follow_up}],
                        ContextBuilder.resolve_browser_mode(follow_up),
                        session_key=follow_session,
                    )
                traces.append(trace)
        except Exception as exc:
            trace = self.agent.tracer.get_current_run()
            return EvalResult(
                case_id=case.id,
                passed=False,
                checks={"run_status": False},
                run_id=trace.run_id if trace else None,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )

        combined_trace = SimpleNamespace(
            tool_calls=[call for item in traces for call in item.tool_calls],
            steps=[step for item in traces for step in item.steps],
        )
        call_counts = {
            name: sum(
                call.tool_name == name
                for call in combined_trace.tool_calls
            )
            for name in case.expected_tool_call_counts
        }
        execution_counts = {
            name: sum(
                executed_name == name
                for executed_name, _ in getattr(
                    self.agent.tools,
                    "executed_calls",
                    [],
                )
            )
            for name in case.expected_tool_execution_counts
        }
        task_ids = [
            item.metadata.get("task_id")
            for item in traces
            if item.metadata.get("task_id")
        ]
        checks = {
            "run_status": trace.status == case.expected_status,
            "expected_tools": assert_expected_tools(
                combined_trace,
                case.expected_tools,
            ),
            "forbidden_tools": assert_forbidden_tools(
                combined_trace,
                case.forbidden_tools,
            ),
            "must_contain": assert_must_contain(output, case.must_contain),
            "must_not_contain": assert_must_not_contain(
                output,
                case.must_not_contain,
            ),
            "max_steps": assert_max_steps(combined_trace, case.max_steps),
            "policy_decisions": assert_trace_metadata_values(
                combined_trace,
                "policy_decision",
                case.expected_policy_decisions,
            ),
            "risk_levels": assert_trace_metadata_values(
                combined_trace,
                "risk_level",
                case.expected_risk_levels,
            ),
            "approval_statuses": assert_trace_metadata_values(
                combined_trace,
                "approval_status",
                case.expected_approval_statuses,
            ),
            "tool_executions": (
                case.expected_tool_executions is None
                or getattr(self.agent.tools, "execution_count", None)
                == case.expected_tool_executions
            ),
            "tool_call_counts": all(
                call_counts[name] == expected
                for name, expected in case.expected_tool_call_counts.items()
            ),
            "tool_execution_counts": all(
                execution_counts[name] == expected
                for name, expected in (
                    case.expected_tool_execution_counts.items()
                )
            ),
            "shared_task_id": (
                not case.expected_shared_task_id
                or (
                    len(task_ids) == len(traces)
                    and len(set(task_ids)) == 1
                )
            ),
            "trace_metadata": all(
                assert_trace_metadata_values(
                    combined_trace,
                    key,
                    expected,
                )
                for key, expected in case.expected_trace_metadata.items()
            ),
        }
        check_errors = self._check_errors(
            case,
            combined_trace,
            trace,
            output,
            checks,
            call_counts,
            execution_counts,
            task_ids,
        )
        return EvalResult(
            case_id=case.id,
            passed=all(checks.values()),
            checks=checks,
            run_id=trace.run_id,
            duration_ms=(time.perf_counter() - started) * 1000,
            error=trace.error,
            check_errors=check_errors,
        )

    def _check_errors(
        self,
        case: EvalCase,
        combined_trace,
        final_trace,
        output: str,
        checks: dict[str, bool],
        call_counts: dict[str, int],
        execution_counts: dict[str, int],
        task_ids: list[str],
    ) -> dict[str, str]:
        called = {call.tool_name for call in combined_trace.tool_calls}
        errors: dict[str, str] = {}
        if not checks["run_status"]:
            errors["run_status"] = (
                f"run ended with status {final_trace.status}; "
                f"expected {case.expected_status}"
            )
        if not checks["expected_tools"]:
            missing = [tool for tool in case.expected_tools if tool not in called]
            errors["expected_tools"] = (
                f"expected tool(s) not called: {', '.join(missing)}"
            )
        if not checks["forbidden_tools"]:
            used = [tool for tool in case.forbidden_tools if tool in called]
            errors["forbidden_tools"] = (
                f"forbidden tool(s) called: {', '.join(used)}"
            )
        if not checks["must_contain"]:
            missing = [text for text in case.must_contain if text not in output]
            errors["must_contain"] = (
                f"final output missing: {', '.join(missing)}"
            )
        if not checks["must_not_contain"]:
            found = [text for text in case.must_not_contain if text in output]
            errors["must_not_contain"] = (
                f"final output contained forbidden text: {', '.join(found)}"
            )
        if not checks["max_steps"]:
            errors["max_steps"] = (
                f"used {len(combined_trace.steps)} steps, maximum is {case.max_steps}"
            )
        for check, expected in (
            ("policy_decisions", case.expected_policy_decisions),
            ("risk_levels", case.expected_risk_levels),
            ("approval_statuses", case.expected_approval_statuses),
        ):
            if not checks[check]:
                errors[check] = f"missing expected trace values: {expected}"
        if not checks["tool_executions"]:
            errors["tool_executions"] = (
                f"tool executed {getattr(self.agent.tools, 'execution_count', None)} "
                f"time(s); expected {case.expected_tool_executions}"
            )
        if not checks["tool_call_counts"]:
            errors["tool_call_counts"] = (
                f"tool call counts were {call_counts}; expected "
                f"{case.expected_tool_call_counts}"
            )
        if not checks["tool_execution_counts"]:
            errors["tool_execution_counts"] = (
                f"tool execution counts were {execution_counts}; expected "
                f"{case.expected_tool_execution_counts}"
            )
        if not checks["shared_task_id"]:
            errors["shared_task_id"] = (
                f"runs did not share one task_id: {task_ids}"
            )
        if not checks["trace_metadata"]:
            errors["trace_metadata"] = (
                "missing expected ToolCallTrace metadata: "
                f"{case.expected_trace_metadata}"
            )
        return errors

    async def run_cases(self, cases: list[EvalCase]) -> list[EvalResult]:
        return [await self.run_case(case) for case in cases]


async def _run_fake_suite(cases: list[EvalCase]) -> list[EvalResult]:
    results: list[EvalResult] = []
    for case in cases:
        runner = EvalRunner(build_fake_agent(case))
        results.append(await runner.run_case(case))
    return results


def main() -> int:
    cases = load_eval_suite()
    if not cases:
        print(f"No eval cases found in {DEFAULT_EVAL_DIR}")
        return 1
    results = asyncio.run(_run_fake_suite(cases))
    print(format_eval_report(results, cases))
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
