import unittest

from mybot.evals.assertions import (
    assert_expected_tools,
    assert_forbidden_tools,
    assert_max_steps,
    assert_must_contain,
    assert_must_not_contain,
)
from mybot.tracing.models import AgentRunTrace, AgentStepTrace, ToolCallTrace


class EvalAssertionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace = AgentRunTrace(
            run_id="run-1",
            started_at="now",
            user_input="hello",
            status="success",
            steps=[AgentStepTrace("step-1", 1, "now", status="success")],
            tool_calls=[
                ToolCallTrace(
                    call_id="tool-1",
                    step_id="step-1",
                    tool_name="read_file",
                    arguments={},
                    started_at="now",
                    success=True,
                )
            ],
        )

    def test_expected_and_forbidden_tool_assertions(self) -> None:
        self.assertTrue(assert_expected_tools(self.trace, ["read_file"]))
        self.assertFalse(assert_expected_tools(self.trace, ["exec"]))
        self.assertTrue(assert_forbidden_tools(self.trace, ["exec"]))
        self.assertFalse(assert_forbidden_tools(self.trace, ["read_file"]))

    def test_output_and_step_assertions(self) -> None:
        output = "task completed"
        self.assertTrue(assert_must_contain(output, ["completed"]))
        self.assertFalse(assert_must_contain(output, ["failed"]))
        self.assertTrue(assert_must_not_contain(output, ["failed"]))
        self.assertFalse(assert_must_not_contain(output, ["task"]))
        self.assertTrue(assert_max_steps(self.trace, 1))
        self.assertFalse(assert_max_steps(self.trace, 0))


if __name__ == "__main__":
    unittest.main()
