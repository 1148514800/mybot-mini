from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from openai import APITimeoutError, AsyncOpenAI

from ..config import GatewayConfig
from ..tools import ToolRegistry, ToolResult
from ..storage.session_store import SessionStore
from .context import ContextBuilder
from .session import Session
from .planning import Plan, PlanningTool
from .context_manager import ContextManager, ContextBudgetError


class AgentLoop:
    """Run a simple tool-calling loop for one CLI conversation."""

    def __init__(self, client: AsyncOpenAI, config: GatewayConfig, tools: ToolRegistry,
                 context: ContextBuilder, session: Session | None = None):
        self.client = client
        self.config = config
        self.tools = tools
        self.context = context
        self.context_manager = ContextManager(config)
        self.session = session if session is not None else Session(config.session_max_turns)
        self.store = SessionStore(config.session_path, config.workspace) if config.session_persist else None
        if self.store is not None:
            self.session.restore(self.store.load())
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
        self.context_clipped = False
        self.context_history_omitted = False
        try:
            reply = await self._handle_message(user_input)
            if self.context_clipped:
                reply = "[CONTEXT] 本轮部分工具结果仅提供节选，未验证全文阅读或分析。以下模型回复不能视为完整任务结论：\n" + reply
            if self.context_history_omitted:
                reply = "[CONTEXT] 部分历史已省略，预算不足以提供其摘要。\n" + reply
            return reply
        except BaseException as exc:
            report = self.plan.close("上下文预算不足" if isinstance(exc, ContextBudgetError) else "任务异常或中断")
            if report:
                print(report)
            raise

    async def _handle_message(self, user_input: str) -> str:
        if user_input.strip() == "/clear":
            if self.store is not None:
                self.store.clear()
            self.session.clear()
            self.plan.reset()
            return "当前会话已清空。"
        messages = self.context.build_messages(user_input, self.session.history())
        turns = self.session.export_turns()
        turn_start = len(messages) - 1
        limit = max(1, min(self.config.max_react_steps, 30))
        debug = self.config.debug
        for step in range(1, limit + 1):
            definitions = self.tools.get_definitions() or None
            llm_messages, stats = self.context_manager.prepare(messages, definitions, turns, self.plan)
            self.context_clipped = self.context_clipped or stats["current_clipped"]
            self.context_history_omitted = self.context_history_omitted or stats.get("history_omitted", False)
            if debug and self.config.context_enabled:
                print(f"[CONTEXT] chars={stats['before']}->{stats['after']} max={self.config.context_max_chars}")
            start = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.config.model,
                        messages=llm_messages,
                        tools=definitions,
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
        if self.store is not None:
            turns = self.session.export_turns() + [messages[turn_start:]]
            self.store.save(turns[-self.session.max_turns:])
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
