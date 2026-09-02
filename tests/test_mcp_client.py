from __future__ import annotations

import os
import unittest
from contextlib import AsyncExitStack
from types import SimpleNamespace
from unittest.mock import patch

from mcp import StdioServerParameters

from mybot.mcp import MCPClientFactory, MCPServerConfig


class AsyncContext:
    def __init__(self, value):
        self.value = value
        self.closed = False

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback):
        self.closed = True


class MCPClientFactoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_uses_official_parameters_and_client_lifecycle(self):
        connected = SimpleNamespace(protocol_version="test")
        client_context = AsyncContext(connected)
        config = MCPServerConfig(
            name="local",
            command="python",
            args=("-m", "server"),
            env={"TOKEN": "${MCP_CLIENT_TEST_TOKEN}"},
        )
        with patch.dict(os.environ, {"MCP_CLIENT_TEST_TOKEN": "secret"}), patch(
            "mybot.mcp.client.Client",
            return_value=client_context,
        ) as client_class:
            async with AsyncExitStack() as stack:
                result = await MCPClientFactory().connect(config, stack)
                self.assertIs(result, connected)
                parameters = client_class.call_args.args[0]
                self.assertIsInstance(parameters, StdioServerParameters)
                self.assertEqual(parameters.command, "python")
                self.assertEqual(parameters.args, ["-m", "server"])
                self.assertEqual(parameters.env, {"TOKEN": "secret"})
            self.assertTrue(client_context.closed)

    async def test_streamable_http_uses_official_transport_with_headers(self):
        connected = SimpleNamespace(protocol_version="test")
        client_context = AsyncContext(connected)
        http_object = object()
        http_context = AsyncContext(http_object)
        transport = object()
        config = MCPServerConfig(
            name="remote",
            transport="streamable_http",
            url="http://127.0.0.1:8000/mcp",
            headers={"Authorization": "Bearer ${MCP_HTTP_TEST_TOKEN}"},
        )
        with patch.dict(os.environ, {"MCP_HTTP_TEST_TOKEN": "secret"}), patch(
            "mybot.mcp.client.httpx2.AsyncClient",
            return_value=http_context,
        ) as http_class, patch(
            "mybot.mcp.client.streamable_http_client",
            return_value=transport,
        ) as streamable, patch(
            "mybot.mcp.client.Client",
            return_value=client_context,
        ) as client_class:
            async with AsyncExitStack() as stack:
                result = await MCPClientFactory().connect(config, stack)
                self.assertIs(result, connected)
                self.assertEqual(
                    http_class.call_args.kwargs["headers"],
                    {"Authorization": "Bearer secret"},
                )
                streamable.assert_called_once_with(
                    "http://127.0.0.1:8000/mcp",
                    http_client=http_object,
                )
                self.assertIs(client_class.call_args.args[0], transport)
            self.assertTrue(client_context.closed)
            self.assertTrue(http_context.closed)


if __name__ == "__main__":
    unittest.main()
