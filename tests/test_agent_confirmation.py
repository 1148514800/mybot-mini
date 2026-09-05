from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from mybot.agent.context import BROWSER_MODE_MANAGED
from mybot.evals.fakes import build_fake_agent
from mybot.evals.models import EvalCase
from mybot.guardrails import ApprovalManager
from mybot.messaging import InboundMessage
from mybot.storage.session import SessionManager
from mybot.tracing import REDACTED


def fake_case(command="rm -rf tests/output") -> EvalCase:
    return EvalCase(
        id="confirmation",
        name="confirmation",
        input="delete output",
        metadata={
            "fake_tools": [
                {
                    "name": "exec",
                    "arguments": {"command": command},
                    "output": "deleted",
                }
            ],
            "fake_output": "task complete",
        },
    )


class AgentConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmation_executes_exact_pending_call_once(self):
        agent = build_fake_agent(fake_case())
        output, first_trace = await agent.run_traced(
            "delete output",
            [{"role": "user", "content": "delete output"}],
            session_key="cli:a",
        )
        self.assertEqual(first_trace.status, "awaiting_confirmation")
        self.assertEqual(first_trace.task_status, "waiting_approval")
        self.assertIn("回复“确认”", output)
        self.assertEqual(agent.tools.execution_count, 0)

        pending = agent.approvals.get("cli:a")
        self.assertIsNotNone(pending)
        exact_arguments = dict(pending.arguments)
        final, resumed_trace = await agent.resume_pending("cli:a", "确认")

        self.assertEqual(final, "task complete")
        self.assertEqual(resumed_trace.status, "success")
        self.assertEqual(resumed_trace.task_status, "completed")
        self.assertEqual(agent.tools.execution_count, 1)
        self.assertEqual(agent.tools.executed_calls[0][1], exact_arguments)
        resumed_call = resumed_trace.tool_calls[0]
        self.assertEqual(resumed_call.metadata["approval_status"], "approved")
        self.assertEqual(
            resumed_call.metadata["approval_id"], pending.approval_id
        )
        self.assertEqual(
            resumed_trace.metadata["resumed_from_run_id"],
            first_trace.run_id,
        )
        self.assertEqual(
            resumed_trace.metadata["task_id"],
            first_trace.metadata["task_id"],
        )
        self.assertIsNone(agent.approvals.get("cli:a"))
        self.assertIsNone(agent.approvals.approve("cli:a", pending.approval_id))

    async def test_rejection_never_executes_tool(self):
        agent = build_fake_agent(fake_case())
        await agent.run_traced(
            "delete output",
            [{"role": "user", "content": "delete output"}],
            session_key="cli:a",
        )
        output, trace = await agent.resume_pending("cli:a", "取消")
        self.assertEqual(trace.status, "cancelled")
        self.assertIn("没有执行", output)
        self.assertEqual(agent.tools.execution_count, 0)

    async def test_other_session_cannot_approve(self):
        agent = build_fake_agent(fake_case())
        await agent.run_traced(
            "delete output",
            [{"role": "user", "content": "delete output"}],
            session_key="cli:a",
        )
        output, trace = await agent.resume_pending("cli:b", "确认")
        self.assertEqual(trace.status, "cancelled")
        self.assertIn("没有等待确认", output)
        self.assertEqual(agent.tools.execution_count, 0)
        self.assertIsNotNone(agent.approvals.get("cli:a"))

    async def test_new_task_cancels_pending_in_message_flow(self):
        agent = build_fake_agent(fake_case())
        with tempfile.TemporaryDirectory() as directory:
            agent.sessions = SessionManager(Path(directory))
            agent.context = SimpleNamespace(
                build_messages=lambda history, content: [
                    {"role": "user", "content": content}
                ],
                resolve_browser_mode=lambda content: BROWSER_MODE_MANAGED,
            )
            first = InboundMessage("cli", "user", "a", "delete output")
            _, first_trace = await agent.handle_inbound_message(first)
            self.assertEqual(first_trace.status, "awaiting_confirmation")

            second = InboundMessage("cli", "user", "a", "查看今天的日志")
            output, second_trace = await agent.handle_inbound_message(second)
            self.assertEqual(output, "task complete")
            self.assertEqual(second_trace.status, "success")
            self.assertIn("cancelled_approval_id", second_trace.metadata)
            self.assertEqual(agent.tools.execution_count, 0)
            self.assertIsNone(agent.approvals.get("cli:a"))

    async def test_only_original_group_sender_can_confirm(self):
        agent = build_fake_agent(fake_case("git push"))
        with tempfile.TemporaryDirectory() as directory:
            agent.sessions = SessionManager(Path(directory))
            agent.context = SimpleNamespace(
                build_messages=lambda history, content: [
                    {"role": "user", "content": content}
                ],
                resolve_browser_mode=lambda content: BROWSER_MODE_MANAGED,
            )
            first = InboundMessage(
                "feishu", "user-a", "group-1", "push changes"
            )
            _, first_trace = await agent.handle_inbound_message(first)
            pending = agent.approvals.get("feishu:group-1")
            self.assertEqual(first_trace.status, "awaiting_confirmation")
            self.assertEqual(pending.requester_sender_id, "user-a")

            denied, denied_trace = await agent.handle_inbound_message(
                InboundMessage("feishu", "user-b", "group-1", "确认")
            )
            self.assertIn("只能由原操作发起人确认", denied)
            self.assertEqual(
                denied_trace.metadata["approval_status"],
                "authorization_mismatch",
            )
            self.assertEqual(denied_trace.task_status, "waiting_approval")
            self.assertIs(agent.approvals.get("feishu:group-1"), pending)
            self.assertEqual(agent.tools.execution_count, 0)

            output, approved_trace = await agent.handle_inbound_message(
                InboundMessage("feishu", "user-a", "group-1", "确认")
            )

        self.assertEqual(output, "task complete")
        self.assertEqual(approved_trace.status, "success")
        self.assertEqual(agent.tools.execution_count, 1)
        self.assertIsNone(agent.approvals.get("feishu:group-1"))

    async def test_expired_message_flow_approval_does_not_execute(self):
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        agent = build_fake_agent(fake_case("git push"))
        agent.approvals = ApprovalManager(
            ttl_seconds=600,
            clock=lambda: now[0],
        )
        with tempfile.TemporaryDirectory() as directory:
            agent.sessions = SessionManager(Path(directory))
            agent.context = SimpleNamespace(
                build_messages=lambda history, content: [
                    {"role": "user", "content": content}
                ],
                resolve_browser_mode=lambda content: BROWSER_MODE_MANAGED,
            )
            await agent.handle_inbound_message(
                InboundMessage("cli", "user", "a", "push changes")
            )
            now[0] += timedelta(seconds=601)
            output, trace = await agent.handle_inbound_message(
                InboundMessage("cli", "user", "a", "确认")
            )

        self.assertIn("已经过期", output)
        self.assertEqual(trace.metadata["approval_status"], "expired")
        self.assertEqual(trace.task_status, "failed")
        self.assertEqual(agent.tools.execution_count, 0)
        self.assertIsNone(agent.approvals.get("cli:a"))

    async def test_blocked_command_never_reaches_registry(self):
        agent = build_fake_agent(fake_case("rm -rf /"))
        output, trace = await agent.run_traced(
            "destroy system",
            [{"role": "user", "content": "destroy system"}],
            session_key="cli:a",
        )
        self.assertEqual(output, "task complete")
        self.assertEqual(trace.status, "success")
        self.assertEqual(agent.tools.execution_count, 0)
        call = trace.tool_calls[0]
        self.assertEqual(call.metadata["policy_decision"], "block")
        self.assertEqual(call.metadata["risk_level"], "destructive")

    async def test_multi_tool_confirmation_is_execution_barrier(self):
        tools = [
            {
                "name": "read_file",
                "arguments": {"path": "README.md"},
                "output": "read",
            },
            {
                "name": "exec",
                "arguments": {"command": "rm tests/output.txt"},
                "output": "deleted",
            },
            {
                "name": "write_file",
                "arguments": {"path": "notes/after.txt", "content": "done"},
                "output": "written",
            },
        ]
        case = EvalCase(
            id="barrier",
            name="barrier",
            input="run batch",
            metadata={
                "fake_tools": tools,
                "fake_tool_batches": [tools],
                "fake_output": "batch complete",
            },
        )
        agent = build_fake_agent(case)
        _, trace = await agent.run_traced(
            case.input,
            [{"role": "user", "content": case.input}],
            session_key="cli:a",
        )
        self.assertEqual(trace.status, "awaiting_confirmation")
        self.assertEqual(agent.tools.execution_count, 1)
        self.assertEqual(agent.tools.executed_calls[0][0], "read_file")

        output, resumed = await agent.resume_pending("cli:a", "确认")
        self.assertEqual(output, "batch complete")
        self.assertEqual(resumed.status, "success")
        self.assertEqual(agent.tools.execution_count, 3)
        self.assertEqual(
            [name for name, _ in agent.tools.executed_calls],
            ["read_file", "exec", "write_file"],
        )

    async def test_confirmation_trace_and_redaction(self):
        case = EvalCase(
            id="redaction",
            name="redaction",
            input="run script",
            metadata={
                "fake_tools": [
                    {
                        "name": "browser_eval",
                        "arguments": {
                            "script": "token=raw-token; cookie=raw-cookie",
                            "password": "raw-password",
                            "api_key": "raw-api-key",
                            "secret": "raw-secret",
                        },
                        "output": "ok",
                    }
                ]
            },
        )
        agent = build_fake_agent(case)
        prompt, trace = await agent.run_traced(
            case.input,
            [{"role": "user", "content": case.input}],
            session_key="cli:a",
        )
        call = trace.tool_calls[0]
        self.assertEqual(call.metadata["policy_decision"], "require_confirmation")
        self.assertEqual(call.metadata["risk_level"], "sensitive")
        self.assertEqual(call.metadata["approval_status"], "pending")
        self.assertTrue(call.metadata["approval_id"])
        self.assertIn("Arguments:", prompt)
        serialized = json.dumps(call.arguments)
        for secret in (
            "raw-token",
            "raw-cookie",
            "raw-password",
            "raw-api-key",
            "raw-secret",
        ):
            self.assertNotIn(secret, serialized)
            self.assertNotIn(secret, prompt)
        self.assertIn(REDACTED, serialized)

    async def test_browser_type_preview_and_trace_hide_typed_text(self):
        secret_text = "plain-looking-password-value"
        case = EvalCase(
            id="browser-type-redaction",
            name="browser type redaction",
            input="submit login",
            metadata={
                "fake_tools": [
                    {
                        "name": "browser_type",
                        "arguments": {
                            "target": "e1",
                            "text": secret_text,
                            "submit": True,
                        },
                        "output": f"filled {secret_text}",
                    }
                ]
            },
        )
        agent = build_fake_agent(case)

        prompt, trace = await agent.run_traced(
            case.input,
            [{"role": "user", "content": case.input}],
            session_key="cli:a",
        )

        self.assertNotIn(secret_text, prompt)
        self.assertIn(REDACTED, prompt)
        self.assertEqual(trace.tool_calls[0].arguments["text"], REDACTED)

    async def test_browser_click_preview_includes_resolved_target_context(self):
        case = EvalCase(
            id="browser-click-preview",
            name="browser click preview",
            input="publish",
            metadata={
                "fake_tools": [
                    {
                        "name": "browser_click",
                        "arguments": {"target": "e123"},
                        "output": "published",
                    }
                ]
            },
        )
        agent = build_fake_agent(case)

        prompt, trace = await agent.run_traced(
            case.input,
            [{"role": "user", "content": case.input}],
            session_key="cli:a",
            browser_snapshot=(
                "- Page URL: https://example.com/editor\n"
                "- button '发布' [ref=e123]"
            ),
        )

        self.assertEqual(trace.status, "awaiting_confirmation")
        self.assertIn("Target: e123", prompt)
        self.assertIn("Target text:", prompt)
        self.assertIn("发布", prompt)
        self.assertIn("Current URL: https://example.com/editor", prompt)
        self.assertEqual(agent.tools.execution_count, 0)

    async def test_internal_debug_trace_redacts_tool_arguments_and_result(self):
        secret_text = "plain-debug-secret"
        case = EvalCase(
            id="debug-redaction",
            name="debug redaction",
            input="type without submit",
            metadata={
                "fake_tools": [
                    {
                        "name": "browser_type",
                        "arguments": {
                            "target": "#field",
                            "text": secret_text,
                            "submit": False,
                        },
                        "output": f"typed {secret_text}",
                    }
                ],
                "fake_output": "done",
            },
        )
        agent = build_fake_agent(case)
        agent.config.show_internal_process = True
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            await agent.run_traced(
                case.input,
                [{"role": "user", "content": case.input}],
                session_key="cli:a",
            )

        rendered = stdout.getvalue()
        self.assertNotIn(secret_text, rendered)
        self.assertIn(REDACTED, rendered)


if __name__ == "__main__":
    unittest.main()
