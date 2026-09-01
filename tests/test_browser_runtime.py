import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from mybot.tools.browser.connection import BrowserAttachTool
from mybot.tools.browser.interaction import BrowserClickTool
from mybot.tools.browser.session import BrowserSessionManager


class FakeProcess:
    def __init__(
        self,
        returncode: int | None,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.returncode = -9


class HangingProcess(FakeProcess):
    def __init__(self):
        super().__init__(returncode=None)

    async def communicate(self) -> tuple[bytes, bytes]:
        if self.returncode is None:
            await asyncio.Event().wait()
        return b"", b""


class BrowserSessionManagerTests(unittest.TestCase):
    def test_default_set_resolve_and_clear(self) -> None:
        sessions = BrowserSessionManager()

        self.assertEqual(sessions.resolve(), "managed_browser")
        self.assertEqual(sessions.set_active("local_browser"), "local_browser")
        self.assertEqual(sessions.resolve(), "local_browser")
        self.assertEqual(sessions.resolve("managed_browser"), "managed_browser")

        sessions.clear("managed_browser")
        self.assertEqual(sessions.resolve(), "local_browser")

        sessions.clear("local_browser")
        self.assertEqual(sessions.resolve(), "managed_browser")


class BrowserCliResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sessions = BrowserSessionManager()

    def test_success_returns_browser_result_and_sets_active_session(self) -> None:
        process = FakeProcess(0, stdout=b"connected")
        tool = BrowserAttachTool(self.sessions)

        with patch(
            "mybot.tools.browser.base.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ):
            result = asyncio.run(tool.execute())

        self.assertTrue(result.success)
        self.assertEqual(result.action, "attach")
        self.assertEqual(result.session, "local_browser")
        self.assertEqual(result.output, "connected")
        self.assertEqual(result.metadata["exit_code"], 0)
        self.assertFalse(result.metadata["output_truncated"])
        self.assertEqual(self.sessions.resolve(), "local_browser")

    def test_nonzero_exit_preserves_stdout_stderr_and_active_session(self) -> None:
        self.sessions.set_active("local_browser")
        process = FakeProcess(2, stdout=b"partial", stderr=b"failure detail")
        tool = BrowserClickTool(self.sessions)

        with patch(
            "mybot.tools.browser.base.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=process),
        ):
            result = asyncio.run(
                tool.execute("e12", session="managed_browser")
            )

        self.assertFalse(result.success)
        self.assertEqual(result.action, "click")
        self.assertEqual(result.session, "managed_browser")
        self.assertIn("code 2", result.error)
        self.assertIn("partial", result.output)
        self.assertIn("STDERR", result.output)
        self.assertEqual(result.metadata["exit_code"], 2)
        self.assertEqual(self.sessions.resolve(), "local_browser")

    def test_missing_cli_returns_structured_failure(self) -> None:
        tool = BrowserClickTool(self.sessions)

        with patch(
            "mybot.tools.browser.base.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=FileNotFoundError),
        ):
            result = asyncio.run(tool.execute("e12"))

        self.assertFalse(result.success)
        self.assertEqual(result.action, "click")
        self.assertIn("not found", result.error)
        self.assertTrue(result.metadata["missing_cli"])

    def test_unexpected_exception_returns_structured_failure(self) -> None:
        tool = BrowserClickTool(self.sessions)

        with patch(
            "mybot.tools.browser.base.asyncio.create_subprocess_exec",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = asyncio.run(tool.execute("e12"))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "RuntimeError: boom")

    def test_timeout_kills_process_and_returns_structured_failure(self) -> None:
        process = HangingProcess()
        tool = BrowserClickTool(self.sessions)

        with (
            patch(
                "mybot.tools.browser.base.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=process),
            ),
            patch("mybot.tools.browser.base.COMMAND_TIMEOUT_SECONDS", 0.001),
        ):
            result = asyncio.run(tool.execute("e12"))

        self.assertFalse(result.success)
        self.assertIn("timed out", result.error)
        self.assertTrue(result.metadata["timed_out"])
        self.assertEqual(process.returncode, -9)


if __name__ == "__main__":
    unittest.main()
