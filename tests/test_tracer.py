import unittest

from mybot.tools.result import BrowserResult
from mybot.tracing.tracer import (
    REDACTED,
    RESULT_PREVIEW_MAX_CHARS,
    AgentTracer,
    redact_mapping,
    redact_text,
)


class AgentTracerTests(unittest.TestCase):
    def test_run_start_and_finish_populate_ids_and_duration(self) -> None:
        tracer = AgentTracer()

        run = tracer.start_run("hello")
        finished = tracer.finish_run("world")

        self.assertEqual(run.run_id, finished.run_id)
        self.assertEqual(len(run.run_id), 32)
        self.assertEqual(finished.status, "success")
        self.assertEqual(finished.final_output, "world")
        self.assertIsNotNone(finished.finished_at)
        self.assertGreaterEqual(finished.duration_ms, 0)

    def test_failed_run_closes_unfinished_step_and_llm_call(self) -> None:
        tracer = AgentTracer()
        tracer.start_run("hello")
        step = tracer.start_step(1)
        call = tracer.start_llm_call(
            step_id=step.step_id,
            model="fake",
            provider="fake",
            message_count=1,
        )

        run = tracer.finish_run(status="failed", error="unexpected")

        self.assertEqual(run.status, "failed")
        self.assertEqual(step.status, "failed")
        self.assertIsNotNone(step.finished_at)
        self.assertEqual(call.error, "unexpected")
        self.assertIsNotNone(call.finished_at)

    def test_llm_and_browser_tool_trace_records_structured_metadata(self) -> None:
        tracer = AgentTracer()
        tracer.start_run("open page")
        step = tracer.start_step(1)
        llm_call = tracer.start_llm_call(
            step_id=step.step_id,
            model="fake-model",
            provider="fake-provider",
            message_count=2,
        )
        tracer.finish_llm_call(
            llm_call,
            finish_reason="tool_calls",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
        tool_call = tracer.start_tool_call(
            step_id=step.step_id,
            tool_name="browser_snapshot",
            arguments={"session": "managed_browser", "api_key": "secret"},
        )
        result = BrowserResult(
            success=True,
            action="snapshot",
            session="managed_browser",
            output="x" * (RESULT_PREVIEW_MAX_CHARS + 100),
            metadata={"cookie": "secret", "depth": 8},
        )
        tracer.finish_tool_call(tool_call, result)
        tracer.finish_step()
        run = tracer.finish_run("done")

        self.assertEqual(llm_call.total_tokens, 15)
        self.assertEqual(tool_call.arguments["api_key"], REDACTED)
        self.assertEqual(tool_call.metadata["cookie"], REDACTED)
        self.assertEqual(tool_call.metadata["action"], "snapshot")
        self.assertEqual(tool_call.result_type, "BrowserResult")
        self.assertLessEqual(
            len(tool_call.result_preview),
            RESULT_PREVIEW_MAX_CHARS,
        )
        self.assertEqual(run.steps[0].tool_call_ids, [tool_call.call_id])

    def test_redaction_handles_nested_mappings_and_common_text_secrets(self) -> None:
        value = redact_mapping(
            {
                "nested": {
                    "password": "p1",
                    "Authorization": "Bearer token",
                },
                "safe": "visible",
            }
        )

        self.assertEqual(value["nested"]["password"], REDACTED)
        self.assertEqual(value["nested"]["Authorization"], REDACTED)
        self.assertEqual(value["safe"], "visible")
        self.assertNotIn(
            "abc123",
            redact_text('api_key="abc123"'),
        )


if __name__ == "__main__":
    unittest.main()
