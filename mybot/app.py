"""Application entry point: wire config, tools, agent, and the CLI loop."""
from __future__ import annotations

from .agent import AgentLoop, ContextBuilder
from .config import GatewayConfig, build_client
from .mcp import MCPManager
from .tools import build_default_tool_registry
from .tracing import AgentTracer
from .workspace import init_workspace


async def run_gateway(config: GatewayConfig | None = None) -> None:
    config = config or GatewayConfig()
    init_workspace(config.workspace)

    tools = build_default_tool_registry(config.workspace)
    mcp = MCPManager(config.mcp, tools)
    await mcp.start()

    llm_client = None
    try:
        llm_client = build_client(config)
        agent = AgentLoop(
            client=llm_client,
            config=config,
            tools=tools,
            context=ContextBuilder(config.workspace),
            tracer=AgentTracer(trace_dir=config.trace_dir),
        )

        for status in mcp.statuses:
            if status.enabled and status.error:
                print(f"Optional MCP server '{status.name}' failed: {status.error}")

        print("Gateway started. Channel: cli\n")
        await agent.run()
    finally:
        if llm_client is not None:
            await llm_client.close()
        await mcp.close()
        print("Gateway stopped.")
