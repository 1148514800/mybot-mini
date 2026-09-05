from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from ..agent import AgentLoop, ContextBuilder
from ..messaging import CLIChannel, FeishuChannel, BaseChannel, MessageBus, route_outbound
from ..mcp import MCPClientManager
from ..storage.memory import MemoryManager
from ..storage.session import SessionManager
from ..storage.checkpoint import ActiveTaskCheckpointStore
from ..tools import build_default_tool_registry
from ..tracing import AgentTracer
from ..workspace import init_instructions, init_workspace
from .config import GatewayConfig, build_client


async def run_gateway(config: GatewayConfig | None = None) -> None:
    config = config or GatewayConfig()
    init_instructions(config.workspace / "instructions")
    init_workspace(config.workspace)

    bus = MessageBus()
    memory = MemoryManager(config.workspace)
    tools = build_default_tool_registry(
        config.workspace,
        memory_manager=memory,
    )
    mcp_manager = MCPClientManager(config.mcp, tools)
    try:
        await mcp_manager.start()
    except BaseException:
        await mcp_manager.close()
        raise

    channels: dict[str, BaseChannel] = {}
    tasks: list[asyncio.Task] = []
    llm_client: AsyncOpenAI | None = None

    try:
        context = ContextBuilder(
            config.workspace,
            memory_manager=memory,
        )
        sessions = SessionManager(config.workspace)
        tracer = AgentTracer(trace_dir=config.trace_dir)
        checkpoints = ActiveTaskCheckpointStore(
            config.workspace,
            enabled=config.checkpoint_enabled,
            recent_task_ttl_seconds=(
                config.checkpoint_recent_task_ttl_seconds
            ),
        )
        if checkpoints.enabled and not checkpoints.available:
            print(
                "Active task checkpoint storage disabled after initialization "
                f"failure: {checkpoints.last_error}"
            )
        llm_client = build_client(config)
        agent = AgentLoop(
            client=llm_client,
            config=config,
            bus=bus,
            tools=tools,
            context=context,
            sessions=sessions,
            tracer=tracer,
            checkpoint_store=checkpoints,
        )

        channels["cli"] = CLIChannel(bus)
        if config.feishu.enabled and config.feishu.app_id and config.feishu.app_secret:
            channels["feishu"] = FeishuChannel(
                bus,
                app_id=config.feishu.app_id,
                app_secret=config.feishu.app_secret,
            )
        else:
            print("Feishu channel disabled. Set feishu config to enable it.")

        for status in mcp_manager.statuses:
            if status.enabled and status.error:
                print(
                    f"Optional MCP server '{status.name}' failed "
                    f"({status.transport}): {status.error}"
                )

        print(f"Gateway started. Channels: {list(channels.keys())}\n")
        print(f"Internal process trace: {config.show_internal_process}\n")

        tasks = [
            asyncio.create_task(agent.run(), name="agent"),
            asyncio.create_task(
                route_outbound(bus, channels),
                name="outbound-router",
            ),
            *[
                asyncio.create_task(channel.start(), name=f"channel:{name}")
                for name, channel in channels.items()
            ],
        ]
        done, _ = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        # Surface an unexpected service failure instead of silently stopping.
        for task in done:
            task.result()
    finally:
        try:
            for channel in channels.values():
                await channel.stop()

            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            if llm_client is not None:
                await llm_client.close()
            await mcp_manager.close()
            print("Gateway stopped.")
