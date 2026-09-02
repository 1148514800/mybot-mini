import asyncio
import unittest

from mybot.tools.exec import ExecTool


class ExecToolTests(unittest.TestCase):
    def test_playwright_cli_cannot_bypass_browser_tools(self) -> None:
        result = asyncio.run(
            ExecTool().execute("playwright-cli -s=test open https://example.com")
        )

        self.assertFalse(result.success)
        self.assertIn("Browser CLI commands are blocked", result.error)

    def test_npm_playwright_cli_package_is_also_blocked(self) -> None:
        result = asyncio.run(ExecTool().execute("npx @playwright/cli open"))

        self.assertFalse(result.success)
        self.assertIn("Browser CLI commands are blocked", result.error)


if __name__ == "__main__":
    unittest.main()
