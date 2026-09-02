from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mybot.agent.context import BROWSER_MODE_MANAGED
from mybot.evals.fakes import build_fake_agent
from mybot.evals.models import EvalCase
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
        self.assertIn("回复“确认”", output)
        self.assertEqual(agent.tools.execution_count, 0)

        pending = agent.approvals.get("cli:a")
        self.assertIsNotNone(pending)
        exact_arguments = dict(pending.arguments)
        final, resumed_trace = await agent.resume_pending("cli:a", "确认")

        self.assertEqual(final, "task complete")
        self.assertEqual(resumed_trace.status, "success")
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
        _, trace = await agent.run_traced(
            case.input,
            [{"role": "user", "content": case.input}],
            session_key="cli:a",
        )
        call = trace.tool_calls[0]
        self.assertEqual(call.metadata["policy_decision"], "require_confirmation")
        self.assertEqual(call.metadata["risk_level"], "sensitive")
        self.assertEqual(call.metadata["approval_status"], "pending")
        self.assertTrue(call.metadata["approval_id"])
        serialized = json.dumps(call.arguments)
        for secret in (
            "raw-token",
            "raw-cookie",
            "raw-password",
            "raw-api-key",
            "raw-secret",
        ):
            self.assertNotIn(secret, serialized)
        self.assertIn(REDACTED, serialized)


if __name__ == "__main__":
    unittest.main()
