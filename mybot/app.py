"""Application entry point: wire config, tools, agent, and the CLI loop."""
from __future__ import annotations

from .agent import AgentLoop, ContextBuilder
from .config import GatewayConfig, load_config
from .provider_failover import build_gateway_client as build_client
from .tools.registry import build_configured_tool_registry
from .workspace import init_workspace
from .mcp_client.approval import cli_approval
from .tools.command_approval import cli_command_approval
from .tools.undo_approval import cli_undo_approval


async def run_gateway(config: GatewayConfig | None = None) -> None:
    config = config or load_config()
    if config.coding_enabled:
        if not config.workspace.is_dir():raise ValueError('Coding workspace must already exist')
    from .workspace_lease import WorkspaceLease
    lease = WorkspaceLease(config.workspace).acquire()
    cleanup_ok = False
    llm_client = None
    agent = None
    try:
        if not config.coding_enabled:
            init_workspace(config.workspace)
        tools = build_configured_tool_registry(config,
            command_approval_provider=cli_command_approval)
        from contextlib import AsyncExitStack
        async with AsyncExitStack() as stack:
            if config.mcp_enabled:
                from .mcp_client.manager import MCPClientManager
                await stack.enter_async_context(MCPClientManager(config, tools, approval_provider=cli_approval))
            llm_client = build_client(config)
            agent = AgentLoop(
                client=llm_client,
                config=config,
                tools=tools,
                context=ContextBuilder(config.workspace),
                undo_approval_provider=cli_undo_approval,
            )

            print("Gateway started. Channel: cli\n")
            await agent.run()
        cleanup_ok = True
    finally:
        manager_ok, cleanup_ok = cleanup_ok, False
        try:
            if getattr(agent, '_git_capsule', None) is not None:
                agent._git_capsule.close()
            if llm_client is not None:
                await llm_client.close()
            report = getattr(agent, 'last_coding_report', None)
            history=getattr(agent,'history',None)
            cleanup_ok = manager_ok and (not report or report['state'] != 'execution_uncertain') and (history is None or history.turn_id is None and not history.store.workspace_uncertain())
            close_history=getattr(agent,'close_history',None)
            if close_history is not None:close_history()
        finally:
            lease.release(confirmed=cleanup_ok)
        print("Gateway stopped.")
