from __future__ import annotations

import asyncio
import unittest

from mcp_types import (
    CallToolResult,
    ImageContent,
    TextContent,
    Tool,
    ToolAnnotations,
)

from mybot.mcp import MCPServerConfig, MCPToolAdapter, UnsupportedMCPSchema
from mybot.tracing import REDACTED


class FakeClient:
    def __init__(self, result=None, *, delay=0, error=None):
        self.result = result
        self.delay = delay
        self.error = error
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def server_config(**overrides):
    values = {
        "name": "demo",
        "transport": "stdio",
        "command": "python",
    }
    values.update(overrides)
    return MCPServerConfig(**values)


def mcp_tool(**overrides):
    values = {
        "name": "search",
        "description": "Search external data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "enum": ["a", "b"]},
                "options": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                },
            },
            "required": ["query"],
        },
        "annotations": ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
        ),
    }
    values.update(overrides)
    return Tool(**values)


class MCPToolAdapterTests(unittest.IsolatedAsyncioTestCase):
    def make_adapter(self, client, tool=None, config=None):
        return MCPToolAdapter(
            client=client,
            server_config=config or server_config(),
            mcp_tool=tool or mcp_tool(),
            local_name="mcp__demo__search",
            protocol_version="2026-test-version",
        )

    async def test_schema_description_execution_and_metadata(self):
        client = FakeClient(
            CallToolResult(
                content=[TextContent(text="found")],
                structuredContent={"count": 1},
            )
        )
        adapter = self.make_adapter(client)
        result = await adapter.execute(query="a", options={"limit": 2})

        self.assertEqual(adapter.parameters["required"], ["query"])
        self.assertEqual(
            adapter.parameters["properties"]["query"]["enum"],
            ["a", "b"],
        )
        self.assertEqual(adapter.description, "Search external data")
        self.assertTrue(result.success)
        self.assertIn("found", result.output)
        self.assertIn('structuredContent={"count":1}', result.output)
        self.assertEqual(client.calls, [("search", {"query": "a", "options": {"limit": 2}})])
        self.assertEqual(result.metadata["tool_source"], "mcp")
        self.assertEqual(result.metadata["mcp_server"], "demo")
        self.assertTrue(result.metadata["read_only_hint"])
        self.assertTrue(result.metadata["idempotent_hint"])

    async def test_mcp_error_becomes_tool_result_failure(self):
        adapter = self.make_adapter(
            FakeClient(
                CallToolResult(
                    content=[TextContent(text="external failure")],
                    isError=True,
                )
            )
        )
        result = await adapter.execute(query="a")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "external failure")

    async def test_large_output_is_truncated(self):
        config = server_config(max_output_chars=10)
        adapter = self.make_adapter(
            FakeClient(CallToolResult(content=[TextContent(text="x" * 40)])),
            config=config,
        )
        result = await adapter.execute(query="a")
        self.assertEqual(result.output, "x" * 10)
        self.assertTrue(result.metadata["output_truncated"])
        self.assertEqual(result.metadata["original_output_chars"], 40)

    async def test_timeout_returns_failure_without_retry(self):
        client = FakeClient(
            CallToolResult(content=[TextContent(text="late")]),
            delay=0.05,
        )
        adapter = self.make_adapter(
            client,
            config=server_config(tool_timeout_seconds=0.01),
        )
        result = await adapter.execute(query="a")
        self.assertFalse(result.success)
        self.assertTrue(result.metadata["timed_out"])
        self.assertEqual(len(client.calls), 1)

    async def test_multimodal_and_input_required_are_explicitly_unsupported(self):
        image_adapter = self.make_adapter(
            FakeClient(
                CallToolResult(
                    content=[ImageContent(data="base64", mimeType="image/png")]
                )
            )
        )
        image_result = await image_adapter.execute(query="a")
        self.assertTrue(image_result.success)
        self.assertNotIn("base64", image_result.output)
        self.assertIn("not supported", image_result.output)

        pending_adapter = self.make_adapter(
            FakeClient(CallToolResult(content=[], resultType="input_required"))
        )
        pending_result = await pending_adapter.execute(query="a")
        self.assertFalse(pending_result.success)
        self.assertEqual(
            pending_result.metadata["unsupported_result_type"],
            "input_required",
        )
        task_adapter = self.make_adapter(
            FakeClient(CallToolResult(content=[], resultType="task_required"))
        )
        task_result = await task_adapter.execute(query="a")
        self.assertFalse(task_result.success)
        self.assertEqual(
            task_result.metadata["unsupported_result_type"],
            "task_required",
        )

    async def test_client_exception_is_failure_and_not_raised(self):
        adapter = self.make_adapter(FakeClient(error=RuntimeError("broken")))
        result = await adapter.execute(query="a")
        self.assertFalse(result.success)
        self.assertIn("RuntimeError", result.error)

    async def test_external_secret_fields_are_redacted(self):
        adapter = self.make_adapter(
            FakeClient(
                CallToolResult(
                    content=[TextContent(text="authorization=raw-auth")],
                    structuredContent={"token": "raw-token", "ok": True},
                )
            )
        )
        result = await adapter.execute(query="a")
        self.assertNotIn("raw-auth", result.output)
        self.assertNotIn("raw-token", result.output)
        self.assertIn(REDACTED, result.output)

    def test_description_limit_and_invalid_schema(self):
        adapter = self.make_adapter(
            FakeClient(None),
            tool=mcp_tool(description="x" * 3000),
        )
        self.assertEqual(len(adapter.description), 2000)
        self.assertTrue(adapter.runtime_metadata["description_truncated"])
        with self.assertRaises(UnsupportedMCPSchema):
            self.make_adapter(
                FakeClient(None),
                tool=mcp_tool(inputSchema={"type": "string"}),
            )


if __name__ == "__main__":
    unittest.main()
