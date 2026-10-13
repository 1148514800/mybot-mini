"""Phase 04 offline tests: uv run python -m scripts.check_planning."""
import contextlib
import io
import json
import tempfile
import unittest
from collections import deque
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as N

import httpx
from openai import APITimeoutError
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.planning import Plan
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from scripts.check_session import assert_pairs, call, response


def plan_call(identifier="p"):
    return call(identifier, "create_plan", '{"steps":["列出文件","写入总结"]}')


def update(identifier, step, status):
    return call(identifier, "update_plan", json.dumps({"step": step, "status": status}))


class PlanningChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = Path(self.folder.name)
        self.effects = deque()
        self.requests = []
        self.log = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.log)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        async def create(**kwargs):
            self.requests.append(deepcopy(kwargs))
            item = self.effects.popleft()
            if isinstance(item, Exception):
                raise item
            return item
        self.agent = AgentLoop(N(chat=N(completions=N(create=create))), GatewayConfig(session_persist=False, debug=False, workspace=self.workspace), build_default_tool_registry(self.workspace), ContextBuilder(self.workspace))

    async def test_greeting_direct_without_extra_request(self):
        self.effects.append(response("你好"))
        self.assertEqual(await self.agent.handle_message("你好"), "你好")
        self.assertEqual(self.agent.plan.mode, "DIRECT")
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn("[PLAN]", self.log.getvalue())
        self.assertEqual({t["function"]["name"] for t in self.requests[0]["tools"]}, {"read_file", "write_file", "list_files", "create_plan", "update_plan"})

    async def test_single_tool_direct(self):
        self.effects.extend([response(calls=[call("l")]), response("目录为空")])
        await self.agent.handle_message("列出文件")
        self.assertEqual(self.agent.plan.mode, "DIRECT")
        self.assertEqual(len(self.requests), 2)
        assert_pairs(self, self.agent.session.history())
        self.assertEqual(self.log.getvalue(), "")

    async def test_complete_plan_and_ids(self):
        self.effects.extend([
            response(calls=[plan_call()]),
            response(calls=[update("s1", 1, "in_progress"), call("l")]),
            response(calls=[update("c1", 1, "completed"), update("s2", 2, "in_progress"), call("w", "write_file", '{"path":"summary.txt","content":"PRIVATE_PARAMETERS"}')]),
            response(calls=[update("c2", 2, "completed")]), response("总结已保存")])
        self.assertEqual(await self.agent.handle_message("列出文件，然后写入总结"), "总结已保存")
        self.assertEqual(self.agent.plan.task, "列出文件，然后写入总结")
        self.assertEqual([s.status for s in self.agent.plan.steps], ["completed", "completed"])
        self.assertTrue(self.agent.plan.closed)
        self.assertEqual(self.workspace.joinpath("summary.txt").read_text(), "PRIVATE_PARAMETERS")
        self.assertIn("[PLAN]", self.log.getvalue())
        self.assertIn("[STEP 2] completed", self.log.getvalue())
        self.assertNotIn("PRIVATE_PARAMETERS", self.log.getvalue())
        history = self.agent.session.history()
        assert_pairs(self, history)
        self.assertEqual(len([m for m in history if m["role"] == "tool"]), 7)
        self.effects.append(response("新的任务"))
        await self.agent.handle_message("你好")
        self.assertEqual(self.agent.plan.mode, "DIRECT")
        self.assertEqual(self.requests[-1]["messages"][1:-1], history)
        self.assertFalse((await self.agent._execute("update_plan", '{"step":1,"status":"completed"}')).success)

    async def test_invalid_parameters(self):
        self.agent.plan.reset("test")
        for params in ('{}', '{', '{"steps":"bad"}', '{"steps":["one"]}', '{"steps":["a",2]}', '{"steps":["a",""]}', '{"steps":["a","b","c","d","e","f","g"]}', '{"steps":["a","b"],"extra":1}'):
            self.assertFalse((await self.agent._execute("create_plan", params)).success, params)
            self.assertEqual(self.agent.plan.steps, [])
        self.assertTrue((await self.agent._execute("create_plan", '{"steps":["a","b"]}')).success)
        self.assertFalse((await self.agent._execute("create_plan", '{"steps":["x","y"]}')).success)
        for params in ('{}', '{"step":true,"status":"in_progress"}', '{"step":"1","status":"in_progress"}', '{"step":0,"status":"in_progress"}', '{"step":3,"status":"in_progress"}', '{"step":1,"status":"pending"}', '{"step":1,"status":"unknown"}'):
            self.assertFalse((await self.agent._execute("update_plan", params)).success, params)

    async def test_invalid_transitions_and_no_fake_evidence(self):
        plan = self.agent.plan
        plan.create(["a", "b"])
        for step, status in ((2, "in_progress"), (1, "completed"), (1, "failed")):
            with self.assertRaises(ValueError): plan.update(step, status)
        plan.update(1, "in_progress")
        with self.assertRaises(ValueError): plan.update(1, "completed")
        with self.assertRaises(ValueError): plan.update(1, "in_progress")
        # A successful planning operation cannot count as real tool evidence.
        self.assertFalse((await self.agent._execute("update_plan", '{"step":1,"status":"completed"}')).success)
        self.assertTrue((await self.agent._execute("list_files", '{"path":"."}')).success)
        plan.update(1, "completed")
        with self.assertRaises(ValueError): plan.update(1, "completed")

    async def test_failed_tool_blocks_completion_and_next_operations(self):
        self.effects.extend([response(calls=[plan_call(), update("s", 1, "in_progress"), call("bad", "read_file", '{"path":"missing"}'), update("fake", 1, "completed"), update("skip", 2, "in_progress"), call("w", "write_file", '{"path":"bad.txt","content":"not allowed"}')]), response("全部成功")])
        reply = await self.agent.handle_message("读取然后写入")
        self.assertIn("计划未完成", reply)
        self.assertIn("not found", reply)
        self.assertNotIn("全部成功", reply)
        self.assertEqual([s.status for s in self.agent.plan.steps], ["failed", "pending"])
        self.assertFalse(self.workspace.joinpath("bad.txt").exists())
        assert_pairs(self, self.agent.session.history())

    async def test_success_then_failure_does_not_keep_success_evidence(self):
        self.effects.extend([response(calls=[plan_call(), update("s", 1, "in_progress"), call("l"), call("bad", "read_file", '{"path":"missing"}'), update("fake", 1, "completed")]), response("完成")])
        self.assertIn("计划未完成", await self.agent.handle_message("多步任务"))
        self.assertEqual(self.agent.plan.steps[0].status, "failed")

    async def test_unverified_text_step_not_completed(self):
        self.effects.extend([response(calls=[plan_call(), update("s", 1, "in_progress"), update("fake", 1, "completed")]), response("已经完成总结")])
        reply = await self.agent.handle_message("复杂任务")
        self.assertIn("未验证", reply)
        self.assertNotIn("已经完成总结", reply)
        self.assertEqual(self.agent.plan.steps[0].status, "in_progress")
        self.assertTrue(self.agent.plan.closed)

    async def test_no_execution_without_active_step(self):
        self.effects.extend([response(calls=[plan_call(), call("w", "write_file", '{"path":"bad.txt","content":"not allowed"}')]), response("完成")])
        self.assertIn("计划未完成", await self.agent.handle_message("复杂任务"))
        self.assertFalse(self.workspace.joinpath("bad.txt").exists())

    async def test_timeout_closes_plan_without_invalid_history(self):
        self.effects.append(response("旧回答"))
        await self.agent.handle_message("旧任务")
        history = self.agent.session.history()
        self.effects.extend([response(calls=[plan_call(), update("s", 1, "in_progress")]), APITimeoutError(request=httpx.Request("POST", "https://example.invalid"))])
        reply = await self.agent.handle_message("复杂任务")
        self.assertIn("超时", reply)
        self.assertIn("计划未完成", reply)
        self.assertEqual(self.agent.plan.steps[0].status, "failed")
        self.assertEqual(self.agent.session.history(), history)
        self.assertTrue(self.agent.plan.closed)

    async def test_exception_closes_plan(self):
        self.effects.extend([response(calls=[plan_call(), update("s", 1, "in_progress")]), RuntimeError("network failed")])
        with self.assertRaises(RuntimeError): await self.agent.handle_message("复杂任务")
        self.assertEqual(self.agent.plan.steps[0].status, "failed")
        self.assertTrue(self.agent.plan.closed)
        self.assertEqual(self.agent.session.history(), [])
        self.assertIn("计划未完成", self.log.getvalue())

    async def test_limit_and_clear(self):
        self.agent.config.max_react_steps = 1
        self.effects.append(response(calls=[plan_call(), update("s", 1, "in_progress"), call("l")]))
        reply = await self.agent.handle_message("复杂任务")
        self.assertIn("步上限", reply)
        self.assertIn("计划未完成", reply)
        self.assertEqual([s.status for s in self.agent.plan.steps], ["failed", "pending"])
        assert_pairs(self, self.agent.session.history())
        await self.agent.handle_message("/clear")
        self.assertEqual(self.agent.session.history(), [])
        self.assertEqual(self.agent.plan.steps, [])
        self.assertEqual(self.agent.plan.task, "")
        self.assertEqual(len(self.requests), 1)


def check_planning():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PlanningChecks))
    if not result.wasSuccessful():
        raise AssertionError("Phase 04 Planning checks failed")


if __name__ == "__main__":
    check_planning()
