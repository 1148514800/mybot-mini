import unittest

from mybot.evals.models import EvalCase, EvalResult


class EvalModelTests(unittest.TestCase):
    def test_eval_case_loads_optional_assertions(self) -> None:
        case = EvalCase.from_dict(
            {
                "id": "case-1",
                "name": "Example",
                "input": "hello",
                "expected_tools": ["read_file"],
                "must_contain": ["done"],
                "max_steps": 3,
            }
        )

        self.assertEqual(case.expected_tools, ["read_file"])
        self.assertEqual(case.forbidden_tools, [])
        self.assertEqual(case.max_steps, 3)

    def test_eval_result_stores_checks_and_run_identity(self) -> None:
        result = EvalResult(
            case_id="case-1",
            passed=True,
            checks={"expected_tools": True},
            run_id="run-1",
            duration_ms=12.5,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.run_id, "run-1")


if __name__ == "__main__":
    unittest.main()
