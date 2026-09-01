import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from mybot.storage.memory import MemoryManager
from mybot.tools.memory import MemoryDeleteTool, MemoryWriteTool


class MemoryManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary_directory.name)
        self.manager = MemoryManager(self.workspace)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_reads_legacy_format_as_flat_memories(self) -> None:
        legacy = {
            "user_preferences": {"language": "zh-CN"},
            "project_facts": {"goal": "write a novel"},
            "browser_preferences": {"default_sessions": {"example.com": "main"}},
            "custom_facts": [
                {"key": "operating_system", "value": "Windows 11"},
                {"key": "goal", "value": "publish a novel"},
            ],
        }
        self.manager.path.write_text(json.dumps(legacy), encoding="utf-8")

        self.assertEqual(
            self.manager.load(),
            {
                "language": "zh-CN",
                "goal": "publish a novel",
                "operating_system": "Windows 11",
            },
        )

    def test_write_converts_legacy_file_and_delete_removes_key(self) -> None:
        self.manager.path.write_text(
            json.dumps({"custom_facts": [{"key": "language", "value": "zh-CN"}]}),
            encoding="utf-8",
        )

        self.manager.set("goal", "write a novel")
        self.assertEqual(
            json.loads(self.manager.path.read_text(encoding="utf-8")),
            {"language": "zh-CN", "goal": "write a novel"},
        )
        self.assertTrue(self.manager.delete("language"))
        self.assertFalse(self.manager.delete("missing"))
        self.assertEqual(self.manager.load(), {"goal": "write a novel"})

    def test_summary_renders_structured_values(self) -> None:
        self.manager.save({"language": "zh-CN", "topics": ["fantasy", "mystery"]})

        self.assertEqual(
            self.manager.get_memory_summary(),
            '# Memory\n- language: zh-CN\n- topics: ["fantasy", "mystery"]',
        )

    def test_invalid_json_is_not_silently_overwritten(self) -> None:
        self.manager.path.write_text("{invalid", encoding="utf-8")

        self.assertEqual(self.manager.get_memory_summary(), "")
        with self.assertRaises(ValueError):
            self.manager.set("goal", "write a novel")
        self.assertEqual(self.manager.path.read_text(encoding="utf-8"), "{invalid")


class MemoryToolTests(unittest.TestCase):
    def test_write_and_delete_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            manager = MemoryManager(Path(temporary_directory))
            write_result = asyncio.run(
                MemoryWriteTool(manager).execute("language", "zh-CN")
            )
            delete_result = asyncio.run(MemoryDeleteTool(manager).execute("language"))

        self.assertEqual(
            json.loads(write_result), {"key": "language", "value": "zh-CN"}
        )
        self.assertEqual(
            json.loads(delete_result), {"key": "language", "deleted": True}
        )


if __name__ == "__main__":
    unittest.main()
