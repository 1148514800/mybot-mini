from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from openai import APITimeoutError, AsyncOpenAI

from ..config import GatewayConfig
from ..tools import ToolRegistry, ToolResult
from .context import ContextBuilder
from .session import Session
from .planning import Plan, PlanningTool


class AgentLoop:
    """Run a simple tool-calling loop for one CLI conversation."""

    def __init__(self, client: AsyncOpenAI, config: GatewayConfig, tools: ToolRegistry,
                 context: ContextBuilder, session: Session | None = None):
        self.client = client
        self.config = config
        self.tools = tools
        self.context = context
        self.session = session if session is not None else Session(config.session_max_turns)
        self.plan = Plan()
        for name in ("create_plan", "update_plan"):
            self.tools.register(PlanningTool(self.plan, name))

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
        self.plan.reset(user_input)
        try:
            return await self._handle_message(user_input)
        except BaseException:
            report = self.plan.close("任务异常或中断")
            if report:
                print(report)
            raise

    async def _handle_message(self, user_input: str) -> str:
        if user_input.strip() == "/clear":
            self.session.clear()
            self.plan.reset()
            return "当前会话已清空。"
        messages = self.context.build_messages(user_input, self.session.history())
        turn_start = len(messages) - 1
        limit = max(1, min(self.config.max_react_steps, 30))
        debug = self.config.debug
        for step in range(1, limit + 1):
            start = time.perf_counter()
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
                report = self.plan.close("模型请求超时")
                return f"模型请求超时（{self.config.request_timeout_seconds:g} 秒）。" + (f"\n{report}" if report else "")

            message = response.choices[0].message
            if debug:
                print(
                    f"[LLM {step}] time={time.perf_counter() - start:.2f}s "
                    f"tokens={response.usage.total_tokens if response.usage else '?'} "
                    f"tool_calls={len(message.tool_calls or [])}"
                )
            if not message.tool_calls:
                reply = (message.content or "").strip() or "模型没有返回文本。"
                return self._finish_turn(messages, turn_start, reply)

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
                if debug:
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = "<invalid JSON>"
                    if isinstance(args, dict) and "content" in args:
                        args["content"] = f"<{len(str(args['content']))} chars>"
                    print(f"[CALL] {call.function.name}: {args}")
                result = await self._execute(call.function.name, call.function.arguments)
                if debug:
                    print(
                        f"[RESULT] success={result.success} "
                        f"chars={len(result.output)} error={result.error}"
                    )
                messages.append({
                    "role": "tool", "tool_call_id": call.id, "content": result.to_text(),
                })

        return self._finish_turn(messages, turn_start, f"已达到单次任务的 {limit} 步上限。", "达到 ReAct 上限")

    def _finish_turn(self, messages: list[dict[str, Any]], turn_start: int, reply: str,
                     reason: str = "") -> str:
        report = self.plan.close(reason)
        if report:
            reply = f"{reply}\n{report}" if reason else report
        messages.append({"role": "assistant", "content": reply})
        self.session.add_turn(messages[turn_start:])
        return reply

    async def _execute(self, name: str, raw_arguments: Any) -> ToolResult:
        if name in ("create_plan", "update_plan"):
            return await self._execute_tool(name, raw_arguments)
        error = self.plan.execution_error()
        if error:
            return ToolResult(success=False, error=error)
        result = await self._execute_tool(name, raw_arguments)
        self.plan.observe(name, result)
        return result

    async def _execute_tool(self, name: str, raw_arguments: Any) -> ToolResult:
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
