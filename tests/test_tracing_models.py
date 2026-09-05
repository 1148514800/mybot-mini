import unittest

from mybot.tracing.models import (
    AgentRunTrace,
    AgentStepTrace,
    LLMCallTrace,
    ToolCallTrace,
)


class TracingModelTests(unittest.TestCase):
    def test_run_summary_counts_steps_calls_retries_and_errors(self) -> None:
        trace = AgentRunTrace(
            run_id="run-1",
            started_at="2026-01-01T00:00:00+00:00",
            finished_at="2026-01-01T00:00:01+00:00",
            duration_ms=1000,
            status="success",
            user_input="open a page",
            steps=[
                AgentStepTrace(
                    step_id="step-1",
                    step_index=1,
                    started_at="2026-01-01T00:00:00+00:00",
                    status="success",
                )
            ],
            llm_calls=[
                LLMCallTrace(
                    call_id="llm-1",
                    step_id="step-1",
                    started_at="2026-01-01T00:00:00+00:00",
                    model="fake",
                    provider="fake",
                    message_count=1,
                    retry_count=1,
                )
            ],
            tool_calls=[
                ToolCallTrace(
                    call_id="tool-1",
                    step_id="step-1",
                    tool_name="browser_open",
                    arguments={},
                    started_at="2026-01-01T00:00:00+00:00",
                    success=False,
                    error="failed",
                )
            ],
        )

        summary = trace.summary()

        self.assertEqual(summary["steps"], 1)
        self.assertEqual(summary["llm_calls"], 1)
        self.assertEqual(summary["tool_calls"], 1)
        self.assertEqual(summary["browser_calls"], 1)
        self.assertEqual(summary["retries"], 1)
        self.assertEqual(summary["errors"], 1)
        self.assertEqual(summary["runtime_status"], "success")
        self.assertIsNone(summary["task_status"])
        self.assertIn("Duration: 1.00s", trace.summary_text())


if __name__ == "__main__":
    unittest.main()
