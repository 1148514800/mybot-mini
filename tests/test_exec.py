import asyncio
import tempfile
import unittest
from pathlib import Path

from mybot.tools.exec import ExecTool


class ExecToolTests(unittest.TestCase):
    def test_playwright_cli_cannot_bypass_browser_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = asyncio.run(
                ExecTool(Path(directory)).execute(
                    "playwright-cli -s=test open https://example.com"
                )
            )

        self.assertFalse(result.success)
        self.assertIn("Browser CLI commands are blocked", result.error)

    def test_npm_playwright_cli_package_is_also_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = asyncio.run(
                ExecTool(Path(directory)).execute("npx @playwright/cli open")
            )

        self.assertFalse(result.success)
        self.assertIn("Browser CLI commands are blocked", result.error)

    def test_commands_run_with_workspace_as_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            result = asyncio.run(ExecTool(workspace).execute("pwd"))

        self.assertTrue(result.success)
        self.assertEqual(Path(result.output.strip()).resolve(), workspace)


if __name__ == "__main__":
    unittest.main()
