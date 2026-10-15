from __future__ import annotations

import asyncio
import os
import json
import time
from collections import deque
from contextlib import AsyncExitStack

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

from ..config import PROJECT_DIR
from ..tools import ToolResult
from .adapter import MCPToolAdapter, DefinitionError
from .config import validate_mcp
from .approval import authorize


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
    def __init__(self,config,registry,approval_provider=None):
        self.enabled = config.mcp_enabled
        self.servers = validate_mcp(self.enabled,config.mcp_servers)
        self.registry = registry
        self.clients,self.protocols = {},{}
        self.stack = None
        self.closed = False
        self.owner = None
        self.approval_provider = approval_provider
        self._adapters = {}
        self._audit = deque(maxlen=256)
        self._policies = {(server,name): value.get("tool_policies",{}).get(name,"confirm")
                          for server,value in self.servers.items() for name in value["allowed_tools"]}

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
            self._adapters = {(a.server,a.remote_name):a for a in adapters.values()}
            for key in sorted(adapters):
                adapter = adapters[key]
                if self._policies[adapter.server,adapter.remote_name] != 'deny':
                    self.registry.register(adapter)
            return self
        except BaseException as exc:
            await self.stack.aclose()
            self.clients.clear()
            self.closed = True
            if isinstance(exc,asyncio.CancelledError):raise
            # Never expose external error text, command arguments, stderr or credentials.
            reason = str(exc) if isinstance(exc,DefinitionError) else failure_kind(exc)
            raise MCPStartupError(f"MCP server '{name}': {stage} failed ({reason}); check trusted server configuration") from None

    @property
    def audit(self):
        return [dict(event) for event in self._audit]

    async def call(self,server,name,arguments):
        started = time.perf_counter()
        policy = self._policies.get((server,name),'deny')
        event = dict(server=server if server in self.servers else '<unknown>',
                     tool=name if (server,name) in self._policies else '<unknown>',
                     policy=policy,decision='not_requested',executed=False,success=False,error=None)
        try:
            if asyncio.current_task() is not self.owner:
                event['error'] = 'wrong_task'
                return ToolResult(success=False,error='MCP calls must run in the owning gateway task')
            if policy == 'deny':
                event.update(decision='denied',error='policy_denied')
                return ToolResult(success=False,error='policy_denied',metadata={'permission_denied':True})
            if self.closed or server not in self.clients:
                event['error'] = 'unavailable'
                return ToolResult(success=False,error='MCP tool is unavailable; restart gateway if disconnected')
            # Freeze the exact schema-validated payload BEFORE yielding to a provider.
            try:
                payload = json.dumps(arguments,allow_nan=False)
                snapshot = json.loads(payload)
                valid = isinstance(snapshot,dict) and self._adapters[server,name].validator.is_valid(snapshot)
            except (ValueError,TypeError,KeyError,RecursionError):
                valid = False
            if not valid:
                event['error'] = 'invalid_arguments'
                return ToolResult(success=False,error='Invalid MCP arguments')
            if policy == 'confirm':
                approved,reason = await authorize(self.approval_provider,server,name,snapshot)
                event['decision'] = 'approved' if approved else 'denied'
                if not approved:
                    event['error'] = reason
                    return ToolResult(success=False,error=reason,metadata={'permission_denied':True})
            else:
                event['decision'] = 'allowed'
            event['executed'] = True
            try:
                result = await self.clients[server].call_tool(name,json.loads(payload),read_timeout_seconds=self.servers[server].get('timeout_seconds',10))
                result = MCPToolAdapter.result(result)
                event.update(success=result.success,error=None if result.success else 'remote_result_rejected')
                return result
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                kind = failure_kind(exc)
                event['error'] = kind
                # SDK context teardown stays in the owner task, never wait_for.
                self.closed = True
                try:
                    await self.stack.aclose()
                finally:
                    self.clients.clear()
                return ToolResult(success=False,error=f'MCP call failed ({kind}); MCP connections closed, restart gateway',metadata={'mcp_failure':kind})
        except asyncio.CancelledError:
            event['error'] = 'cancelled'
            raise
        finally:
            event['duration_seconds'] = round(time.perf_counter()-started,6)
            self._audit.append(event)

    async def __aexit__(self,*exc):
        if asyncio.current_task() is not self.owner:
            raise RuntimeError('MCP contexts must close in their owning gateway task')
        try:
            if self.stack is not None:await self.stack.aclose()
        finally:
            self.closed = True
            self.clients.clear()
