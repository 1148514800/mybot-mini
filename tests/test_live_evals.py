from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from mybot.evals.live import (
    BROWSER_OPT_IN,
    LIVE_OPT_IN,
    LiveEvalCase,
    LiveEvalResult,
    _make_context,
    format_live_report,
    run_live_suite,
)


class LiveEvalHarnessTests(unittest.TestCase):
    def test_live_suite_is_opt_in_and_does_not_need_api_key(self) -> None:
        results = asyncio.run(run_live_suite(environ={}))

        self.assertEqual(len(results), 6)
        self.assertTrue(all(item.status == "skip" for item in results))
        self.assertTrue(all(LIVE_OPT_IN in (item.failure_reason or "") for item in results))

    def test_opt_in_without_key_is_explicit_environment_skip(self) -> None:
        results = asyncio.run(run_live_suite(environ={LIVE_OPT_IN: "1"}))

        self.assertTrue(all(item.status == "skip" for item in results))
        self.assertTrue(all("no API key" in (item.failure_reason or "") for item in results))

    def test_browser_is_skipped_without_browser_opt_in(self) -> None:
        browser_case = LiveEvalCase("browser_live", lambda context: None, browser=True)
        results = asyncio.run(
            run_live_suite(
                environ={LIVE_OPT_IN: "1", "OPENAI_API_KEY": "test-key"},
                cases=[browser_case],
            )
        )

        self.assertEqual(results[0].status, "skip")
        self.assertIn(BROWSER_OPT_IN, results[0].failure_reason or "")

    def test_report_and_public_result_are_safe_and_locatable(self) -> None:
        result = LiveEvalResult(
            name="read_file_tool",
            status="fail",
            provider="openai-compatible",
            model="test-model",
            task_id="task-1",
            run_id="run-1",
            tool_calls=["read_file"],
            failure_reason="model behavior: expected read_file",
        )

        report = format_live_report([result])
        self.assertIn("Live E2E: 0/1 passed", report)
        self.assertIn("FAIL read_file_tool", report)
        self.assertIn("model behavior", report)
        public = result.public_dict()
        self.assertEqual(public["task_id"], "task-1")
        self.assertNotIn("arguments", public)

    def test_restart_context_inherits_provider_and_model_configuration(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory(prefix="mybot-live-config-") as directory:
                workspace = Path(directory)
                first = await _make_context(
                    workspace,
                    key="custom-key",
                    base_url="https://provider.example/v1",
                    provider="custom-provider",
                    model="custom-model",
                    max_react_steps=7,
                    max_context_chars=1234,
                    max_tool_result_chars=567,
                )
                source = first.config
                second = await _make_context(
                    workspace,
                    key="ignored-key",
                    base_url="https://ignored.example/v1",
                    provider="ignored-provider",
                    model="ignored-model",
                    source_config=source,
                )
                try:
                    for name in (
                        "provider",
                        "model",
                        "api_key",
                        "base_url",
                        "max_react_steps",
                        "max_context_chars",
                        "max_recent_messages",
                        "max_tool_result_chars",
                        "max_memory_chars",
                        "max_completion_tokens",
                        "rate_limit_retries",
                        "request_timeout_seconds",
                    ):
                        self.assertEqual(
                            getattr(second.config, name),
                            getattr(source, name),
                            name,
                        )
                finally:
                    await second.close()
                    await first.close()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
