from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from openai import APITimeoutError, AsyncOpenAI

from ..config import GatewayConfig
from ..tools import ToolRegistry, ToolResult
from ..tracing import AgentRunTrace, AgentTracer, redact_arguments, redact_text
from .context import BROWSER_MODE_LOCAL, BROWSER_MODE_MANAGED, ContextBuilder


MAX_REACT_STEPS_HARD_LIMIT = 30
MAX_RATE_LIMIT_RETRIES_HARD_LIMIT = 10
MAX_REPEATED_TOOL_CALLS = 2
MAX_EMPTY_RESPONSES = 2

BROWSER_SESSION_BY_MODE = {
    BROWSER_MODE_LOCAL: "local_browser",
    BROWSER_MODE_MANAGED: "managed_browser",
}
BROWSER_ENTRY_TOOLS = ("browser_open", "browser_attach")


class AgentLoop:
    """Run the ReAct loop for one CLI conversation."""

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

    # -- CLI ---------------------------------------------------------------
    async def run(self) -> None:
        """Read prompts from stdin until the user exits."""
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
                reply, trace = await self.handle_message(user_input)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                print(f"\nBot: 运行时错误: {type(exc).__name__}: {exc}\n")
                continue
            self.trace(trace.summary_text().replace("\n", " | "))
            print(f"\nBot: {reply}\n")

    async def handle_message(self, user_input: str) -> tuple[str, AgentRunTrace]:
        """Answer one user message and return the finished trace."""
        return await self.run_traced(
            user_input,
            self.context.build_messages(user_input),
            self.context.resolve_browser_mode(user_input),
        )

    def trace(self, message: str) -> None:
        if self.config.show_internal_process:
            print(f"[trace] {redact_text(message)}")

    # -- ReAct -------------------------------------------------------------
    async def run_traced(
        self,
        user_input: str,
        messages: list[dict],
        browser_mode: str = BROWSER_MODE_MANAGED,
    ) -> tuple[str, AgentRunTrace]:
        self.tracer.start_run(
            user_input,
            metadata={"browser_mode": browser_mode, "model": self.config.model},
        )
        try:
            output, status, error = await self._react(messages, browser_mode)
        except BaseException as exc:
            self.tracer.finish_run(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        return output, self.tracer.finish_run(
            final_output=output, status=status, error=error
        )

    async def _react(
        self,
        messages: list[dict],
        browser_mode: str,
    ) -> tuple[str, str, str | None]:
        final_parts: list[str] = []
        limit = max(1, min(self.config.max_react_steps, MAX_REACT_STEPS_HARD_LIMIT))
        empty_responses = 0
        browser_initialized = False
        last_signature = ""
        repeated = 0

        for step in range(1, limit + 1):
            self.trace(f"model step={step}")
            step_trace = self.tracer.start_step(step)
            turn = await self._request_model(
                messages, step_trace, browser_mode, browser_initialized
            )
            if turn["error"]:
                self.tracer.finish_step(status="failed", error=turn["error"])
                output = turn["error"] if turn["timeout"] else f"调用模型时出错: {turn['error']}"
                return output, "failed", turn["error"]

            message, finish_reason, content = turn["message"], turn["finish_reason"], turn["content"]

            if finish_reason == "length" and content:
                final_parts.append(content)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "Continue where you stopped."})
                self.tracer.finish_step()
                continue

            if not message.tool_calls:
                if content:
                    final_parts.append(content)
                    self.tracer.finish_step()
                    return "".join(final_parts).strip(), "success", None
                empty_responses += 1
                if empty_responses < MAX_EMPTY_RESPONSES:
                    messages.append(
                        {
                            "role": "user",
                            "content": "上一轮没有返回文本或工具调用，请继续完成任务或说明原因。",
                        }
                    )
                    self.tracer.finish_step(status="empty_response")
                    continue
                error = "model returned consecutive empty responses"
                self.tracer.finish_step(status="failed", error=error)
                return (
                    "".join(final_parts).strip() or "模型连续返回空响应。",
                    "failed",
                    error,
                )

            empty_responses = 0
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in message.tool_calls
                    ],
                }
            )
            for call in message.tool_calls:
                signature = self._signature(call)
                repeated = repeated + 1 if signature == last_signature else 0
                last_signature = signature
                guard = None
                if repeated >= MAX_REPEATED_TOOL_CALLS:
                    guard = ToolResult(
                        success=False,
                        error=(
                            "Repeated identical tool call blocked. Inspect the latest "
                            "result, choose a different action, or finish the task."
                        ),
                    )
                    self.trace(f"blocked repeated tool call name={call.function.name}")
                result = await self._execute(
                    call, browser_mode, browser_initialized, step_trace, guard
                )
                if result.success and call.function.name in BROWSER_ENTRY_TOOLS:
                    browser_initialized = True
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result.to_text(),
                    }
                )
            self.tracer.finish_step()

        return (
            f"已达到单次任务的 {limit} 步执行上限，任务尚未正常结束。",
            "max_steps",
            None,
        )

    # -- model -------------------------------------------------------------
    async def _request_model(
        self,
        messages: list[dict],
        step_trace: Any,
        browser_mode: str,
        browser_initialized: bool,
    ) -> dict[str, Any]:
        definitions = [
            definition
            for definition in self.tools.get_definitions()
            if definition["function"]["name"] not in self._blocked_tools(
                browser_mode, browser_initialized
            )
        ]
        retries = max(0, min(self.config.rate_limit_retries, MAX_RATE_LIMIT_RETRIES_HARD_LIMIT))
        timeout = max(1.0, float(self.config.request_timeout_seconds))
        attempt = 0
        while True:
            call_trace = self.tracer.start_llm_call(
                step_trace, self.config.model, len(messages), retry_count=attempt
            )
            start = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.config.model,
                        messages=messages,
                        tools=definitions or None,
                        temperature=0.1,
                        max_tokens=self.config.max_completion_tokens,
                    ),
                    timeout=timeout,
                )
            except (TimeoutError, APITimeoutError):
                error = f"LLM request timeout after {timeout:g}s"
                self.tracer.finish_llm_call(call_trace, error=error)
                return {"error": error, "timeout": True}
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self.tracer.finish_llm_call(call_trace, error=error)
                if self._is_rate_limit(exc) and attempt < retries:
                    attempt += 1
                    self.trace(f"rate limited, retry {attempt}/{retries}")
                    await asyncio.sleep(min(60, 5 * attempt))
                    continue
                return {"error": error, "timeout": False}

            choice = response.choices[0]
            usage = getattr(response, "usage", None)
            self.tracer.finish_llm_call(
                call_trace,
                finish_reason=choice.finish_reason,
                total_tokens=getattr(usage, "total_tokens", None),
            )
            call_trace.metadata["elapsed_ms"] = round(
                (time.perf_counter() - start) * 1000, 1
            )
            return {
                "message": choice.message,
                "content": (choice.message.content or "").strip(),
                "finish_reason": choice.finish_reason,
                "error": None,
            }

    # -- tools -------------------------------------------------------------
    async def _execute(
        self,
        call: Any,
        browser_mode: str,
        browser_initialized: bool,
        step_trace: Any,
        guard: ToolResult | None,
    ) -> ToolResult:
        name = str(call.function.name).strip()
        arguments, error = self._normalize(name, call.function.arguments, browser_mode)
        call_trace = self.tracer.start_tool_call(
            step_trace, name, arguments or {}, {"model_tool_call_id": call.id}
        )
        self.trace(
            f"tool call name={name} args={json.dumps(redact_arguments(name, arguments or {}))}"
        )
        if error is not None:
            result = error
        elif guard is not None:
            result = guard
        elif not self.tools.has_tool(name):
            result = ToolResult(success=False, error=f"unknown tool '{name}'")
        elif (validation := self._validate(name, arguments)) is not None:
            result = ToolResult(
                success=False, error=f"invalid arguments for tool '{name}': {validation}"
            )
        else:
            result = await self.tools.execute(name, arguments)

        self.tracer.finish_tool_call(call_trace, result)
        preview = json.dumps(
            {"success": result.success, "output": result.output[:300], "error": result.error},
            ensure_ascii=False,
        )
        self.trace(f"tool result name={name} result={preview}")
        return result

    def _normalize(
        self, name: str, raw_arguments: Any, browser_mode: str
    ) -> tuple[dict[str, Any] | None, ToolResult | None]:
        if name in BROWSER_ENTRY_TOOLS:
            allowed = "browser_attach" if browser_mode == BROWSER_MODE_LOCAL else "browser_open"
            if name != allowed:
                return None, ToolResult(
                    success=False,
                    error=f"{name} is blocked in {browser_mode} browser mode; use {allowed}.",
                )
        if raw_arguments in (None, ""):
            arguments: Any = {}
        elif isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                return None, ToolResult(success=False, error=f"invalid JSON arguments: {exc}")
        else:
            arguments = dict(raw_arguments)
        if not isinstance(arguments, dict):
            return None, ToolResult(success=False, error="arguments must be a JSON object")
        if name.startswith("browser_") and name not in BROWSER_ENTRY_TOOLS:
            arguments["session"] = BROWSER_SESSION_BY_MODE[browser_mode]
        return arguments, None

    def _validate(self, name: str, arguments: dict[str, Any]) -> str | None:
        schema = self.tools.get_parameters(name)
        for required in schema.get("required", []):
            if required not in arguments:
                return f"missing required field '{required}'"
        properties = schema.get("properties", {})
        for key, value in arguments.items():
            rule = properties.get(key)
            if not isinstance(rule, dict):
                continue
            expected = rule.get("type")
            if expected and not _matches_type(value, str(expected)):
                return f"field '{key}' must be {expected}"
            if "enum" in rule and value not in rule["enum"]:
                return f"field '{key}' must be one of {rule['enum']}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if "minimum" in rule and value < rule["minimum"]:
                    return f"field '{key}' must be >= {rule['minimum']}"
                if "maximum" in rule and value > rule["maximum"]:
                    return f"field '{key}' must be <= {rule['maximum']}"
        return None

    @staticmethod
    def _blocked_tools(browser_mode: str, browser_initialized: bool) -> set[str]:
        if browser_initialized:
            # Once a session exists, both entry tools are unnecessary.
            return set(BROWSER_ENTRY_TOOLS)
        blocked = "browser_open" if browser_mode == BROWSER_MODE_LOCAL else "browser_attach"
        return {blocked}

    @staticmethod
    def _signature(call: Any) -> str:
        try:
            arguments = json.dumps(
                json.loads(call.function.arguments or "{}"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, json.JSONDecodeError):
            arguments = str(call.function.arguments)
        return f"{call.function.name}:{arguments}"

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}"
        return "RateLimitError" in text or "429" in text or "TPM limit reached" in text


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    return True
