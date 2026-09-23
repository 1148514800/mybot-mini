import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from mybot.tools import build_default_tool_registry
from mybot.tools.browser.base import DEFAULT_SESSION, SNAPSHOT_MAX_OUTPUT_CHARS
from mybot.tools.browser.connection import BrowserAttachTool
from mybot.tools.browser.interaction import (
    BrowserInspectTool,
    BrowserLinksTool,
    BrowserSnapshotTool,
    BrowserVerifyTool,
)
from mybot.tools.browser.navigation import (
    MANAGED_BROWSER_SESSION,
    BrowserCloseTool,
    BrowserGotoTool,
    BrowserOpenTool,
    BrowserTabTool,
)
from mybot.tools.browser.session import BrowserSessionManager
from mybot.tools.result import BrowserResult


class BrowserSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sessions = BrowserSessionManager()

    def success(
        self,
        action: str = "test",
        session: str = "research",
    ) -> BrowserResult:
        return BrowserResult(
            success=True,
            action=action,
            session=session,
            output="ok",
        )

    def test_session_manager_keeps_active_session_for_injected_tools(self) -> None:
        tool = BrowserGotoTool(self.sessions)

        tool._record_session("novel_research")

        self.assertEqual(
            BrowserSnapshotTool(self.sessions)._resolve_session(),
            "novel_research",
        )

    def test_default_session_is_managed_browser(self) -> None:
        self.assertEqual(DEFAULT_SESSION, MANAGED_BROWSER_SESSION)

    def test_attach_uses_cdp_and_records_session(self) -> None:
        tool = BrowserAttachTool(self.sessions)
        tool._run_parts = AsyncMock(
            return_value=self.success("attach", "local_browser")
        )

        result = asyncio.run(tool.execute())

        tool._run_parts.assert_awaited_once_with(
            [
                "playwright-cli",
                "attach",
                "--cdp=chrome",
                "-s=local_browser",
            ]
        )
        self.assertTrue(result.success)

    def test_attach_has_no_launch_or_endpoint_options(self) -> None:
        properties = BrowserAttachTool(self.sessions).parameters["properties"]

        self.assertEqual(properties, {})

    def test_open_uses_fixed_persistent_managed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            tool = BrowserOpenTool(workspace, self.sessions)
            tool._run_parts = AsyncMock(
                return_value=self.success("open", MANAGED_BROWSER_SESSION)
            )

            asyncio.run(tool.execute("https://example.com"))

            expected_profile = (
                workspace / "browser_profiles" / "managed_browser"
            ).resolve()
            tool._run_parts.assert_awaited_once_with(
                [
                    "playwright-cli",
                    "-s=managed_browser",
                    "open",
                    "https://example.com",
                    "--browser=chrome",
                    "--headed",
                    f"--profile={expected_profile}",
                ]
            )
            self.assertTrue(expected_profile.is_dir())

    def test_open_schema_does_not_expose_profile_or_browser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            properties = BrowserOpenTool(
                Path(temporary_directory),
                self.sessions,
            ).parameters["properties"]

        self.assertEqual(set(properties), {"url"})

    def test_tab_tool_maps_select_and_close_commands(self) -> None:
        tool = BrowserTabTool(self.sessions)
        tool._run_parts = AsyncMock(return_value=self.success("tab"))

        asyncio.run(tool.execute("select", index=3, session="research"))
        asyncio.run(tool.execute("close", index=1, session="research"))

        self.assertEqual(
            tool._run_parts.await_args_list[0].args[0],
            ["playwright-cli", "-s=research", "tab-select", "3"],
        )
        self.assertEqual(
            tool._run_parts.await_args_list[1].args[0],
            ["playwright-cli", "-s=research", "tab-close", "1"],
        )

    def test_tab_tool_requires_index_for_select(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(BrowserTabTool(self.sessions).execute("select"))

    def test_default_registry_uses_unified_tab_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            registry = build_default_tool_registry(Path(temporary_directory))

        tool_names = {
            definition["function"]["name"]
            for definition in registry.get_definitions()
        }
        self.assertIn("browser_tab", tool_names)
        self.assertIn("browser_links", tool_names)
        self.assertIn("browser_inspect", tool_names)
        self.assertIn("browser_verify", tool_names)
        self.assertIn("browser_attach", tool_names)
        self.assertIn("browser_open", tool_names)
        self.assertNotIn("browser_new_tab", tool_names)

        browser_tools = [
            tool
            for tool in registry._tools.values()
            if tool.name.startswith("browser_")
        ]
        self.assertTrue(browser_tools)
        manager = browser_tools[0].session_manager
        self.assertTrue(
            all(tool.session_manager is manager for tool in browser_tools)
        )

    def test_snapshot_returns_inline_output_with_bounded_depth(self) -> None:
        tool = BrowserSnapshotTool(self.sessions)
        tool._run_parts = AsyncMock(return_value=self.success("snapshot"))

        asyncio.run(tool.execute(session="research", target="e12"))

        tool._run_parts.assert_awaited_once_with(
            [
                "playwright-cli",
                "-s=research",
                "snapshot",
                "--filename=",
                "--depth=8",
                "e12",
            ],
            max_output_chars=SNAPSHOT_MAX_OUTPUT_CHARS,
        )

    def test_snapshot_rejects_invalid_depth(self) -> None:
        tool = BrowserSnapshotTool(self.sessions)

        with self.assertRaises(ValueError):
            asyncio.run(tool.execute(depth=0))
        with self.assertRaises(ValueError):
            asyncio.run(tool.execute(depth="8"))

    def test_links_uses_visual_order_script_and_target(self) -> None:
        tool = BrowserLinksTool(self.sessions)
        tool._run_parts = AsyncMock(return_value=self.success("links"))

        asyncio.run(
            tool.execute(
                target=".video-list",
                url_contains="/video/",
                limit=10,
                session="research",
            )
        )

        parts = tool._run_parts.await_args.args[0]
        self.assertEqual(parts[:3], ["playwright-cli", "-s=research", "eval"])
        self.assertIn('const urlFilter="/video/"', parts[3])
        self.assertIn("candidates.sort", parts[3])
        self.assertIn("seen.has(key)", parts[3])
        self.assertEqual(parts[4], ".video-list")

    def test_links_rejects_invalid_limit(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(BrowserLinksTool(self.sessions).execute(limit=0))

    def test_inspect_builds_fixed_script_from_structured_query(self) -> None:
        tool = BrowserInspectTool(self.sessions)
        tool._run_parts = AsyncMock(return_value=self.success("inspect"))

        asyncio.run(
            tool.execute(
                role="button",
                text="发送",
                exact=True,
                limit=5,
                session="research",
            )
        )

        parts = tool._run_parts.await_args.args[0]
        self.assertEqual(parts[:3], ["playwright-cli", "-s=research", "eval"])
        encoded = parts[3].split("atob('", 1)[1].split("')", 1)[0]
        query = json.loads(base64.b64decode(encoded).decode("ascii"))
        self.assertEqual(query["role"], "button")
        self.assertEqual(query["text"], "发送")
        self.assertFalse(query["verify"])
        self.assertIn("document.querySelectorAll", parts[3])
        self.assertNotIn("script", tool.parameters["properties"])

    def test_verify_uses_fixed_structured_postcondition(self) -> None:
        tool = BrowserVerifyTool(self.sessions)
        tool._run_parts = AsyncMock(return_value=self.success("verify"))

        result = asyncio.run(
            tool.execute(
                text="Saved",
                url_contains="/done",
                session="research",
            )
        )

        parts = tool._run_parts.await_args.args[0]
        encoded = parts[3].split("atob('", 1)[1].split("')", 1)[0]
        query = json.loads(base64.b64decode(encoded).decode("ascii"))
        self.assertTrue(query["verify"])
        self.assertEqual(query["text"], "Saved")
        self.assertEqual(query["url_contains"], "/done")
        self.assertTrue(result.metadata["postcondition_met"])
        self.assertNotIn("script", tool.parameters["properties"])

    def test_inspect_requires_a_structured_filter(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires selector"):
            asyncio.run(BrowserInspectTool(self.sessions).execute())

    def test_truncated_output_has_an_explicit_marker(self) -> None:
        tool = BrowserSnapshotTool(self.sessions)

        result = tool._truncate_output("x" * 100, 80)

        self.assertEqual(len(result), 80)
        self.assertIn("output truncated", result)

    def test_closing_active_session_resets_to_default(self) -> None:
        tool = BrowserCloseTool(self.sessions)
        tool._record_session("research")
        tool._run_parts = AsyncMock(return_value=self.success("close"))

        asyncio.run(tool.execute(session="research"))

        self.assertEqual(tool._resolve_session(), DEFAULT_SESSION)

    def test_failed_close_does_not_clear_active_session(self) -> None:
        tool = BrowserCloseTool(self.sessions)
        tool._record_session("research")
        tool._run_parts = AsyncMock(
            return_value=BrowserResult(
                success=False,
                action="close",
                session="research",
                error="close failed",
            )
        )

        asyncio.run(tool.execute(session="research"))

        self.assertEqual(tool._resolve_session(), "research")


if __name__ == "__main__":
    unittest.main()
