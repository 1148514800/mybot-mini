from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mybot.agent.context import BROWSER_MODE_MANAGED
from mybot.agent.loop import AgentLoop
from mybot.evals.fakes import FakeToolRegistry, build_fake_agent
from mybot.evals.models import EvalCase
from mybot.messaging import InboundMessage
from mybot.storage.session import SessionManager


def case(fake_tools, *, batches=None, output="done", max_steps=None):
    metadata = {"fake_tools": fake_tools, "fake_output": output}
    if batches is not None:
        metadata["fake_tool_batches"] = batches
    return EvalCase(
        id="browser-reliability",
        name="browser reliability",
        input="browser task",
        max_steps=max_steps,
        metadata=metadata,
    )


class AgentBrowserReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_final_click_cannot_report_success(self):
        click = {
            "name": "browser_click",
            "arguments": {"target": "e12"},
            "success": False,
            "error": "click failed",
            "result_metadata": {
                "error_type": "unknown",
                "recoverable": False,
            },
        }
        agent = build_fake_agent(case([click], output="已完成"))

        output, trace = await agent.run_traced(
            "点击提交",
            [{"role": "user", "content": "点击提交"}],
            session_key="cli:a",
        )

        self.assertEqual(trace.status, "failed")
        self.assertNotIn("已完成", output)
        self.assertIn("尚未完成", output)
        self.assertEqual(
            trace.metadata["browser_completion_state"],
            "final_action_failed",
        )

    async def test_final_action_and_postcondition_allow_success(self):
        tools = [
            {
                "name": "browser_click",
                "arguments": {"target": "#submit"},
                "output": "clicked",
            },
            {
                "name": "browser_verify",
                "arguments": {"text": "Saved"},
                "output": "postcondition_met=true",
            },
        ]
        agent = build_fake_agent(case(tools, output="任务已完成"))

        output, trace = await agent.run_traced(
            "提交表单",
            [{"role": "user", "content": "提交表单"}],
            session_key="cli:a",
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(output, "任务已完成")
        self.assertTrue(trace.metadata["completion_verified"])
        self.assertEqual(trace.metadata["browser_completion_state"], "verified")

    async def test_stale_target_refreshes_snapshot_and_retries_once(self):
        open_call = {
            "name": "browser_open",
            "arguments": {},
            "output": "opened",
        }
        stale_click = {
            "name": "browser_click",
            "arguments": {"target": "e12"},
            "success": False,
            "error": "Ref e12 not found in current page snapshot",
            "result_metadata": {
                "error_type": "stale_target",
                "recoverable": True,
            },
        }
        refresh = {
            "name": "browser_snapshot",
            "arguments": {},
            "output": "button Save [ref=e44]",
        }
        retry_click = {
            "name": "browser_click",
            "arguments": {"target": "e44"},
            "output": "clicked",
        }
        verify = {
            "name": "browser_verify",
            "arguments": {"text": "Saved"},
            "output": "postcondition_met=true",
        }
        agent = build_fake_agent(
            case(
                [open_call, stale_click, refresh, retry_click, verify],
                batches=[
                    [open_call],
                    [stale_click],
                    [retry_click],
                    [verify],
                ],
                output="保存成功",
            )
        )

        output, trace = await agent.run_traced(
            "保存设置",
            [{"role": "user", "content": "保存设置"}],
            session_key="cli:a",
        )

        self.assertEqual(trace.status, "success")
        self.assertEqual(output, "保存成功")
        self.assertEqual(
            [name for name, _ in agent.tools.executed_calls],
            [
                "browser_open",
                "browser_click",
                "browser_snapshot",
                "browser_click",
                "browser_verify",
            ],
        )
        stale_trace = next(
            call
            for call in trace.tool_calls
            if call.tool_name == "browser_click" and call.success is False
        )
        self.assertEqual(stale_trace.metadata["recovery_action"], "browser_snapshot")
        self.assertTrue(stale_trace.metadata["recovery_succeeded"])
        recovery_trace = next(
            call
            for call in trace.tool_calls
            if call.tool_name == "browser_snapshot"
        )
        self.assertTrue(recovery_trace.metadata["runtime_recovery"])
        self.assertEqual(recovery_trace.metadata["recovery_for"], "browser_click")

    async def test_repeated_syntax_failure_is_stopped_by_budget(self):
        inspect = {
            "name": "browser_inspect",
            "arguments": {"selector": "["},
            "success": False,
            "error": "SyntaxError: invalid selector",
            "result_metadata": {
                "error_type": "tool_syntax_error",
                "recoverable": False,
            },
        }
        agent = build_fake_agent(
            case(
                [inspect],
                batches=[[inspect], [inspect]],
                output="已完成",
                max_steps=4,
            )
        )

        output, trace = await agent.run_traced(
            "查询页面",
            [{"role": "user", "content": "查询页面"}],
            session_key="cli:a",
        )

        self.assertEqual(trace.status, "failed")
        self.assertEqual(agent.tools.execution_count, 1)
        self.assertTrue(
            any(
                call.metadata.get("budget_rule")
                == "non_recoverable_action_repeat"
                for call in trace.tool_calls
            )
        )
        self.assertNotIn("已完成", output)


def tool_response(call_id, name, arguments):
    call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments),
        ),
    )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[call]),
                finish_reason="tool_calls",
            )
        ]
    )


