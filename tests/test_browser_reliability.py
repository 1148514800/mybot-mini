import unittest

from mybot.agent.browser_reliability import (
    BrowserTaskBudget,
    BrowserTaskState,
    is_recent_task_continuation,
)
from mybot.tools.result import BrowserResult


def browser_result(success=True, error=None, **metadata):
    return BrowserResult(
        success=success,
        action="click",
        session="managed_browser",
        output="ok" if success else "",
        error=error,
        metadata=metadata,
    )


class BrowserTaskStateTests(unittest.TestCase):
    def test_final_action_requires_explicit_postcondition(self):
        state = BrowserTaskState()
        state.note_result(
            "browser_click",
            {"target": "#submit"},
            browser_result(),
        )

        self.assertEqual(state.completion_state, "verification_required")
        self.assertIn("browser_verify", state.completion_block_reason())

        state.note_result(
            "browser_verify",
            {"text": "Saved"},
            browser_result(),
        )
        self.assertEqual(state.completion_state, "verified")
        self.assertIsNone(state.completion_block_reason())

    def test_same_failed_action_only_gets_one_retry(self):
        state = BrowserTaskState()
        budget = BrowserTaskBudget(max_failed_action_retries=1)
        args = {"target": "e12"}
        failed = browser_result(
            False,
            "Ref e12 not found",
            error_type="stale_target",
            recoverable=True,
        )

        state.note_result("browser_click", args, failed)
        self.assertIsNone(state.preflight("browser_click", args, budget))
        state.note_result("browser_click", args, failed)

        blocked = state.preflight("browser_click", args, budget)
        self.assertFalse(blocked.success)
        self.assertEqual(blocked.metadata["error_type"], "budget_exceeded")

    def test_syntax_error_blocks_identical_action_immediately(self):
        state = BrowserTaskState()
        args = {"selector": "["}
        state.note_result(
            "browser_inspect",
            args,
            browser_result(
                False,
                "Invalid selector",
                error_type="tool_syntax_error",
                recoverable=False,
            ),
        )

        blocked = state.preflight(
            "browser_inspect",
            args,
            BrowserTaskBudget(),
        )
        self.assertFalse(blocked.success)
        self.assertEqual(
            blocked.metadata["budget_rule"],
            "non_recoverable_action_repeat",
        )

    def test_browser_open_attempt_is_limited_to_one(self):
        state = BrowserTaskState()
        failed = browser_result(
            False,
            "open failed",
            error_type="unknown",
            recoverable=False,
        )
        state.note_result("browser_open", {}, failed)

        blocked = state.preflight("browser_open", {}, BrowserTaskBudget())

        self.assertFalse(blocked.success)
        self.assertEqual(blocked.metadata["budget_rule"], "browser_open_budget")

    def test_continuation_intent_is_deterministic(self):
        self.assertTrue(is_recent_task_continuation("你没有完成，刚才没点成功"))
        self.assertTrue(is_recent_task_continuation("继续"))
        self.assertFalse(is_recent_task_continuation("帮我查明天的天气"))


if __name__ == "__main__":
    unittest.main()
