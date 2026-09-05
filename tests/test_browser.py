"""Optional playwright-cli integration tests.

Unit tests for browser command construction and result handling live in the other
browser test modules and never require a real browser.
"""

import asyncio
import os
import shutil
import subprocess
import unittest
import uuid

from mybot.tools.browser.interaction import BrowserInspectTool
from mybot.tools.browser.session import BrowserSessionManager


PLAYWRIGHT_CLI = shutil.which("playwright-cli") or shutil.which(
    "playwright-cli.cmd"
)
RUN_LOCAL_BROWSER_TESTS = os.environ.get("MYBOT_RUN_BROWSER_INTEGRATION") == "1"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    if PLAYWRIGHT_CLI is None:
        raise FileNotFoundError("playwright-cli was not found in PATH")

    command = [PLAYWRIGHT_CLI, *args]
    if os.name == "nt" and PLAYWRIGHT_CLI.lower().endswith((".cmd", ".bat")):
        command = ["cmd", "/c", *command]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


@unittest.skipUnless(
    PLAYWRIGHT_CLI,
    "playwright-cli integration test skipped: command not found in PATH",
)
class PlaywrightCliIntegrationTests(unittest.TestCase):
    def test_cli_version(self) -> None:
        result = run_cli("--version")

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_browser_inspect_selector_text_role_and_placeholder(self) -> None:
        session = f"inspect_integration_{uuid.uuid4().hex[:10]}"
        tool = BrowserInspectTool(BrowserSessionManager())
        opened = asyncio.run(
            tool._run_parts(
                [
                    "playwright-cli",
                    f"-s={session}",
                    "open",
                    "about:blank",
                    "--browser=chrome",
                ]
            )
        )
        self.assertTrue(opened.success, opened.to_text())
        try:
            initialized = asyncio.run(
                tool._run_parts(
                    [
                        "playwright-cli",
                        f"-s={session}",
                        "eval",
                        (
                            "() => { document.body.innerHTML="
                            "'<label>Message <input id=message-input "
                            "placeholder=\"Write message\"></label>"
                            "<button id=submit>Submit order</button>'; "
                            "return true; }"
                        ),
                    ]
                )
            )
            self.assertTrue(initialized.success, initialized.to_text())
            selector = asyncio.run(
                tool.execute(selector="#message-input", session=session)
            )
            text = asyncio.run(
                tool.execute(text="Submit order", session=session)
            )
            role = asyncio.run(
                tool.execute(role="textbox", session=session)
            )
            placeholder = asyncio.run(
                tool.execute(placeholder="Write message", session=session)
            )
        finally:
            asyncio.run(
                tool._run_parts(
                    ["playwright-cli", f"-s={session}", "close"]
                )
            )

        for result in (selector, text, role, placeholder):
            self.assertTrue(result.success, result.to_text())
        for result in (selector, role, placeholder):
            self.assertIn('"count": 1', result.output)
        self.assertIn('"target": "#message-input"', selector.output)
        self.assertIn('"role": "textbox"', role.output)
        self.assertIn('"placeholder": "Write message"', placeholder.output)
        self.assertIn('"target": "#submit"', text.output)


@unittest.skipUnless(
    PLAYWRIGHT_CLI and RUN_LOCAL_BROWSER_TESTS,
    (
        "local Chrome integration test skipped: requires playwright-cli and "
        "MYBOT_RUN_BROWSER_INTEGRATION=1"
    ),
)
class LocalChromeIntegrationTests(unittest.TestCase):
    def test_attach_and_list_tabs(self) -> None:
        attached = run_cli("attach", "--cdp=chrome", "-s=local_browser")
        self.assertEqual(
            attached.returncode,
            0,
            attached.stderr or attached.stdout,
        )

        tabs = run_cli("-s=local_browser", "tab-list")
        self.assertEqual(tabs.returncode, 0, tabs.stderr or tabs.stdout)


if __name__ == "__main__":
    unittest.main()
