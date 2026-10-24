"""Phase 03 simulated LLM tests: uv run python -m scripts.check_session."""
import asyncio
import contextlib
import io
import tempfile
import unittest
from collections import deque
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

import httpx
from openai import APITimeoutError
from mybot.agent import AgentLoop, ContextBuilder, Session
import mybot.config as config_module
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from scripts.legacy_write_fixture import legacy_registry


def response(content=None, calls=None):
    return N(choices=[N(message=N(content=content, tool_calls=calls), finish_reason="tool_calls" if calls else "stop")], usage=None)


def call(identifier, name="list_files", arguments='{"path":"."}'):
    return N(id=identifier, function=N(name=name, arguments=arguments))


def assert_pairs(test, messages):
    pending = set()
    for message in messages:
        if message["role"] == "tool":
            test.assertIn(message["tool_call_id"], pending)
            pending.remove(message["tool_call_id"])
        else:
            test.assertFalse(pending, "Unanswered tool call before a new user/assistant message")
            pending = {item["id"] for item in message.get("tool_calls", [])}
    test.assertFalse(pending)


class SessionChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = Path(self.folder.name)
        self.requests = []
        self.effects = deque()
        async def create(**kwargs):
            self.requests.append(deepcopy(kwargs["messages"]))
            item = self.effects.popleft()
            if isinstance(item, Exception):
                raise item
            return item
        self.agent = AgentLoop(N(chat=N(completions=N(create=create))), GatewayConfig(skills_enabled=False, context_enabled=False, session_persist=False, debug=False, workspace=self.workspace, session_max_turns=6), legacy_registry(self.workspace), ContextBuilder(self.workspace))

    async def test_configured_history_window(self):
        with patch.object(config_module, "_CONFIG", {"session": {"max_turns": 2}}):
            config = GatewayConfig(skills_enabled=False, context_enabled=False, session_persist=False, debug=False, workspace=self.workspace)
        self.assertEqual(config.session_max_turns, 2)
        self.agent = AgentLoop(self.agent.client, config, self.agent.tools, self.agent.context)
        for number in range(3):
            self.effects.extend([response(calls=[call(f"configured-{number}")]), response(f"answer-{number}")])
            await self.agent.handle_message(f"user-{number}")
        history = self.agent.session.history()
        self.assertEqual([m["content"] for m in history if m["role"] == "user"], ["user-1", "user-2"])
        self.assertEqual(len(history), 8)
        assert_pairs(self, history)

    async def test_config_default_and_invalid_values(self):
        with patch.object(config_module, "_CONFIG", {}):
            self.assertEqual(GatewayConfig(skills_enabled=False, context_enabled=False, ).session_max_turns, 6)
        for value in (0, -1, True, "6", 2.5, None):
            with self.subTest(value=value), patch.object(config_module, "_CONFIG", {"session": {"max_turns": value}}):
                with self.assertRaisesRegex(ValueError, "session.max_turns"):
                    GatewayConfig(skills_enabled=False, context_enabled=False, )

    async def test_first_and_second_turn(self):
        self.effects.extend([response("记住了"), response("Python")])
        self.assertEqual(await self.agent.handle_message("我最喜欢的语言是 Python"), "记住了")
        self.assertEqual([m["role"] for m in self.requests[0]], ["system", "user"])
        self.assertEqual(await self.agent.handle_message("我喜欢什么语言？"), "Python")
        self.assertEqual([m["role"] for m in self.requests[1]], ["system", "user", "assistant", "user"])
        self.assertIn("Python", self.requests[1][1]["content"])
        self.assertEqual(self.agent.session.history()[-1]["content"], "Python")

    async def test_tools_and_multiple_ids(self):
        self.effects.extend([response(calls=[call("w", "write_file", '{"path":"note.txt","content":"Python"}'), call("r", "read_file", '{"path":"note.txt"}')]), response("已写入并读取"), response("Python")])
        await self.agent.handle_message("写入并读取")
        history = self.agent.session.history()
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "tool", "tool", "assistant"])
        self.assertEqual([m["tool_call_id"] for m in history if m["role"] == "tool"], ["w", "r"])
        self.assertEqual(history[3]["content"], "Python")
        self.assertEqual(self.workspace.joinpath("note.txt").read_text(), "Python")
        assert_pairs(self, history)
        await self.agent.handle_message("刚写了什么？")
        self.assertEqual(self.requests[-1][1:-1], history)
        assert_pairs(self, self.requests[-1])

    async def test_whole_turn_eviction(self):
        for number in range(7):
            self.effects.extend([response(calls=[call(f"id-{number}")]), response(f"answer-{number}")])
            await self.agent.handle_message(f"user-{number}")
        history = self.agent.session.history()
        self.assertEqual([m["content"] for m in history if m["role"] == "user"], [f"user-{n}" for n in range(1, 7)])
        self.assertEqual(len(history), 24)
        self.assertNotIn("id-0", str(history))
        assert_pairs(self, history)

    async def test_clear_cli(self):
        self.effects.append(response("记住了"))
        await self.agent.handle_message("Python")
        with patch("builtins.input", side_effect=["/clear", "quit"]), contextlib.redirect_stdout(io.StringIO()) as out:
            await self.agent.run()
        self.assertIn("当前会话已清空", out.getvalue())
        self.assertEqual(self.agent.session.history(), [])
        self.assertEqual(len(self.requests), 1)
        self.effects.append(response("新会话"))
        await self.agent.handle_message("你好")
        self.assertEqual([m["role"] for m in self.requests[-1]], ["system", "user"])

    async def test_limit_finishes_paired_turn(self):
        self.agent.config.max_react_steps = 1
        self.effects.append(response(calls=[call("limit-1")]))
        reply = await self.agent.handle_message("列目录")
        self.assertIn("1 步上限", reply)
        history = self.agent.session.history()
        self.assertEqual([m["role"] for m in history], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(history[-1]["content"], reply)
        assert_pairs(self, history)
        self.effects.append(response("继续"))
        await self.agent.handle_message("接着说")
        assert_pairs(self, self.requests[-1])

    async def test_api_timeout_rolls_back_current_turn(self):
        self.effects.append(response("旧回答"))
        await self.agent.handle_message("旧问题")
        history = self.agent.session.history()
        self.effects.extend([response(calls=[call("timeout-1", "write_file", '{"path":"side.txt","content":"written"}')]), APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))])
        self.assertIn("超时", await self.agent.handle_message("超时轮"))
        self.assertEqual(self.agent.session.history(), history)
        self.assertEqual(self.workspace.joinpath("side.txt").read_text(), "written")
        self.effects.append(response("恢复"))
        await self.agent.handle_message("新问题")
        self.assertEqual(self.requests[-1][1:-1], history)
        assert_pairs(self, self.requests[-1])

    async def test_wait_for_timeout(self):
        async def slow(**kwargs):
            await asyncio.sleep(2)
        self.agent.client.chat.completions.create = slow
        self.agent.config.request_timeout_seconds = 1
        self.assertIn("超时", await self.agent.handle_message("等待"))
        self.assertEqual(self.agent.session.history(), [])

    async def test_tool_error_is_paired(self):
        self.effects.extend([response(calls=[call("bad", "read_file", '{"path":"missing"}')]), response("文件不存在")])
        await self.agent.handle_message("读取缺失文件")
        history = self.agent.session.history()
        self.assertIn("Error:", history[2]["content"])
        assert_pairs(self, history)

    async def test_unexpected_exception_keeps_previous_history(self):
        self.effects.append(response("旧回答"))
        await self.agent.handle_message("旧问题")
        history = self.agent.session.history()
        self.effects.extend([response(calls=[call("x")]), RuntimeError("network failed")])
        with self.assertRaises(RuntimeError):
            await self.agent.handle_message("失败轮")
        self.assertEqual(self.agent.session.history(), history)

    async def test_history_copies_and_session_isolation(self):
        session = Session(max_turns=1)
        turn = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}]
        session.add_turn(turn)
        turn[0]["content"] = "changed"
        history = session.history()
        history[0]["content"] = "changed again"
        self.assertEqual(session.history()[0]["content"], "hello")
        self.assertEqual(Session().history(), [])
        with self.assertRaises(ValueError):
            Session(0)


def check_session():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SessionChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Phase 03 Session checks failed")


if __name__ == "__main__":
    check_session()
