from __future__ import annotations

import asyncio
import json
from datetime import datetime

from openai import OpenAI

from ..core.config import GatewayConfig
from ..messaging import MessageBus, OutboundMessage
from ..storage.session import SessionManager
from ..tools import ToolRegistry, ToolResult
from ..tools.browser.connection import LOCAL_BROWSER_SESSION
from ..tools.browser.navigation import MANAGED_BROWSER_SESSION
from ..tracing import AgentRunTrace, AgentTracer
from .context import (
    BROWSER_MODE_LOCAL,
    BROWSER_MODE_MANAGED,
    ContextBuilder,
)


MAX_REACT_STEPS_HARD_LIMIT = 30
MAX_RATE_LIMIT_RETRIES_HARD_LIMIT = 10
MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS = 2
MAX_EMPTY_MODEL_RESPONSES = 2

_BROWSER_SESSION_BY_MODE = {
    BROWSER_MODE_LOCAL: LOCAL_BROWSER_SESSION,
    BROWSER_MODE_MANAGED: MANAGED_BROWSER_SESSION,
}


class AgentLoop:
    def __init__(
        self,
        client: OpenAI,
        config: GatewayConfig,
        bus: MessageBus,
        tools: ToolRegistry,
        context: ContextBuilder,
        sessions: SessionManager,
        tracer: AgentTracer | None = None,
    ):
        self.client = client
        self.config = config
        self.bus = bus
        self.tools = tools
        self.context = context
        self.sessions = sessions
        self.tracer = tracer or AgentTracer()

    def _trace(self, message: str) -> None:
        if self.config.show_internal_process:
            print(f"[trace] {message}")

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}"
        return (
            "RateLimitError" in text
            or "429" in text
            or "TPM limit reached" in text
        )

    def _effective_react_steps(self) -> int:
        return max(
            1,
            min(self.config.max_react_steps, MAX_REACT_STEPS_HARD_LIMIT),
        )

    def _effective_rate_limit_retries(self) -> int:
        return max(
            0,
            min(
                self.config.rate_limit_retries,
                MAX_RATE_LIMIT_RETRIES_HARD_LIMIT,
            ),
        )

    def _tool_call_signature(self, tool_call) -> str:
        name = tool_call.function.name
        raw_arguments = tool_call.function.arguments or "{}"
        try:
            arguments = json.loads(raw_arguments)
            normalized = json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, json.JSONDecodeError):
            normalized = str(raw_arguments)
        return f"{name}:{normalized}"

    def _tool_arguments_for_trace(
        self,
        tool_call,
        browser_mode: str,
    ) -> dict:
        raw_arguments = tool_call.function.arguments or "{}"
        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, json.JSONDecodeError):
            return {"arguments_parse_error": True}
        if not isinstance(arguments, dict):
            return {"arguments_type": type(arguments).__name__}
        if tool_call.function.name.startswith("browser_") and (
            tool_call.function.name not in {"browser_attach", "browser_open"}
        ):
            arguments = dict(arguments)
            arguments["session"] = _BROWSER_SESSION_BY_MODE[browser_mode]
        return arguments

    def _usage_value(self, usage, name: str) -> int | None:
        if usage is None:
            return None
        value = usage.get(name) if isinstance(usage, dict) else getattr(
            usage,
            name,
            None,
        )
        return value if isinstance(value, int) else None

    def _tracing_active(self) -> bool:
        run = self.tracer.get_current_run()
        return run is not None and run.status == "running"

    def _tool_definitions_for_browser_mode(
        self,
        browser_mode: str,
    ) -> list[dict]:
        blocked_tool = (
            "browser_open"
            if browser_mode == BROWSER_MODE_LOCAL
            else "browser_attach"
        )
        return [
            definition
            for definition in self.tools.get_definitions()
            if definition.get("function", {}).get("name") != blocked_tool
        ]

    async def _execute_tool_call(
        self,
        tool_call,
        browser_mode: str = BROWSER_MODE_MANAGED,
    ) -> ToolResult:
        """Decode and execute one model tool call without breaking the loop."""
        name = tool_call.function.name
        if browser_mode == BROWSER_MODE_LOCAL and name == "browser_open":
            return ToolResult(
                success=False,
                error=(
                    "browser_open is blocked because the user explicitly "
                    "requested the local browser. Use browser_attach."
                ),
            )
        if browser_mode == BROWSER_MODE_MANAGED and name == "browser_attach":
            return ToolResult(
                success=False,
                error=(
                    "browser_attach is blocked because managed_browser is the "
                    "default for this request. Use browser_open."
                ),
            )

        raw_arguments = tool_call.function.arguments or "{}"
        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            return ToolResult(
                success=False,
                error=f"Invalid arguments for tool '{name}': {exc}",
            )

        if not isinstance(arguments, dict):
            return ToolResult(
                success=False,
                error=f"Arguments for tool '{name}' must be a JSON object.",
            )

        if name.startswith("browser_") and name not in {
            "browser_attach",
            "browser_open",
        }:
            arguments = dict(arguments)
            arguments["session"] = _BROWSER_SESSION_BY_MODE[browser_mode]

        self._trace(
            f"tool call name={name} args="
            f"{json.dumps(arguments, ensure_ascii=False)}"
        )
        result = await self.tools.execute(name, arguments)
        preview = result.to_text()[:300].replace("\n", " ")
        self._trace(f"tool result name={name} result={preview}")
        return result

    async def run(self):
        while True:
            try:
                message = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            session = self.sessions.get_or_create(message.session_key)
            history = session.build_prompt_history(max_recent_messages=12)
            messages = self.context.build_messages(history, message.content)
            browser_mode = self.context.resolve_browser_mode(message.content)
            reply, run_trace = await self.run_traced(
                message.content,
                messages,
                browser_mode,
            )
            self._trace(run_trace.summary_text().replace("\n", " | "))

            session.messages.append(
                {
                    "role": "user",
                    "content": message.content,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            session.messages.append(
                {
                    "role": "assistant",
                    "content": reply,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            self.sessions.save(session)

            await self.bus.publish_outbound(
                OutboundMessage(channel=message.channel, chat_id=message.chat_id, content=reply)
            )

    async def run_traced(
        self,
        user_input: str,
        messages: list[dict],
        browser_mode: str = BROWSER_MODE_MANAGED,
    ) -> tuple[str, AgentRunTrace]:
        """Run the existing ReAct loop and return its completed in-memory trace."""
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": browser_mode,
                "model": self.config.model,
                "provider": getattr(self.config, "provider", ""),
            },
        )
        try:
            output, status, error = await self._react_loop_outcome(
                messages,
                browser_mode,
            )
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.tracer.finish_run(status="failed", error=error)
            raise
        trace = self.tracer.finish_run(
            final_output=output,
            status=status,
            error=error,
        )
        return output, trace

    async def _react_loop(
        self,
        messages: list[dict],
        browser_mode: str = BROWSER_MODE_MANAGED,
    ) -> str:
        output, _, _ = await self._react_loop_outcome(messages, browser_mode)
        return output

    async def _react_loop_outcome(
        self,
        messages: list[dict],
        browser_mode: str = BROWSER_MODE_MANAGED,
    ) -> tuple[str, str, str | None]:
        final_parts: list[str] = []
        rate_limit_retries = 0
        rate_limit_retry_limit = self._effective_rate_limit_retries()
        react_step_limit = self._effective_react_steps()
        empty_response_count = 0
        last_tool_signature = ""
        identical_tool_call_count = 0
        tool_definitions = self._tool_definitions_for_browser_mode(browser_mode)
        for step in range(react_step_limit):
            self._trace(f"model step={step + 1}")
            step_trace = (
                self.tracer.start_step(step + 1)
                if self._tracing_active()
                else None
            )
            llm_trace = (
                self.tracer.start_llm_call(
                    step_id=step_trace.step_id,
                    model=self.config.model,
                    provider=getattr(self.config, "provider", ""),
                    message_count=len(messages),
                    retry_count=rate_limit_retries,
                )
                if step_trace
                else None
            )
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    tools=tool_definitions or None,
                    temperature=0.1,
                    max_tokens=self.config.max_completion_tokens,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if llm_trace:
                    self.tracer.finish_llm_call(llm_trace, error=error)
                if step_trace:
                    self.tracer.finish_step(status="failed", error=error)
                if (
                    self._is_rate_limit_error(exc)
                    and rate_limit_retries < rate_limit_retry_limit
                ):
                    rate_limit_retries += 1
                    self._trace(
                        "rate limited, waiting 60s before retry "
                        f"{rate_limit_retries}/{rate_limit_retry_limit}"
                    )
                    await asyncio.sleep(60)
                    continue
                return f"调用模型时出错: {error}", "failed", error

            choice = response.choices[0]
            message = choice.message
            finish_reason = choice.finish_reason
            content = (message.content or "").strip()
            if llm_trace:
                usage = getattr(response, "usage", None)
                self.tracer.finish_llm_call(
                    llm_trace,
                    finish_reason=finish_reason,
                    input_tokens=self._usage_value(usage, "prompt_tokens"),
                    output_tokens=self._usage_value(
                        usage,
                        "completion_tokens",
                    ),
                    total_tokens=self._usage_value(usage, "total_tokens"),
                )

            if finish_reason == "length" and content:
                final_parts.append(content)
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Continue from exactly where you stopped. Do not repeat prior text.",
                    }
                )
                if step_trace:
                    self.tracer.finish_step()
                continue

            if not message.tool_calls:
                if content:
                    final_parts.append(content)
                    if step_trace:
                        self.tracer.finish_step()
                    return "".join(final_parts).strip(), "success", None

                empty_response_count += 1
                if empty_response_count < MAX_EMPTY_MODEL_RESPONSES:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "上一轮没有返回文本或工具调用。请根据最近一次工具结果继续完成用户任务；"
                                "如果无法继续，请明确说明原因。"
                            ),
                        }
                    )
                    if step_trace:
                        self.tracer.finish_step(status="empty_response")
                    continue

                output = (
                    "".join(final_parts).strip()
                    or "模型连续返回空响应。模型结束了本轮处理，但没有返回文本结果。"
                )
                error = "model returned consecutive empty responses"
                if step_trace:
                    self.tracer.finish_step(status="failed", error=error)
                return output, "failed", error

            empty_response_count = 0
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in message.tool_calls
                    ],
                }
            )

            for tool_call in message.tool_calls:
                tool_trace = (
                    self.tracer.start_tool_call(
                        step_id=step_trace.step_id,
                        tool_name=tool_call.function.name,
                        arguments=self._tool_arguments_for_trace(
                            tool_call,
                            browser_mode,
                        ),
                        metadata={"model_tool_call_id": tool_call.id},
                    )
                    if step_trace
                    else None
                )
                signature = self._tool_call_signature(tool_call)
                if signature == last_tool_signature:
                    identical_tool_call_count += 1
                else:
                    last_tool_signature = signature
                    identical_tool_call_count = 1

                if (
                    identical_tool_call_count
                    > MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS
                ):
                    result = ToolResult(
                        success=False,
                        error=(
                            "Repeated identical tool call blocked. Inspect the "
                            "latest result, choose a different action, or finish "
                            "the task."
                        ),
                    )
                    self._trace(
                        f"blocked repeated tool call signature={signature[:200]}"
                    )
                else:
                    try:
                        result = await self._execute_tool_call(
                            tool_call,
                            browser_mode,
                        )
                    except Exception as exc:
                        if tool_trace:
                            self.tracer.finish_tool_call(
                                tool_trace,
                                error=f"{type(exc).__name__}: {exc}",
                            )
                        raise
                if tool_trace:
                    self.tracer.finish_tool_call(tool_trace, result=result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.to_text(),
                    }
                )

            if step_trace:
                self.tracer.finish_step()

        return (
            f"已达到单次任务的 {react_step_limit} 步执行上限，任务尚未正常结束。",
            "max_steps",
            None,
        )
