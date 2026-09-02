from __future__ import annotations

import unittest

from mcp import Client
from mcp.server import MCPServer
from mcp_types import ToolAnnotations

from mybot.mcp import MCPServerConfig, MCPToolAdapter


class OfficialMCPIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_client_lists_and_calls_in_process_server(self):
        server = MCPServer("mybot-phase4-test")

        @server.tool(
            annotations=ToolAnnotations(
                readOnlyHint=True,
                idempotentHint=True,
            )
        )
        def greet(name: str) -> str:
            """Return a deterministic greeting."""
            return f"hello {name}"

        async with Client(server) as client:
            listed = await client.list_tools()
            self.assertEqual([tool.name for tool in listed.tools], ["greet"])
            adapter = MCPToolAdapter(
                client=client,
                server_config=MCPServerConfig(
                    name="in_process",
                    command="unused",
                    trust_annotations=True,
                ),
                mcp_tool=listed.tools[0],
                local_name="mcp__in_process__greet",
                protocol_version=str(client.protocol_version),
            )
            result = await adapter.execute(name="Codex")

        self.assertTrue(result.success)
        self.assertIn("hello Codex", result.output)
        self.assertIn("structuredContent", result.output)
        self.assertEqual(result.metadata["tool_source"], "mcp")
        self.assertTrue(result.metadata["read_only_hint"])
        self.assertTrue(result.metadata["protocol_version"])


if __name__ == "__main__":
    unittest.main()
