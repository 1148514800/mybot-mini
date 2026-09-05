import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mybot.agent.context import BROWSER_MODE_LOCAL, BROWSER_MODE_MANAGED
from mybot.agent.loop import AgentLoop
from mybot.tools.result import ToolResult


def tool_call(call_id: str, name: str, arguments: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )


def response_with_tool(call_id: str) -> SimpleNamespace:
    message = SimpleNamespace(
        content=None,
        tool_calls=[tool_call(call_id, "browser_snapshot", {"session": "test"})],
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")]
    )


class FakeCompletions:
    def __init__(self, responses: list[SimpleNamespace]):
        self._responses = iter(responses)

    async def create(self, **kwargs) -> SimpleNamespace:
        return next(self._responses)


class SlowCompletions:
    async def create(self, **kwargs) -> SimpleNamespace:
        await asyncio.sleep(60)
        raise AssertionError("unreachable")


class AgentLoopTests(unittest.TestCase):
    def build_loop(self, responses: list[SimpleNamespace]) -> AgentLoop:
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions(responses))
        )
        config = SimpleNamespace(
            model="test-model",
            max_completion_tokens=100,
            max_react_steps=200000,
            rate_limit_retries=20000,
            request_timeout_seconds=60,
            show_internal_process=False,
        )
        tools = SimpleNamespace(
            get_definitions=lambda: [
                {
                    "type": "function",
                    "function": {"name": "browser_attach"},
                },
                {
                    "type": "function",
                    "function": {"name": "browser_open"},
                },
                {
                    "type": "function",
                    "function": {"name": "browser_snapshot"},
                },
            ],
            execute=AsyncMock(return_value=ToolResult(success=True, output="ok")),
        )
        return AgentLoop(client, config, None, tools, None, None)

    def test_managed_mode_hides_attach_and_local_mode_hides_open(self) -> None:
        loop = self.build_loop([])

        managed_names = {
            item["function"]["name"]
            for item in loop._tool_definitions_for_browser_mode(
                BROWSER_MODE_MANAGED
            )
        }
        local_names = {
            item["function"]["name"]
            for item in loop._tool_definitions_for_browser_mode(BROWSER_MODE_LOCAL)
        }

        self.assertEqual(managed_names, {"browser_open", "browser_snapshot"})
        self.assertEqual(local_names, {"browser_attach", "browser_snapshot"})

    def test_browser_session_is_forced_to_current_request_mode(self) -> None:
        loop = self.build_loop([])
        call = tool_call(
            "call-1",
            "browser_snapshot",
            {"session": "local_browser"},
        )

        result = asyncio.run(
            loop._execute_tool_call(call, BROWSER_MODE_MANAGED)
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "ok")
        loop.tools.execute.assert_awaited_once_with(
            "browser_snapshot",
            {"session": "managed_browser"},
        )

    def test_wrong_browser_entry_tool_is_blocked_at_execution(self) -> None:
        loop = self.build_loop([])

        managed_result = asyncio.run(
            loop._execute_tool_call(
                tool_call("call-1", "browser_attach", {}),
                BROWSER_MODE_MANAGED,
            )
        )
        local_result = asyncio.run(
            loop._execute_tool_call(
                tool_call("call-2", "browser_open", {}),
                BROWSER_MODE_LOCAL,
            )
        )

        self.assertIn("browser_attach is blocked", managed_result.error)
        self.assertIn("browser_open is blocked", local_result.error)
        loop.tools.execute.assert_not_awaited()

    def test_configured_limits_are_hard_capped(self) -> None:
        loop = self.build_loop([])

        self.assertEqual(loop._effective_react_steps(), 30)
        self.assertEqual(loop._effective_rate_limit_retries(), 10)

    def test_llm_timeout_returns_stable_error_and_finishes_trace(self) -> None:
        loop = self.build_loop([])
        loop.client.chat.completions = SlowCompletions()
        loop.config.request_timeout_seconds = 0.01

        output, trace = asyncio.run(
            loop.run_traced(
                "hello",
                [{"role": "user", "content": "hello"}],
            )
        )

        self.assertEqual(output, "LLM request timeout after 0.01s")
        self.assertEqual(trace.status, "failed")
        self.assertEqual(trace.error, output)
        self.assertEqual(trace.steps[0].status, "failed")
        self.assertEqual(trace.llm_calls[0].error, output)

    def test_third_consecutive_identical_tool_call_is_blocked(self) -> None:
        final_message = SimpleNamespace(content="done", tool_calls=None)
        responses = [
            response_with_tool("call-1"),
            response_with_tool("call-2"),
            response_with_tool("call-3"),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=final_message,
                        finish_reason="stop",
                    )
                ]
            ),
        ]
        loop = self.build_loop(responses)

        result = asyncio.run(loop._react_loop([]))

        self.assertEqual(result, "done")
        self.assertEqual(loop.tools.execute.await_count, 2)

    def test_tool_result_is_serialized_to_string_for_model(self) -> None:
        final_message = SimpleNamespace(content="done", tool_calls=None)
        responses = [
            response_with_tool("call-1"),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(message=final_message, finish_reason="stop")
                ]
            ),
        ]
        loop = self.build_loop(responses)
        messages: list[dict] = []

        asyncio.run(loop._react_loop(messages))

        tool_message = next(
            message for message in messages if message["role"] == "tool"
        )
        self.assertEqual(tool_message["content"], "ok")
        self.assertIsInstance(tool_message["content"], str)

    def test_empty_final_message_has_fallback_text(self) -> None:
        final_message = SimpleNamespace(content=None, tool_calls=None)
        loop = self.build_loop(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=final_message,
                            finish_reason="stop",
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=final_message,
                            finish_reason="stop",
                        )
                    ]
                )
            ]
        )

        result = asyncio.run(loop._react_loop([]))

        self.assertIn("没有返回文本结果", result)

    def test_empty_response_is_retried_before_final_fallback(self) -> None:
        empty_message = SimpleNamespace(content=None, tool_calls=None)
        final_message = SimpleNamespace(content="继续完成了", tool_calls=None)
        loop = self.build_loop(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=empty_message,
                            finish_reason="stop",
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=final_message,
                            finish_reason="stop",
                        )
                    ]
                ),
            ]
        )

        result = asyncio.run(loop._react_loop([]))

        self.assertEqual(result, "继续完成了")

    def test_run_traced_records_llm_tool_and_successful_completion(self) -> None:
        final_message = SimpleNamespace(content="done", tool_calls=None)
        loop = self.build_loop(
            [
                response_with_tool("call-1"),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=final_message,
                            finish_reason="stop",
                        )
                    ],
                    usage=SimpleNamespace(
                        prompt_tokens=10,
                        completion_tokens=5,
                        total_tokens=15,
                    ),
                ),
            ]
        )

        output, trace = asyncio.run(
            loop.run_traced(
                "take a snapshot",
                [{"role": "user", "content": "take a snapshot"}],
            )
        )

        self.assertEqual(output, "done")
        self.assertEqual(trace.status, "success")
        self.assertEqual(trace.task_status, "completed")
        self.assertEqual(trace.task_id, trace.metadata["task_id"])
        self.assertEqual(len(trace.steps), 2)
        self.assertEqual(len(trace.llm_calls), 2)
        self.assertEqual(len(trace.tool_calls), 1)
        self.assertEqual(trace.tool_calls[0].tool_name, "browser_snapshot")

    def test_run_traced_marks_max_steps_without_changing_output(self) -> None:
        loop = self.build_loop([response_with_tool("call-1")])
        loop.config.max_react_steps = 1

        output, trace = asyncio.run(
            loop.run_traced(
                "take a snapshot",
                [{"role": "user", "content": "take a snapshot"}],
            )
        )

        self.assertIn("1 步执行上限", output)
        self.assertEqual(trace.status, "max_steps")
        self.assertEqual(trace.task_status, "max_steps")

    def test_unexpected_exception_finishes_run_and_open_trace_items(self) -> None:
        malformed_response = SimpleNamespace(choices=[])
        loop = self.build_loop([malformed_response])

        with self.assertRaises(IndexError):
            asyncio.run(
                loop.run_traced(
                    "hello",
                    [{"role": "user", "content": "hello"}],
                )
            )

        trace = loop.tracer.get_current_run()
        self.assertEqual(trace.status, "failed")
        self.assertEqual(trace.task_status, "failed")
        self.assertEqual(trace.steps[0].status, "failed")
        self.assertIsNotNone(trace.llm_calls[0].finished_at)


if __name__ == "__main__":
    unittest.main()
