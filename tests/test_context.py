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


if __name__ == "__main__":
    unittest.main()
