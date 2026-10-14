"""Phase 05 tempfile + simulated LLM tests; no API keys or model requests."""
import contextlib
import io
import json
import stat
import tempfile
import unittest
from collections import deque
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

import httpx
from openai import APITimeoutError
import mybot.config as config_module
from mybot.agent import AgentLoop, ContextBuilder, Session
from mybot.config import GatewayConfig
from mybot.storage.session_store import SessionStore, validate_turns
from scripts.check_session import assert_pairs, call, response


class PersistenceChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.path = self.root / ".state/session.json"
        self.effects = deque()
        self.requests = []
        self.redirect = contextlib.redirect_stdout(io.StringIO())
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def agent(self, persist=True, max_turns=6):
        async def create(**kwargs):
            self.requests.append(deepcopy(kwargs["messages"]))
            item = self.effects.popleft()
            if isinstance(item, Exception): raise item
            return item
        from mybot.tools import build_default_tool_registry
        config = GatewayConfig(context_enabled=False, debug=False, workspace=self.workspace, session_persist=persist,
                               session_path=self.path, session_max_turns=max_turns)
        return AgentLoop(N(chat=N(completions=N(create=create))), config,
                         build_default_tool_registry(self.workspace), ContextBuilder(self.workspace))

    async def test_save_and_restart(self):
        agent = self.agent()
        self.assertEqual(agent.session.history(), [])
        self.assertFalse(self.path.exists())
        self.effects.append(response("记住了"))
        await agent.handle_message("我喜欢 Python")
        data = json.loads(self.path.read_text())
        self.assertEqual(set(data), {"version", "turns"})
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["turns"], agent.session.export_turns())
        self.assertEqual([m["role"] for m in data["turns"][0]], ["user", "assistant"])
        restored = self.agent()
        self.effects.append(response("Python"))
        self.assertEqual(await restored.handle_message("喜欢什么语言？"), "Python")
        self.assertIn("Python", self.requests[-1][1]["content"])
        self.assertEqual(len(restored.session.export_turns()), 2)

    async def test_multiple_tool_results_restore(self):
        agent = self.agent()
        self.effects.extend([response(calls=[call("w", "write_file", '{"path":"note.txt","content":"Python"}'), call("r", "read_file", '{"path":"note.txt"}')]), response("完成")])
        await agent.handle_message("写入并读取")
        restored = self.agent()
        self.assertEqual(restored.session.export_turns(), agent.session.export_turns())
        assert_pairs(self, restored.session.history())
        self.assertEqual([m["tool_call_id"] for m in restored.session.history() if m["role"] == "tool"], ["w", "r"])

    async def test_restore_and_save_use_current_window(self):
        agent = self.agent(max_turns=6)
        for n in range(4):
            self.effects.extend([response(calls=[call(f"l-{n}")]), response(str(n))])
            await agent.handle_message(f"u-{n}")
        restored = self.agent(max_turns=2)
        self.assertEqual([m["content"] for m in restored.session.history() if m["role"] == "user"], ["u-2", "u-3"])
        assert_pairs(self, restored.session.history())
        self.effects.append(response("next"))
        await restored.handle_message("u-4")
        self.assertEqual(len(json.loads(self.path.read_text())["turns"]), 2)
        self.assertEqual(self.agent(max_turns=2).session.history(), restored.session.history())

    async def test_clear_disk_memory_and_plan(self):
        agent = self.agent()
        self.effects.extend([response(calls=[call("p", "create_plan", '{"steps":["a","b"]}')]), response("完成")])
        await agent.handle_message("计划任务")
        self.assertTrue(agent.plan.steps)
        self.assertEqual(await agent.handle_message("/clear"), "当前会话已清空。")
        self.assertEqual(agent.session.history(), [])
        self.assertEqual(agent.plan.steps, [])
        self.assertEqual(json.loads(self.path.read_text()), {"version": 1, "turns": []})
        self.assertEqual(self.agent().session.history(), [])

    async def test_timeout_and_exception_do_not_write(self):
        agent = self.agent()
        self.effects.append(response("old"))
        await agent.handle_message("old")
        previous = self.path.read_bytes()
        history = agent.session.history()
        for error in (APITimeoutError(request=httpx.Request("POST", "https://example.invalid")), RuntimeError("network failed")):
            self.effects.extend([response(calls=[call("l")]), error])
            if isinstance(error, APITimeoutError):
                self.assertIn("超时", await agent.handle_message("timeout"))
            else:
                with self.assertRaises(RuntimeError): await agent.handle_message("error")
            self.assertEqual(self.path.read_bytes(), previous)
            self.assertEqual(agent.session.history(), history)

    async def test_react_limit_persists_complete_pairs(self):
        agent = self.agent()
        agent.config.max_react_steps = 1
        self.effects.append(response(calls=[call("l")]))
        self.assertIn("步上限", await agent.handle_message("list"))
        restored = self.agent()
        assert_pairs(self, restored.session.history())
        self.assertEqual(restored.session.history()[-1]["role"], "assistant")

    async def test_atomic_replace_failure_preserves_file_and_memory(self):
        agent = self.agent()
        self.effects.append(response("old"))
        await agent.handle_message("old")
        previous = self.path.read_bytes()
        history = agent.session.history()
        self.effects.append(response("not saved"))
        with patch("mybot.storage.session_store.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(RuntimeError, "save failed"):
                await agent.handle_message("new")
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(agent.session.history(), history)
        self.assertEqual(list(self.path.parent.glob(".session-*.tmp")), [])

    async def test_fsync_failure_preserves_file(self):
        store = SessionStore(self.path, self.workspace)
        store.save([])
        previous = self.path.read_bytes()
        with patch("mybot.storage.session_store.os.fsync", side_effect=OSError("fsync failed")):
            with self.assertRaisesRegex(RuntimeError, "save failed"): store.save([])
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.glob(".session-*.tmp")), [])

    async def test_clear_failure_keeps_disk_and_memory(self):
        agent = self.agent()
        self.effects.append(response("old"))
        await agent.handle_message("old")
        previous = self.path.read_bytes()
        history = agent.session.history()
        with patch("mybot.storage.session_store.os.replace", side_effect=OSError("clear failed")):
            with self.assertRaisesRegex(RuntimeError, "save failed"): await agent.handle_message("/clear")
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(agent.session.history(), history)
        self.assertEqual(self.agent().session.history(), history)

    async def test_corrupt_and_unsupported_documents_preserved(self):
        self.path.parent.mkdir()
        for content in ('{BROKEN_PRIVATE_HISTORY', '[]', '{"version":2,"turns":[]}', '{"version":true,"turns":[]}', '{"version":1,"turns":{}}', '{"version":1,"turns":[],"api_key":"private"}'):
            self.path.write_text(content)
            with self.subTest(content=content), self.assertRaisesRegex(RuntimeError, "original file preserved") as error:
                self.agent()
            self.assertNotIn("BROKEN_PRIVATE_HISTORY", str(error.exception))
            self.assertEqual(self.path.read_text(), content)
        self.assertEqual(self.requests, [])

    async def test_bad_message_pairs_and_roles_rejected(self):
        valid = [{"role":"user","content":"u"}, {"role":"assistant","content":None,"tool_calls":[{"id":"c","type":"function","function":{"name":"list_files","arguments":"{}"}}]}, {"role":"tool","tool_call_id":"c","content":"ok"}, {"role":"assistant","content":"a"}]
        bad = []
        missing = deepcopy(valid); missing.pop(2); bad.append(missing)
        wrong = deepcopy(valid); wrong[2]["tool_call_id"] = "unknown"; bad.append(wrong)
        duplicate = deepcopy(valid); duplicate.insert(3, deepcopy(duplicate[2])); bad.append(duplicate)
        calls = deepcopy(valid); calls[1]["tool_calls"].append(deepcopy(calls[1]["tool_calls"][0])); bad.append(calls)
        bad.extend([[{"role":"system","content":"secret"},valid[-1]], valid[:-1], [valid[0],valid[0],valid[-1]], [valid[0],valid[-1],valid[-1]]])
        self.path.parent.mkdir()
        for turn in bad:
            self.path.write_text(json.dumps({"version":1,"turns":[turn]}))
            previous = self.path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "load failed"): self.agent()
            self.assertEqual(self.path.read_bytes(), previous)
        validate_turns([valid])

    async def test_disabled_persistence_ignores_existing_corrupt_file(self):
        self.path.parent.mkdir()
        self.path.write_text("broken")
        agent = self.agent(persist=False)
        self.effects.append(response("hello"))
        await agent.handle_message("hello")
        self.assertEqual(self.path.read_text(), "broken")
        await agent.handle_message("/clear")
        self.assertEqual(agent.session.history(), [])
        self.assertEqual(self.path.read_text(), "broken")

    async def test_planning_history_does_not_resume_execution(self):
        agent = self.agent()
        self.effects.extend([response(calls=[call("p","create_plan",'{"steps":["list","write"]}'),call("s1","update_plan",'{"step":1,"status":"in_progress"}'),call("l"),call("c1","update_plan",'{"step":1,"status":"completed"}'),call("s2","update_plan",'{"step":2,"status":"in_progress"}'),call("w","write_file",'{"path":"out.txt","content":"once"}'),call("c2","update_plan",'{"step":2,"status":"completed"}')]),response("done")])
        await agent.handle_message("complex")
        before = self.workspace.joinpath("out.txt").stat().st_mtime_ns
        history = agent.session.history()
        count = len(self.requests)
        restored = self.agent()
        self.assertEqual(len(self.requests), count)
        self.assertEqual(restored.plan.mode, "DIRECT")
        self.assertEqual(restored.plan.steps, [])
        self.assertEqual(restored.session.history(), history)
        self.assertEqual(self.workspace.joinpath("out.txt").stat().st_mtime_ns, before)
        assert_pairs(self, history)
        self.effects.append(response("new"))
        await restored.handle_message("hello")
        self.assertEqual(self.requests[-1][1:-1], history)
        self.assertEqual(restored.plan.task, "hello")

    async def test_storage_cannot_be_accessed_through_workspace_tools(self):
        agent = self.agent()
        self.effects.append(response("secret history"))
        await agent.handle_message("hello")
        self.workspace.joinpath("alias").symlink_to(self.path)
        for name in ("read_file", "write_file"):
            for path in (str(self.path), "../.state/session.json", "alias"):
                params = {"path":path}
                if name == "write_file": params["content"] = "overwritten"
                self.assertFalse((await agent._execute(name, json.dumps(params))).success)
        with self.assertRaisesRegex(ValueError, "outside"):
            SessionStore(self.workspace / "session.json", self.workspace)
        outside_alias = self.root / "alias"
        outside_alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "outside"):
            SessionStore(outside_alias / "session.json", self.workspace)

    async def test_config_types_and_project_relative_path(self):
        with patch.object(config_module, "PROJECT_DIR", self.root), patch.object(config_module, "_CONFIG", {"session":{"persist":True,"path":"./state.json"}}):
            config = GatewayConfig(context_enabled=False, workspace=self.workspace)
            self.assertEqual(config.session_path, (self.root / "state.json").resolve())
            self.assertTrue(config.session_persist)
        for section in ([], {"persist":"true"}, {"persist":1}, {"path":12}, {"path":False}, {"path":""}, {"path":None}):
            with patch.object(config_module, "_CONFIG", {"session":section}), self.assertRaisesRegex(ValueError, "session"):
                GatewayConfig(context_enabled=False, workspace=self.workspace)
        with self.assertRaisesRegex(ValueError, "outside"):
            GatewayConfig(context_enabled=False, workspace=self.workspace, session_persist=True, session_path=self.workspace / "history.json")

    async def test_deepcopy_roundtrip_and_permissions(self):
        session = Session(max_turns=1)
        turns = [[{"role":"user","content":"u"},{"role":"assistant","content":"a"}]]
        session.restore(turns)
        turns[0][0]["content"] = "changed"
        exported = session.export_turns()
        exported[0][0]["content"] = "changed again"
        self.assertEqual(session.history()[0]["content"], "u")
        store = SessionStore(self.path, self.workspace)
        store.save(session.export_turns())
        self.assertEqual(store.load(), session.export_turns())
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)


def check_persistence():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PersistenceChecks))
    if not result.wasSuccessful(): raise AssertionError("Phase 05 Persistence checks failed")


if __name__ == "__main__":
    check_persistence()
