import asyncio
import unittest
from pathlib import Path

from mybot.evals.fakes import build_fake_agent
from mybot.evals.models import EvalCase
from mybot.evals.reporter import format_eval_report
from mybot.evals.runner import EvalRunner, load_eval_suite


class EvalRunnerTests(unittest.TestCase):
    def passing_case(self) -> EvalCase:
        return EvalCase(
            id="fake-1",
            name="Fake read",
            input="read a file",
            expected_tools=["read_file"],
            forbidden_tools=["exec"],
            must_contain=["done"],
            must_not_contain=["failed"],
            max_steps=3,
            metadata={
                "category": "unit",
                "fake_tools": [
                    {
                        "name": "read_file",
                        "arguments": {"path": "README.md"},
                        "output": "MyBot",
                    }
                ],
                "fake_output": "done",
            },
        )

    def test_fake_llm_eval_produces_trace_and_passes_checks(self) -> None:
        case = self.passing_case()
        result = asyncio.run(EvalRunner(build_fake_agent(case)).run_case(case))

        self.assertTrue(result.passed)
        self.assertTrue(all(result.checks.values()))
        self.assertIsNotNone(result.run_id)

    def test_failed_assertion_is_reported_deterministically(self) -> None:
        case = self.passing_case()
        case.must_contain = ["missing phrase"]
        result = asyncio.run(EvalRunner(build_fake_agent(case)).run_case(case))

        self.assertFalse(result.passed)
        self.assertFalse(result.checks["must_contain"])
        self.assertIn("missing phrase", result.check_errors["must_contain"])

        report = format_eval_report([result], [case])
        self.assertIn("Failed:       1", report)
        self.assertIn("fake-1", report)

    def test_project_eval_suite_contains_twelve_offline_cases(self) -> None:
        eval_dir = Path(__file__).resolve().parents[1] / "evals"
        cases = load_eval_suite(eval_dir)

        self.assertEqual(len(cases), 12)
        self.assertTrue(all("fake_output" in case.metadata for case in cases))


if __name__ == "__main__":
    unittest.main()
