"""Optional playwright-cli integration tests.

Unit tests for browser command construction and result handling live in the other
browser test modules and never require a real browser.
"""

import os
import shutil
import subprocess
import unittest


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
