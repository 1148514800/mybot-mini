from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from .config import MCPServerConfig


class MCPClientFactory:
    """Build connected official SDK v2 clients for supported transports."""

    async def connect(
        self,
        config: MCPServerConfig,
        stack: AsyncExitStack,
    ) -> Any:
        if config.transport == "stdio":
            parameters = StdioServerParameters(
                command=config.command or "",
                args=list(config.args),
                env=config.resolved_env() or None,
            )
            client = Client(
                parameters,
                read_timeout_seconds=config.tool_timeout_seconds,
                input_required_max_rounds=0,
            )
            return await stack.enter_async_context(client)

        headers = config.resolved_headers()
        http_client = await stack.enter_async_context(
            httpx2.AsyncClient(
                headers=headers or None,
                follow_redirects=True,
                timeout=httpx2.Timeout(config.tool_timeout_seconds),
            )
        )
        transport = streamable_http_client(
            config.url or "",
            http_client=http_client,
        )
        client = Client(
            transport,
            read_timeout_seconds=config.tool_timeout_seconds,
            input_required_max_rounds=0,
        )
        return await stack.enter_async_context(client)