def final_response(content):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=None),
                finish_reason="stop",
            )
        ]
    )


class ExplicitCompletions:
    def __init__(self, responses):
        self.responses = iter(responses)

    async def create(self, **kwargs):
        return next(self.responses)


class CountingContext:
    def __init__(self):
        self.build_count = 0

    def build_messages(self, history, content):
        self.build_count += 1
        return [{"role": "user", "content": content}]

    def resolve_browser_mode(self, content):
        return BROWSER_MODE_MANAGED


class RecentTaskContinuationTests(unittest.IsolatedAsyncioTestCase):
    async def test_correction_reuses_task_browser_and_loaded_skill(self):
        open_call = {"name": "browser_open", "arguments": {}, "output": "opened"}
        skill_call = {
            "name": "read_file",
            "arguments": {"path": "skills/playwright-cli/SKILL.md"},
            "output": "skill instructions",
        }
        inspect_call = {
            "name": "browser_inspect",
            "arguments": {"text": "Result"},
            "output": "Result found",
        }
        completions = ExplicitCompletions(
            [
                tool_response("open-1", "browser_open", {}),
                tool_response(
                    "skill-1",
                    "read_file",
                    {"path": "skills/playwright-cli/SKILL.md"},
                ),
                final_response("初次检查完成"),
                tool_response("open-2", "browser_open", {}),
                tool_response(
                    "skill-2",
                    "read_file",
                    {"path": "skills/playwright-cli/SKILL.md"},
                ),
                tool_response("inspect-1", "browser_inspect", {"text": "Result"}),
                final_response("已继续检查"),
            ]
        )
        config = SimpleNamespace(
            model="fake",
            provider="fake",
            max_completion_tokens=100,
            max_react_steps=10,
            rate_limit_retries=0,
            request_timeout_seconds=60,
            show_internal_process=False,
        )
        tools = FakeToolRegistry([open_call, skill_call, inspect_call])
        context = CountingContext()
        with tempfile.TemporaryDirectory() as directory:
            agent = AgentLoop(
                SimpleNamespace(
                    chat=SimpleNamespace(completions=completions)
                ),
                config,
                None,
                tools,
                context,
                SessionManager(Path(directory)),
            )
            _, first = await agent.handle_inbound_message(
                InboundMessage("cli", "user", "a", "打开页面检查结果")
            )
            output, resumed = await agent.handle_inbound_message(
                InboundMessage("cli", "user", "a", "你没有完成，继续")
            )

        self.assertEqual(first.status, "success")
        self.assertEqual(resumed.status, "success")
        self.assertEqual(output, "已继续检查")
        self.assertEqual(first.metadata["task_id"], resumed.metadata["task_id"])
        self.assertTrue(resumed.metadata["continuation"])
        self.assertEqual(context.build_count, 1)
        self.assertEqual(
            [name for name, _ in tools.executed_calls],
            ["browser_open", "read_file", "browser_inspect"],
        )
        skipped = {
            call.tool_name: call.metadata.get("execution_skipped")
            for call in resumed.tool_calls
        }
        self.assertEqual(skipped["browser_open"], "browser_already_initialized")
        self.assertEqual(skipped["read_file"], "skill_already_loaded")


if __name__ == "__main__":
    unittest.main()
