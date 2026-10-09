from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import APITimeoutError, AsyncOpenAI

from ..config import GatewayConfig
from ..tools import ToolRegistry, ToolResult
from .context import ContextBuilder


class AgentLoop:
    """Run a simple tool-calling loop for one CLI conversation."""

    def __init__(self, client: AsyncOpenAI, config: GatewayConfig, tools: ToolRegistry,
                 context: ContextBuilder):
        self.client = client
        self.config = config
        self.tools = tools
        self.context = context

    async def run(self) -> None:
        while True:
            try:
                user_input = (await asyncio.to_thread(input, "You: ")).strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                return
            try:
                reply = await self.handle_message(user_input)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                print(f"\nBot: 运行时错误: {type(exc).__name__}: {exc}\n")
                continue
            print(f"\nBot: {reply}\n")

    async def handle_message(self, user_input: str) -> str:
        messages = self.context.build_messages(user_input)
        limit = max(1, min(self.config.max_react_steps, 30))
        for _ in range(limit):
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.config.model,
                        messages=messages,
                        tools=self.tools.get_definitions() or None,
                        temperature=0.1,
                        max_tokens=self.config.max_completion_tokens,
                    ),
                    timeout=max(1.0, self.config.request_timeout_seconds),
                )
            except (TimeoutError, APITimeoutError):
                return f"模型请求超时（{self.config.request_timeout_seconds:g} 秒）。"

            message = response.choices[0].message
            if not message.tool_calls:
                return (message.content or "").strip() or "模型没有返回文本。"

            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {"id": call.id, "type": "function", "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    }}
                    for call in message.tool_calls
                ],
            })
            for call in message.tool_calls:
                result = await self._execute(call.function.name, call.function.arguments)
                messages.append({
                    "role": "tool", "tool_call_id": call.id, "content": result.to_text(),
                })

        return f"已达到单次任务的 {limit} 步上限。"

    async def _execute(self, name: str, raw_arguments: Any) -> ToolResult:
        try:
            arguments = json.loads(raw_arguments or "{}") if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError as exc:
            return ToolResult(success=False, error=f"invalid JSON arguments: {exc}")
        if not isinstance(arguments, dict):
            return ToolResult(success=False, error="arguments must be a JSON object")
        if not self.tools.has_tool(name):
            return ToolResult(success=False, error=f"unknown tool '{name}'")
        schema = self.tools.get_parameters(name)
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in arguments:
                return ToolResult(success=False, error=f"missing required field '{required}'")
        for key, value in arguments.items():
            rule = properties.get(key, {})
            expected = rule.get("type")
            if expected == "string" and not isinstance(value, str):
                return ToolResult(success=False, error=f"field '{key}' must be a string")
        return await self.tools.execute(name, arguments)
