"""Application entry point: wire config, tools, agent, and the CLI loop."""
from __future__ import annotations

from .agent import AgentLoop, ContextBuilder
from .config import GatewayConfig, build_client
from .tools import build_default_tool_registry
from .workspace import init_workspace
from .mcp_client.manager import MCPClientManager
from .mcp_client.approval import cli_approval
from .tools.command_approval import cli_command_approval
from .tools.undo_approval import cli_undo_approval


async def run_gateway(config: GatewayConfig | None = None) -> None:
    config = config or GatewayConfig()
    if config.coding_enabled:
        if not config.workspace.is_dir():raise ValueError('Coding workspace must already exist')
    else:
        init_workspace(config.workspace)

    tools = build_default_tool_registry(config.workspace, coding_enabled=config.coding_enabled, patch_mode=config.coding_patch_mode,
        command=config.coding_command, command_approval_provider=cli_command_approval)
    llm_client = None
    try:
        async with MCPClientManager(config, tools, approval_provider=cli_approval):
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
    finally:
        if llm_client is not None:
            await llm_client.close()
        print("Gateway stopped.")
