from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

from ..config import PROJECT_DIR
from ..tools import ToolResult
from .adapter import MCPToolAdapter, DefinitionError
from .config import validate_mcp


def failure_kind(exc):
    if isinstance(exc,BaseExceptionGroup):
        kinds = [failure_kind(e) for e in exc.exceptions]
        return next((k for k in kinds if k!='protocol_or_connection_error'),kinds[0])
    if isinstance(exc,FileNotFoundError):return 'executable_not_found'
    if isinstance(exc,TimeoutError) or (isinstance(exc,MCPError) and exc.code==-32001):return 'timeout'
    if isinstance(exc,ValueError):return 'invalid_configuration_or_definition'
    return 'protocol_or_connection_error'


class MCPStartupError(RuntimeError):
    pass


class MCPClientManager:
    """Own SDK contexts in the gateway task; adapters only issue tools/call."""
    def __init__(self,config,registry):
        self.enabled = config.mcp_enabled
        self.servers = validate_mcp(self.enabled,config.mcp_servers)
        self.registry = registry
        self.clients,self.protocols = {},{}
        self.stack = None
        self.closed = False
        self.owner = None

    async def __aenter__(self):
        if self.stack is not None or self.closed:
            raise RuntimeError('MCP manager cannot be reentered')
        self.owner = asyncio.current_task()
        self.stack = AsyncExitStack()
        if not self.enabled:
            return self
        adapters = {}
        try:
            for name,config in sorted(self.servers.items()):
                stage = 'connect/initialize'
                # SDK only inherits its small default environment; stderr is not stdout.
                errlog = self.stack.enter_context(open(os.devnull,'w'))
                parameters = StdioServerParameters(command=config['command'],args=config.get('args',[]),cwd=PROJECT_DIR)
                transport = stdio_client(parameters,errlog=errlog)
                client = Client(transport,mode='legacy',read_timeout_seconds=config.get('timeout_seconds',10),cache=None)
                # No wait_for around __aenter__: SDK cancel scopes must stay in this task.
                await self.stack.enter_async_context(client)
                self.clients[name] = client
                self.protocols[name] = client.protocol_version
                cursor,seen,total = None,set(),0
                while True:
                    stage = 'tools/list'
                    listed = await client.list_tools(cursor=cursor)
                    total += len(listed.tools)
                    if total>256:
                        raise ValueError('MCP tool discovery limit exceeded')
                    for definition in listed.tools:
                        if definition.name in config['allowed_tools']:
                            stage = 'tool definition'
                            adapter = MCPToolAdapter(self,name,definition)
                            if adapter.name in adapters or self.registry.has_tool(adapter.name):
                                raise ValueError('MCP tool name collision')
                            adapters[adapter.name] = adapter
                    cursor = listed.next_cursor
                    if not cursor:break
                    if cursor in seen or len(seen)>=16:
                        raise ValueError('MCP pagination limit exceeded')
                    seen.add(cursor)
                missing = set(config['allowed_tools'])-{a.remote_name for a in adapters.values() if a.server==name}
                if missing:
                    raise ValueError('An allowed MCP tool is not advertised by the server')
            for key in sorted(adapters):self.registry.register(adapters[key])
            return self
        except BaseException as exc:
            await self.stack.aclose()
            self.clients.clear()
            self.closed = True
            if isinstance(exc,asyncio.CancelledError):raise
            # Never expose external error text, command arguments, stderr or credentials.
            reason = str(exc) if isinstance(exc,DefinitionError) else failure_kind(exc)
            raise MCPStartupError(f"MCP server '{name}': {stage} failed ({reason}); check trusted server configuration") from None

    async def call(self,server,name,arguments):
        if asyncio.current_task() is not self.owner:
            return ToolResult(success=False,error='MCP calls must run in the owning gateway task')
        if self.closed or server not in self.clients or name not in self.servers[server]['allowed_tools']:
            return ToolResult(success=False,error='MCP tool is unavailable or not allowed; restart gateway if disconnected')
        try:
            result = await self.clients[server].call_tool(name,arguments,read_timeout_seconds=self.servers[server].get('timeout_seconds',10))
            return MCPToolAdapter.result(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            kind = failure_kind(exc)
            # SDK context teardown must stay in the owner task, not a wait_for child.
            self.closed = True
            try:
                await self.stack.aclose()
            finally:
                self.clients.clear()
            return ToolResult(success=False,error=f'MCP call failed ({kind}); MCP connections closed, restart gateway',metadata={'mcp_failure':kind})

    async def __aexit__(self,*exc):
        if asyncio.current_task() is not self.owner:
            raise RuntimeError('MCP contexts must close in their owning gateway task')
        try:
            if self.stack is not None:await self.stack.aclose()
        finally:
            self.closed = True
            self.clients.clear()
