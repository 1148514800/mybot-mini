from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from mybot.tools.file_tools import WriteFileTool


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
            "memory/memory.json",
            "sessions/session.jsonl",
            "browser_profiles/managed/state.json",
            "runs/trace.json",
            "workspace/memory/memory.json",
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                result = asyncio.run(
                    WriteFileTool(workspace).execute(path, "overwrite")
                )

                self.assertIn("Runtime-managed", result)
                self.assertFalse((workspace / path).exists())


if __name__ == "__main__":
    unittest.main()
