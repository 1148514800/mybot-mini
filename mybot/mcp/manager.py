from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

from ..tools.registry import ToolRegistry
from ..tracing import redact_text
from .adapter import MCPToolAdapter, UnsupportedMCPSchema
from .client import MCPClientFactory
from .config import MCPConfig, MCPServerConfig
from .models import MCPServerStatus, MCPStartupError
from .naming import build_mcp_tool_name, resolve_name_collision


class MCPClientManager:
    """Own MCP client lifecycles and register discovered tools once at startup."""

    def __init__(
        self,
        config: MCPConfig,
        registry: ToolRegistry,
        client_factory: MCPClientFactory | Any | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.client_factory = client_factory or MCPClientFactory()
        self._stack: AsyncExitStack | None = None
        self._started = False
        self._closed = False
        self._clients: dict[str, Any] = {}
        self._adapters: list[MCPToolAdapter] = []
        self._statuses: dict[str, MCPServerStatus] = {}

    @property
    def adapters(self) -> tuple[MCPToolAdapter, ...]:
        return tuple(self._adapters)

    @property
    def statuses(self) -> tuple[MCPServerStatus, ...]:
        return tuple(self._statuses.values())

    def get_status(self, server_name: str) -> MCPServerStatus | None:
        return self._statuses.get(server_name)

    async def start(self) -> tuple[MCPToolAdapter, ...]:
        if self._started:
            return self.adapters
        self._started = True
        self._closed = False
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()

        for server in self.config.servers:
            status = MCPServerStatus(
                name=server.name,
                transport=server.transport,
                enabled=self.config.enabled and server.enabled,
                required=server.required,
            )
            self._statuses[server.name] = status
            if not self.config.enabled or not server.enabled:
                continue
            try:
                await self._connect_server(server, status)
            except Exception as exc:
                status.connected = False
                safe_error = server.redact_secrets(
                    redact_text(f"{type(exc).__name__}: {exc}")
                )
                status.error = safe_error
                if server.required:
                    await self.close()
                    raise MCPStartupError(
                        f"Required MCP server '{server.name}' "
                        f"({server.transport}) failed: {safe_error}"
                    ) from exc
        return self.adapters

    async def _connect_server(
        self,
        server: MCPServerConfig,
        status: MCPServerStatus,
    ) -> None:
        assert self._stack is not None
        server_stack = AsyncExitStack()
        await server_stack.__aenter__()
        try:
            client = await self.client_factory.connect(server, server_stack)
            tools = await self._list_all_tools(client)
        except BaseException:
            await server_stack.aclose()
            raise

        self._stack.push_async_callback(server_stack.aclose)
        self._clients[server.name] = client
        protocol = getattr(client, "protocol_version", None)
        status.protocol_version = str(protocol) if protocol else None
        status.connected = True

        occupied = {
            definition.get("function", {}).get("name", "")
            for definition in self.registry.get_definitions()
        }
        seen_external_names: set[str] = set()
        for mcp_tool in tools:
            external_name = str(getattr(mcp_tool, "name", ""))
            if not external_name:
                status.discovery_errors.append("skipped MCP tool with empty name")
                continue
            if external_name in seen_external_names:
                status.discovery_errors.append(
                    f"duplicate external MCP tool name '{external_name}'"
                )
                continue
            seen_external_names.add(external_name)

            candidate = build_mcp_tool_name(server.name, external_name)
            local_name = resolve_name_collision(
                candidate,
                server.name,
                external_name,
                occupied,
            )
            try:
                adapter = MCPToolAdapter(
                    client=client,
                    server_config=server,
                    mcp_tool=mcp_tool,
                    local_name=local_name,
                    protocol_version=status.protocol_version,
                )
                self.registry.register(adapter)
            except (UnsupportedMCPSchema, ValueError) as exc:
                status.discovery_errors.append(
                    f"tool '{external_name}' skipped: {type(exc).__name__}: {exc}"
                )
                continue
            occupied.add(local_name)
            self._adapters.append(adapter)
            status.tool_count += 1

    @staticmethod
    async def _list_all_tools(client: Any) -> list[Any]:
        tools: list[Any] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            result = await client.list_tools(cursor=cursor)
            result_type = str(getattr(result, "result_type", "complete"))
            if result_type != "complete":
                raise RuntimeError(
                    f"unsupported MCP tools/list result type '{result_type}'"
                )
            tools.extend(list(getattr(result, "tools", []) or []))
            next_cursor = getattr(result, "next_cursor", None)
            if not next_cursor:
                return tools
            if next_cursor in seen_cursors:
                raise RuntimeError("MCP tools/list returned a repeated cursor")
            seen_cursors.add(next_cursor)
            cursor = str(next_cursor)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._clients.clear()
        for status in self._statuses.values():
            status.connected = False
