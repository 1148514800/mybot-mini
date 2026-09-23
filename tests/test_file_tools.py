from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from mybot.tools.file_tools import ReadFileTool, WriteFileTool


class WriteFileToolTests(unittest.TestCase):
    def test_ordinary_workspace_file_can_be_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            result = asyncio.run(
                WriteFileTool(workspace).execute("notes/status.txt", "ready")
            )
            self.assertTrue((workspace / "notes" / "status.txt").exists())

        self.assertIn("Wrote 5 bytes", result)

    def test_runtime_managed_files_cannot_be_written_directly(self) -> None:
        for path in (
            "sessions/session.jsonl",
            "browser_profiles/managed/state.json",
            "runs/trace.json",
            "checkpoints/active_tasks.sqlite3",
            "artifacts/data/art_x.txt",
            "workspace/checkpoints/active_tasks.sqlite3",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                result = asyncio.run(
                    WriteFileTool(workspace).execute(path, "overwrite")
                )

                self.assertIn("Wrote 9 bytes", result)
                self.assertEqual(
                    (workspace / path).read_text(encoding="utf-8"),
                    "overwrite",
                )

    def test_runtime_managed_artifacts_can_be_read_directly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "artifacts" / "data").mkdir(parents=True)
            (workspace / "artifacts" / "data" / "art_x.txt").write_text("secret")
            result = asyncio.run(ReadFileTool(workspace).execute("artifacts/data/art_x.txt"))
            self.assertEqual(result, "secret")


if __name__ == "__main__":
    unittest.main()
