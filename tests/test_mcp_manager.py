from __future__ import annotations

import unittest
from unittest.mock import patch
from types import SimpleNamespace

from mcp_types import Tool

from mybot.mcp import (
    MCPClientManager,
    MCPConfig,
    MCPServerConfig,
    MCPStartupError,
)
from mybot.tools import ToolRegistry
from mybot.tools.base import Tool as NativeTool
from mybot.tools.result import ToolResult


def external_tool(name="search", schema=None):
    return Tool(
        name=name,
        description=f"External {name}",
        inputSchema=schema
        or {"type": "object", "properties": {"query": {"type": "string"}}},
    )


class FakeClient:
    def __init__(self, tools, protocol="sdk-negotiated", list_error=None):
        self.tools = tools
        self.protocol_version = protocol
        self.list_error = list_error
        self.list_calls = 0

    async def list_tools(self, *, cursor=None):
        self.list_calls += 1
        if self.list_error:
            raise self.list_error
        return SimpleNamespace(
            tools=self.tools,
            next_cursor=None,
            result_type="complete",
        )


class FakeFactory:
    def __init__(self, clients=None, failures=None):
        self.clients = clients or {}
        self.failures = failures or {}
        self.connected = []
        self.closed = []

    async def connect(self, config, stack):
        self.connected.append(config.name)
        if config.name in self.failures:
            raise self.failures[config.name]
        stack.callback(self._close, config.name)
        return self.clients[config.name]

    def _close(self, name):
        self.closed.append(name)


class NativeCollisionTool(NativeTool):
    @property
    def name(self):
        return "mcp__demo__search"

    @property
    def description(self):
        return "native collision"

    @property
    def parameters(self):
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return ToolResult(success=True, output="native")


class MCPClientManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_and_server_disabled_do_not_connect(self):
        servers = (
            MCPServerConfig(name="a", command="python"),
            MCPServerConfig(name="b", command="python", enabled=False),
        )
        factory = FakeFactory()
        manager = MCPClientManager(
            MCPConfig(enabled=False, servers=servers),
            ToolRegistry(),
            factory,
        )
        await manager.start()
        self.assertEqual(factory.connected, [])
        self.assertFalse(manager.get_status("a").enabled)
        await manager.close()
        await manager.close()

    async def test_optional_failure_is_isolated(self):
        server = MCPServerConfig(name="optional", command="missing")
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=(server,)),
            ToolRegistry(),
            FakeFactory(failures={"optional": FileNotFoundError("missing")}),
        )
        adapters = await manager.start()
        self.assertEqual(adapters, ())
        status = manager.get_status("optional")
        self.assertFalse(status.connected)
        self.assertIn("FileNotFoundError", status.error)
        await manager.close()

    async def test_optional_missing_header_env_is_connection_failure(self):
        server = MCPServerConfig(
            name="remote",
            transport="streamable_http",
            url="http://127.0.0.1:8000/mcp",
            headers={"Authorization": "Bearer ${MCP_MISSING_HEADER}"},
        )
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=(server,)),
            ToolRegistry(),
        )
        with patch.dict("os.environ", {}, clear=True):
            await manager.start()
        status = manager.get_status("remote")
        self.assertFalse(status.connected)
        self.assertIn("MCP_MISSING_HEADER", status.error)
        await manager.close()

    async def test_server_status_redacts_configured_secret(self):
        server = MCPServerConfig(
            name="optional",
            command="missing",
            env={"TOKEN": "${MCP_STATUS_SECRET}"},
        )
        factory = FakeFactory(
            failures={"optional": RuntimeError("failed with secret-value")}
        )
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=(server,)),
            ToolRegistry(),
            factory,
        )
        with patch.dict("os.environ", {"MCP_STATUS_SECRET": "secret-value"}):
            await manager.start()
        self.assertNotIn(
            "secret-value",
            manager.get_status("optional").error,
        )
        await manager.close()

    async def test_required_failure_stops_startup_and_closes_prior_clients(self):
        first = MCPServerConfig(name="first", command="python")
        required = MCPServerConfig(
            name="required",
            command="missing",
            required=True,
        )
        factory = FakeFactory(
            clients={"first": FakeClient([external_tool()])},
            failures={"required": RuntimeError("cannot connect")},
        )
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=(first, required)),
            ToolRegistry(),
            factory,
        )
        with self.assertRaises(MCPStartupError) as raised:
            await manager.start()
        self.assertIn("required", str(raised.exception))
        self.assertIn("stdio", str(raised.exception))
        self.assertEqual(factory.closed, ["first"])

    async def test_multiple_servers_discover_register_and_close(self):
        servers = (
            MCPServerConfig(name="github", command="python"),
            MCPServerConfig(
                name="notion",
                transport="streamable_http",
                url="http://localhost/mcp",
            ),
        )
        factory = FakeFactory(
            clients={
                "github": FakeClient([external_tool("search_code")]),
                "notion": FakeClient([external_tool("search")]),
            }
        )
        registry = ToolRegistry()
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=servers),
            registry,
            factory,
        )
        adapters = await manager.start()
        self.assertEqual(len(adapters), 2)
        self.assertTrue(registry.has_tool("mcp__github__search_code"))
        self.assertTrue(registry.has_tool("mcp__notion__search"))
        self.assertEqual(manager.get_status("github").tool_count, 1)
        self.assertEqual(
            manager.get_status("github").protocol_version,
            "sdk-negotiated",
        )
        await manager.close()
        self.assertCountEqual(factory.closed, ["github", "notion"])
        self.assertFalse(manager.get_status("github").connected)

    async def test_invalid_schema_is_skipped_and_recorded(self):
        server = MCPServerConfig(name="demo", command="python")
        client = FakeClient(
            [external_tool("bad", schema={"type": "string"})]
        )
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=(server,)),
            ToolRegistry(),
            FakeFactory(clients={"demo": client}),
        )
        await manager.start()
        status = manager.get_status("demo")
        self.assertTrue(status.connected)
        self.assertEqual(status.tool_count, 0)
        self.assertIn("UnsupportedMCPSchema", status.discovery_errors[0])
        await manager.close()

    async def test_collision_never_overwrites_existing_tool(self):
        registry = ToolRegistry()
        native = NativeCollisionTool()
        registry.register(native)
        server = MCPServerConfig(name="demo", command="python")
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=(server,)),
            registry,
            FakeFactory(clients={"demo": FakeClient([external_tool()])}),
        )
        adapters = await manager.start()
        self.assertEqual(len(adapters), 1)
        self.assertNotEqual(adapters[0].name, native.name)
        self.assertEqual(
            registry.get_runtime_metadata(native.name),
            {},
        )
        self.assertTrue(registry.has_tool(adapters[0].name))
        await manager.close()

    async def test_duplicate_external_name_is_not_silently_overwritten(self):
        server = MCPServerConfig(name="demo", command="python")
        manager = MCPClientManager(
            MCPConfig(enabled=True, servers=(server,)),
            ToolRegistry(),
            FakeFactory(
                clients={
                    "demo": FakeClient(
                        [external_tool("same"), external_tool("same")]
                    )
                }
            ),
        )
        await manager.start()
        status = manager.get_status("demo")
        self.assertEqual(status.tool_count, 1)
        self.assertIn("duplicate external", status.discovery_errors[0])
        await manager.close()


if __name__ == "__main__":
    unittest.main()
