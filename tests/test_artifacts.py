import asyncio
import tempfile
import unittest
from pathlib import Path

from mybot.agent.artifact_results import externalize_tool_result
from mybot.storage.artifacts import ArtifactStore
from mybot.tools.artifact import ArtifactReadTool
from mybot.tools.base import Tool
from mybot.tools.registry import ToolRegistry
from mybot.tools.result import BrowserResult, ToolResult


class _CountingArtifactTool(Tool):
    def __init__(self):
        self.execution_count = 0

    @property
    def name(self):
        return "artifact_probe"

    @property
    def description(self):
        return "probe"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        self.execution_count += 1
        return ToolResult(True, output="unused")


class ArtifactTests(unittest.TestCase):
    def test_large_result_externalizes_and_redacts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            result = ToolResult(True, output="A" * 9000 + " api_key=SUPER_SECRET_VALUE")
            rendered, record = externalize_tool_result(
                result,
                tool_name="read_file",
                arguments={},
                session_key="A",
                task_id="task-a",
                store=store,
                enabled=True,
                threshold_chars=8000,
            )
            self.assertIsNotNone(record)
            self.assertIn("artifact_id=", rendered)
            self.assertNotIn("SUPER_SECRET_VALUE", rendered)
            self.assertNotIn("SUPER_SECRET_VALUE", (store.data_dir / f"{record.artifact_id}.txt").read_text())
            self.assertNotIn("SUPER_SECRET_VALUE", (store.meta_dir / f"{record.artifact_id}.json").read_text())

    def test_small_and_browser_results_are_not_externalized(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            for result, name in [
                (ToolResult(True, output="small"), "read_file"),
                (BrowserResult(True, output="B" * 9000), "browser_snapshot"),
            ]:
                rendered, record = externalize_tool_result(
                    result, tool_name=name, arguments={}, session_key="A", task_id=None,
                    store=store, enabled=True, threshold_chars=8,
                )
                self.assertIsNone(record)
                self.assertEqual(rendered, result.to_text())

    def test_read_is_bounded_and_session_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            record = store.put("A", "task", "read_file", "0123456789" * 100)
            registry = ToolRegistry()
            reader = ArtifactReadTool(store, read_max_chars=80)
            registry.register(reader)
            result = asyncio.run(registry.execute("artifact_read", {"artifact_id": record.artifact_id, "offset": 10, "max_chars": 40}, session_key="A"))
            self.assertTrue(result.success)
            self.assertEqual(result.metadata["returned_chars"], 40)
            self.assertEqual(result.metadata["next_offset"], 50)
            denied = asyncio.run(registry.execute("artifact_read", {"artifact_id": record.artifact_id, "max_chars": 40}, session_key="B"))
            self.assertFalse(denied.success)
            self.assertEqual(denied.metadata["error_type"], "artifact_unavailable")

    def test_missing_identity_fails_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            registry = ToolRegistry()
            reader = ArtifactReadTool(store)
            registry.register(reader)
            result = asyncio.run(registry.execute("artifact_read", {"artifact_id": "art_00000000000000000000000000000000", "session_key": "A"}, session_key=""))
            self.assertFalse(result.success)
            self.assertEqual(result.metadata["error_type"], "artifact_ownership_identity_missing")

    def test_query_returns_bounded_snippet(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            record = store.put("A", None, "read_file", "x" * 5000 + "UNIQUE_NEEDLE_12345" + "y" * 5000)
            content, _ = store.read("A", record.artifact_id, max_chars=100, query="UNIQUE_NEEDLE_12345")
            self.assertIn("UNIQUE_NEEDLE_12345", content)
            self.assertLessEqual(len(content), 100)

    def test_concurrent_puts_do_not_cross_contents(self):
        async def create(store, owner, value):
            return await asyncio.to_thread(store.put, owner, None, "read_file", value)

        async def run_puts(store):
            return await asyncio.gather(
                create(store, "A", "A" * 100), create(store, "B", "B" * 100)
            )

        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory))
            records = asyncio.run(run_puts(store))
            self.assertNotEqual(records[0].artifact_id, records[1].artifact_id)
            self.assertEqual(store.read("A", records[0].artifact_id)[0], "A" * 100)
            self.assertIsNone(store.read("A", records[1].artifact_id))


if __name__ == "__main__":
    unittest.main()
