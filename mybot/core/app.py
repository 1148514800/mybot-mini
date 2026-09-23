from __future__ import annotations

from ..agent import AgentLoop, ContextBuilder
from ..mcp import MCPClientManager
from ..session import SessionManager
from ..tools import build_default_tool_registry
from ..tracing import AgentTracer
from ..workspace import init_instructions, init_workspace
from .config import GatewayConfig, build_client


async def run_gateway(config: GatewayConfig | None = None) -> None:
    config = config or GatewayConfig()
    init_instructions(config.workspace / "instructions")
    init_workspace(config.workspace)

    tools = build_default_tool_registry(config.workspace)
    mcp_manager = MCPClientManager(config.mcp, tools)
    try:
        await mcp_manager.start()
    except BaseException:
        await mcp_manager.close()
        raise

    llm_client = None

    try:
        context = ContextBuilder(config.workspace)
        sessions = SessionManager(config.workspace)
        tracer = AgentTracer(trace_dir=config.trace_dir)
        llm_client = build_client(config)
        agent = AgentLoop(
            client=llm_client,
            config=config,
            tools=tools,
            context=context,
            sessions=sessions,
            tracer=tracer,
        )

        for status in mcp_manager.statuses:
            if status.enabled and status.error:
                print(
                    f"Optional MCP server '{status.name}' failed "
                    f"({status.transport}): {status.error}"
                )

        print("Gateway started. Channel: cli\n")
        print(f"Internal process trace: {config.show_internal_process}\n")

        await agent.run()
    finally:
        if llm_client is not None:
            await llm_client.close()
        await mcp_manager.close()
        print("Gateway stopped.")
