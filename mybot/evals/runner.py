from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from ..agent.context import ContextBuilder
from ..agent.loop import AgentLoop
from .assertions import (
    assert_expected_tools,
    assert_forbidden_tools,
    assert_max_steps,
    assert_must_contain,
    assert_must_not_contain,
)
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
        try:
            output, trace = await self.agent.run_traced(
                case.input,
                messages,
                browser_mode,
            )
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

        checks = {
            "run_status": trace.status == "success",
            "expected_tools": assert_expected_tools(
                trace,
                case.expected_tools,
            ),
            "forbidden_tools": assert_forbidden_tools(
                trace,
                case.forbidden_tools,
            ),
            "must_contain": assert_must_contain(output, case.must_contain),
            "must_not_contain": assert_must_not_contain(
                output,
                case.must_not_contain,
            ),
            "max_steps": assert_max_steps(trace, case.max_steps),
        }
        check_errors = self._check_errors(case, trace, output, checks)
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
        trace,
        output: str,
        checks: dict[str, bool],
    ) -> dict[str, str]:
        called = {call.tool_name for call in trace.tool_calls}
        errors: dict[str, str] = {}
        if not checks["run_status"]:
            errors["run_status"] = f"run ended with status {trace.status}"
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
                f"used {len(trace.steps)} steps, maximum is {case.max_steps}"
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
