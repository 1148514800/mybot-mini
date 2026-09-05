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
            {"role": "tool", "content": "x" * 200},
            {"role": "user", "content": "当前用户输入必须保留"},
        ])
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("当前用户输入必须保留", messages[-1]["content"])
        tool = next(item for item in messages if item["role"] == "tool")
        self.assertIn("tool output truncated", tool["content"])
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


if __name__ == "__main__":
    unittest.main()
