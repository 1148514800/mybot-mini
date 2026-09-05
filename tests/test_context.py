import tempfile
import unittest
from pathlib import Path

from mybot.agent.context import ContextBuilder
from mybot.storage.memory import MemoryManager


class ContextBuilderTests(unittest.TestCase):
    def test_build_messages_merges_system_sections_into_one_message(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            memory = MemoryManager(workspace)
            memory.set("writing_goal", "成为番茄小说作家")

            messages = ContextBuilder(
                workspace,
                memory_manager=memory,
            ).build_messages(
                [{"role": "assistant", "content": "previous reply"}],
                "帮我继续写作",
            )

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(
            sum(message.get("role") == "system" for message in messages),
            1,
        )
        self.assertIn("Use managed mode", messages[0]["content"])
        self.assertIn("writing_goal", messages[0]["content"])
        self.assertEqual(messages[-1]["role"], "user")

    def test_budget_keeps_system_and_current_user_and_truncates_tool(self):
        builder = ContextBuilder(Path("."), max_context_chars=500, max_tool_result_chars=80)
        messages, stats = builder.prepare_messages([
            {"role": "system", "content": "安全规则" * 20},
            {"role": "user", "content": "old" * 100},
            {"role": "assistant", "tool_calls": [{"id": "old-call"}], "content": None},
            {"role": "tool", "content": "x" * 200},
            {"role": "user", "content": "当前用户输入必须保留"},
        ])
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("当前用户输入必须保留", messages[-1]["content"])
        self.assertFalse(any(item.get("role") == "tool" for item in messages))
        self.assertTrue(stats["context_truncated"])

    def test_memory_budget_does_not_modify_memory_file(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            memory = MemoryManager(workspace)
            memory.set("fact", "z" * 1000)
            path = workspace / "memory" / "memory.json"
            before = path.read_text()
            ContextBuilder(workspace, memory_manager=memory, max_memory_chars=40).build_messages([], "hello")
            self.assertEqual(before, path.read_text())

    def test_tool_call_and_results_are_one_compaction_unit(self):
        builder = ContextBuilder(Path("."), max_context_chars=50, max_tool_result_chars=40)
        assistant = {
            "role": "assistant",
            "tool_calls": [
                {"id": "call-a", "type": "function", "function": {"name": "a"}},
                {"id": "call-b", "type": "function", "function": {"name": "b"}},
            ],
            "content": None,
        }
        result = [
            {"role": "system", "content": "rules"},
            assistant,
            {"role": "tool", "tool_call_id": "call-a", "content": "a" * 100},
            {"role": "tool", "tool_call_id": "call-b", "content": "b" * 100},
            {"role": "user", "content": "latest"},
        ]
        compacted, _ = builder.prepare_messages(result)
        self.assertFalse(any(item.get("role") == "tool" for item in compacted))
        self.assertFalse(any(item.get("tool_calls") for item in compacted))

    def test_tool_result_is_truncated_before_unit_budgeting(self):
        builder = ContextBuilder(Path("."), max_context_chars=500, max_tool_result_chars=80)
        compacted, _ = builder.prepare_messages([
            {"role": "system", "content": "rules"},
            {"role": "assistant", "tool_calls": [{"id": "call-a"}], "content": None},
            {"role": "tool", "tool_call_id": "call-a", "content": "x" * 200},
            {"role": "user", "content": "latest"},
        ])
        tool = next(item for item in compacted if item["role"] == "tool")
        self.assertIn("tool output truncated", tool["content"])

    def test_build_messages_keeps_runtime_content_uncompacted(self):
        builder = ContextBuilder(Path("."), max_context_chars=100)
        history = [{"role": "tool", "content": "x" * 500}]
        messages = builder.build_messages(history, "latest")
        self.assertEqual(len(messages[1]["content"]), 500)

    def test_required_context_uses_soft_budget_overflow_flag(self):
        builder = ContextBuilder(Path("."), max_context_chars=10)
        _, stats = builder.prepare_messages([
            {"role": "system", "content": "安全规则必须保留"},
            {"role": "user", "content": "当前请求必须保留"},
        ])
        self.assertTrue(stats["context_budget_overflow"])
        self.assertFalse(stats["context_truncated"])


if __name__ == "__main__":
    unittest.main()
