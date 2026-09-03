from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mybot.agent.context import BROWSER_MODE_MANAGED
from mybot.evals.fakes import build_fake_agent
from mybot.evals.models import EvalCase
from mybot.messaging import InboundMessage
from mybot.storage.session import SessionManager


def clarification_case(fake_tools: list[dict]) -> EvalCase:
    return EvalCase(
        id="clarification",
        name="clarification",
        input="send a message",
        metadata={
            "fake_tools": fake_tools,
            "fake_output": "original task complete",
        },
    )


class CountingContext:
    def __init__(self) -> None:
        self.build_count = 0

    def build_messages(self, history, content):
        self.build_count += 1
        return [{"role": "user", "content": content}]

    def resolve_browser_mode(self, content):
        return BROWSER_MODE_MANAGED


class AgentClarificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_flow_resumes_same_task_and_browser_context(self):
        tools = [
            {"name": "browser_open", "arguments": {}, "output": "opened"},
            {
                "name": "read_file",
                "arguments": {"path": "skills/douyin-skills/SKILL.md"},
                "output": "douyin instructions",
            },
            {
                "name": "request_user_input",
                "arguments": {"question": "找到食物爱西昂，是这个好友吗？"},
                "output": "找到食物爱西昂，是这个好友吗？",
            },
            {
                "name": "browser_inspect",
                "arguments": {"role": "textbox"},
                "output": "message input",
            },
        ]
        agent = build_fake_agent(clarification_case(tools))
        context = CountingContext()
        with tempfile.TemporaryDirectory() as directory:
            agent.context = context
            agent.sessions = SessionManager(Path(directory))

            question, first_trace = await agent.handle_inbound_message(
                InboundMessage("cli", "user", "a", "给好友发送消息")
            )
            pending = agent.clarifications.get("cli:a")
            self.assertEqual(first_trace.status, "awaiting_clarification")
            self.assertIn("食物爱西昂", question)
            self.assertIsNotNone(pending)
            self.assertTrue(pending.browser_initialized)
            self.assertEqual(pending.browser_session, "managed_browser")
            self.assertIn(
                "skills/douyin-skills/skill.md",
                pending.loaded_skills,
            )

            output, resumed_trace = await agent.handle_inbound_message(
                InboundMessage("cli", "user", "a", "是")
            )

        self.assertEqual(output, "original task complete")
        self.assertEqual(resumed_trace.status, "success")
        self.assertNotEqual(first_trace.run_id, resumed_trace.run_id)
        self.assertEqual(
            first_trace.metadata["task_id"],
            resumed_trace.metadata["task_id"],
        )
        self.assertEqual(context.build_count, 1)
        self.assertEqual(
            [name for name, _ in agent.tools.executed_calls],
            [
                "browser_open",
                "read_file",
                "request_user_input",
                "browser_inspect",
            ],
        )
        self.assertIsNone(agent.clarifications.get("cli:a"))

    async def test_loaded_skill_is_not_read_twice_after_clarification(self):
        skill = {
            "name": "read_file",
            "arguments": {"path": "skills/douyin-skills/SKILL.md"},
            "output": "instructions",
        }
        agent = build_fake_agent(
            clarification_case(
                [
                    skill,
                    {
                        "name": "request_user_input",
                        "arguments": {"question": "Which friend?"},
                        "output": "Which friend?",
                    },
                    skill,
                ]
            )
        )

        _, first_trace = await agent.run_traced(
            "send",
            [{"role": "user", "content": "send"}],
            session_key="cli:a",
        )
        _, resumed_trace = await agent.resume_clarification("cli:a", "Alice")

        self.assertEqual(first_trace.status, "awaiting_clarification")
        self.assertEqual(resumed_trace.status, "success")
        self.assertEqual(
            [name for name, _ in agent.tools.executed_calls],
            ["read_file", "request_user_input"],
        )
        repeated = resumed_trace.tool_calls[0]
        self.assertEqual(repeated.tool_name, "read_file")
        self.assertTrue(repeated.metadata["skill_cache_hit"])

    async def test_initialized_browser_is_not_opened_twice(self):
        open_call = {
            "name": "browser_open",
            "arguments": {},
            "output": "opened",
        }
        agent = build_fake_agent(
            clarification_case(
                [
                    open_call,
                    {
                        "name": "request_user_input",
                        "arguments": {"question": "Logged in?"},
                        "output": "Logged in?",
                    },
                    open_call,
                ]
            )
        )

        await agent.run_traced(
            "open",
            [{"role": "user", "content": "open"}],
            session_key="cli:a",
        )
        _, resumed_trace = await agent.resume_clarification("cli:a", "yes")

        self.assertEqual(
            [name for name, _ in agent.tools.executed_calls],
            ["browser_open", "request_user_input"],
        )
        repeated = resumed_trace.tool_calls[0]
        self.assertEqual(
            repeated.metadata["execution_skipped"],
            "browser_already_initialized",
        )

    async def test_clarification_is_barrier_for_remaining_tool_calls(self):
        question = {
            "name": "request_user_input",
            "arguments": {"question": "Choose a recipient"},
            "output": "Choose a recipient",
        }
        click = {
            "name": "browser_click",
            "arguments": {"target": "e9"},
            "output": "clicked",
        }
        case = clarification_case([question, click])
        case.metadata["fake_tool_batches"] = [[question, click]]
        agent = build_fake_agent(case)

        _, trace = await agent.run_traced(
            "send",
            [{"role": "user", "content": "send"}],
            session_key="cli:a",
        )
        self.assertEqual(trace.status, "awaiting_clarification")
        self.assertEqual(agent.tools.execution_count, 1)

        output, resumed = await agent.resume_clarification("cli:a", "Alice")

        self.assertEqual(output, "original task complete")
        self.assertEqual(resumed.status, "success")
        self.assertEqual(agent.tools.execution_count, 1)
        self.assertEqual(agent.tools.executed_calls[0][0], "request_user_input")


if __name__ == "__main__":
    unittest.main()
