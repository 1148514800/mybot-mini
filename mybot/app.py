"""Application entry point: wire config, tools, agent, and the CLI loop."""
from __future__ import annotations

from .agent import AgentLoop, ContextBuilder
from .config import GatewayConfig, build_client
from .tools import build_default_tool_registry
from .workspace import init_workspace


async def run_gateway(config: GatewayConfig | None = None) -> None:
    config = config or GatewayConfig()
    init_workspace(config.workspace)

    tools = build_default_tool_registry(config.workspace)
    llm_client = None
    try:
        llm_client = build_client(config)
        agent = AgentLoop(
            client=llm_client,
            config=config,
            tools=tools,
            context=ContextBuilder(config.workspace),
        )

        print("Gateway started. Channel: cli\n")
        await agent.run()
    finally:
        if llm_client is not None:
            await llm_client.close()
        print("Gateway stopped.")
