import asyncio
import unittest

from mybot.tools.base import Tool
from mybot.tools.registry import ToolRegistry
from mybot.tools.result import BrowserResult, ToolResult


class LegacyTool(Tool):
    def __init__(self, result: str):
        self._result = result

    @property
    def name(self) -> str:
        return "legacy"

    @property
    def description(self) -> str:
        return "Legacy string tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> str:
        return self._result


class ToolResultTests(unittest.TestCase):
    def test_success_serializes_output_without_extra_status_tokens(self) -> None:
        result = ToolResult(success=True, output="completed")

        self.assertEqual(result.to_text(), "completed")

    def test_failure_serializes_error_and_output(self) -> None:
        result = ToolResult(
            success=False,
            error="command failed",
            output="diagnostic output",
        )

        self.assertEqual(
            result.to_text(),
            "Error: command failed\n\ndiagnostic output",
        )

    def test_metadata_uses_compact_json(self) -> None:
        result = ToolResult(
            success=True,
            output="ok",
            metadata={"count": 2, "source": "unit"},
        )

        self.assertEqual(
            result.to_text(),
            'ok\n\nmetadata={"count":2,"source":"unit"}',
        )

    def test_browser_result_includes_action_and_session_but_omits_nulls(self) -> None:
        result = BrowserResult(
            success=True,
            action="snapshot",
            session="managed_browser",
            output="heading Example\nbutton Continue ref=e12",
        )

        text = result.to_text()

        self.assertIn("[browser success action=snapshot session=managed_browser]", text)
        self.assertIn("button Continue ref=e12", text)
        self.assertNotIn("None", text)
        self.assertNotIn("null", text)

    def test_registry_adapts_legacy_success_and_failure_strings(self) -> None:
        registry = ToolRegistry()
        registry.register(LegacyTool("legacy output"))

        success = asyncio.run(registry.execute("legacy", {}))
        self.assertTrue(success.success)
        self.assertEqual(success.output, "legacy output")

        registry.register(LegacyTool("Error: legacy failure"))
        failure = asyncio.run(registry.execute("legacy", {}))
        self.assertFalse(failure.success)
        self.assertEqual(failure.error, "legacy failure")

    def test_registry_returns_structured_unknown_tool_failure(self) -> None:
        result = asyncio.run(ToolRegistry().execute("missing", {}))

        self.assertFalse(result.success)
        self.assertIn("Unknown tool", result.error)


if __name__ == "__main__":
    unittest.main()
