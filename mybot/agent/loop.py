from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from ..core.config import GatewayConfig
from ..tools import ToolRegistry, ToolResult
from ..tracing import (
    AgentRunTrace,
    AgentTracer,
    redact_text,
)
from .model_execution import ModelExecutor
from .tool_calls import tool_call_signature
from .tool_execution import (
    ToolExecutionContext,
    ToolExecutionPipeline,
    ToolExecutionRequest,
)
from .context import (
    BROWSER_MODE_LOCAL,
    BROWSER_MODE_MANAGED,
    ContextBuilder,
)


MAX_REACT_STEPS_HARD_LIMIT = 30
MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS = 2
MAX_EMPTY_MODEL_RESPONSES = 2


class AgentLoop:
    def __init__(
        self,
        client: AsyncOpenAI,
        config: GatewayConfig,
        tools: ToolRegistry,
        context: ContextBuilder,
        tracer: AgentTracer | None = None,
    ):
        self.client = client
        self.config = config
        self.tools = tools
        self.context = context
        self.tracer = tracer or AgentTracer()
        self.tool_execution = ToolExecutionPipeline(
            self.tools,
            self.tracer,
            debug_trace=self._trace,
        )
        if hasattr(self.context, "max_context_chars"):
            self.context.max_context_chars = getattr(config, "max_context_chars", self.context.max_context_chars)
            self.context.max_tool_result_chars = getattr(config, "max_tool_result_chars", self.context.max_tool_result_chars)
        self.model_execution = ModelExecutor(
            client=self.client,
            config=self.config,
            context=self.context,
            tracer=self.tracer,
        )

    def _pipeline(self) -> ToolExecutionPipeline:
        """Keep injected test/runtime dependencies aligned with the pipeline."""
        self.tool_execution.tools = self.tools
        self.tool_execution.tracer = self.tracer
        return self.tool_execution

    def _trace(self, message: str) -> None:
        if self.config.show_internal_process:
            print(f"[trace] {redact_text(message)}")

    def _model_tool_result_text(self, result: ToolResult) -> str:
        return result.to_text()

    def _effective_react_steps(self) -> int:
        return max(
            1,
            min(self.config.max_react_steps, MAX_REACT_STEPS_HARD_LIMIT),
        )

    def _effective_rate_limit_retries(self) -> int:
        """Compatibility access for callers that inspect configured limits."""
        return self.model_execution._effective_rate_limit_retries()

    def _execution_context(
        self,
        *,
        session_key: str = "",
        task_id: str | None = None,
        browser_mode: str,
        browser_snapshot: str,
        browser_initialized: bool,
    ) -> ToolExecutionContext:
        return ToolExecutionContext(
            session_key=session_key,
            task_id=task_id,
            browser_mode=browser_mode,
            browser_snapshot=browser_snapshot,
            browser_initialized=browser_initialized,
        )

    async def _execute_tool_batch(
        self,
        tool_calls: list,
        *,
        messages: list[dict],
        execution_context: ToolExecutionContext,
        session_key: str,
        task_id: str | None,
        step_id: str | None,
        repeat_tracker: dict[str, object] | None = None,
    ) -> None:
        """Execute a model tool batch through the shared execution pipeline."""
        for tool_call in tool_calls:
            execution_guard = None
            if repeat_tracker is not None:
                signature = tool_call_signature(tool_call)
                if signature == repeat_tracker.get("last_signature"):
                    count = int(repeat_tracker.get("count", 0)) + 1
                else:
                    repeat_tracker["last_signature"] = signature
                    count = 1
                repeat_tracker["count"] = count
                if count > MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS:
                    execution_guard = ToolResult(
                        success=False,
                        error=(
                            "Repeated identical tool call blocked. Inspect the "
                            "latest result, choose a different action, or finish "
                            "the task."
                        ),
                    )
                    self._trace(
                        "blocked repeated tool call "
                        f"name={tool_call.function.name}"
                    )

            request = ToolExecutionRequest(
                tool_name=tool_call.function.name,
                arguments=tool_call.function.arguments or "{}",
                session_key=session_key,
                task_id=task_id,
                model_tool_call_id=tool_call.id,
                step_id=step_id,
                messages=messages,
                execution_guard=execution_guard,
            )
            outcome = await self._pipeline().execute(
                request,
                execution_context,
            )
            result = outcome.tool_result

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": self._model_tool_result_text(result),
                }
            )

    def _tracing_active(self) -> bool:
        run = self.tracer.get_current_run()
        return run is not None and run.status == "running"

    def _tool_definitions_for_browser_mode(
        self,
        browser_mode: str,
        browser_initialized: bool = False,
    ) -> list[dict]:
        blocked_tool = (
            "browser_open"
            if browser_mode == BROWSER_MODE_LOCAL
            else "browser_attach"
        )
        blocked_tools = {blocked_tool}
        if browser_initialized:
            blocked_tools.add(
                "browser_attach"
                if browser_mode == BROWSER_MODE_LOCAL
                else "browser_open"
            )
        return [
            definition
            for definition in self.tools.get_definitions()
            if definition.get("function", {}).get("name") not in blocked_tools
        ]

    async def run(self):
        """Run the local CLI conversation until the user exits."""
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
                reply, trace = await self.handle_inbound_message(user_input)
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                print(
                    f"\nBot: 运行时错误: {type(exc).__name__}: {exc}\n"
                )
                continue
            self._trace(trace.summary_text().replace("\n", " | "))
            print(f"\nBot: {reply}\n")

    async def handle_inbound_message(
        self,
        user_input: str,
        *,
        session_key: str = "cli:direct",
    ) -> tuple[str, AgentRunTrace]:
        """Handle one user message from the CLI."""
        messages = self.context.build_messages(user_input)
        browser_mode = self.context.resolve_browser_mode(user_input)
        return await self.run_traced(
            user_input,
            messages,
            browser_mode,
            session_key=session_key,
        )

    async def run_traced(
        self,
        user_input: str,
        messages: list[dict],
        browser_mode: str = BROWSER_MODE_MANAGED,
        *,
        session_key: str = "",
        metadata: dict | None = None,
    ) -> tuple[str, AgentRunTrace]:
        """Run the ReAct loop and return its completed in-memory trace."""
        run_metadata = {
            "browser_mode": browser_mode,
            "model": self.config.model,
            "provider": getattr(self.config, "provider", ""),
        }
        run_metadata.update(metadata or {})
        self.tracer.start_run(user_input, metadata=run_metadata)
        try:
            output, status, error = await self._react_loop_outcome(
                messages,
                browser_mode,
                user_input=user_input,
                session_key=session_key,
            )
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.tracer.finish_run(
                status="failed",
                error=error,
            )
            raise
        trace = self.tracer.finish_run(
            final_output=output,
            status=status,
            error=error,
        )
        return output, trace

    async def _react_loop_outcome(
        self,
        messages: list[dict],
        browser_mode: str = BROWSER_MODE_MANAGED,
        *,
        user_input: str = "",
        session_key: str = "",
        browser_initialized: bool = False,
    ) -> tuple[str, str, str | None]:
        final_parts: list[str] = []
        react_step_limit = self._effective_react_steps()
        empty_response_count = 0
        repeat_tracker: dict[str, object] = {
            "last_signature": "",
            "count": 0,
        }
        for step in range(react_step_limit):
            step_index = step + 1
            self._trace(f"model step={step_index}")
            tool_definitions = self._tool_definitions_for_browser_mode(
                browser_mode,
                browser_initialized,
            )
            step_trace = (
                self.tracer.start_step(step_index)
                if self._tracing_active()
                else None
            )
            model_turn = await self.model_execution.request(
                messages,
                step_id=step_trace.step_id if step_trace else None,
                task_anchor=user_input,
                tool_definitions=tool_definitions,
            )
            if model_turn.error:
                error = model_turn.error
                if step_trace:
                    self.tracer.finish_step(status="failed", error=error)
                output = (
                    error
                    if model_turn.error_reason == "llm_timeout"
                    else f"调用模型时出错: {error}"
                )
                return output, "failed", error

            message = model_turn.message
            finish_reason = model_turn.finish_reason
            content = model_turn.content

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

            execution_context = self._execution_context(
                session_key=session_key,
                browser_mode=browser_mode,
                browser_snapshot="",
                browser_initialized=browser_initialized,
            )
            await self._execute_tool_batch(
                list(message.tool_calls),
                messages=messages,
                execution_context=execution_context,
                session_key=session_key,
                task_id=None,
                step_id=step_trace.step_id if step_trace else None,
                repeat_tracker=repeat_tracker,
            )
            browser_initialized = execution_context.browser_initialized
            if step_trace:
                self.tracer.finish_step()

        return (
            f"已达到单次任务的 {react_step_limit} 步执行上限，任务尚未正常结束。",
            "max_steps",
            None,
        )
