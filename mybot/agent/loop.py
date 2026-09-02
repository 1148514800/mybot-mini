from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime
from types import SimpleNamespace

from openai import OpenAI

from ..core.config import GatewayConfig
from ..guardrails import (
    ApprovalIntent,
    ApprovalManager,
    PendingApproval,
    PolicyDecision,
    PolicyResult,
    ToolPolicy,
    classify_approval_intent,
)
from ..messaging import InboundMessage, MessageBus, OutboundMessage
from ..storage.session import SessionManager
from ..tools import ToolRegistry, ToolResult
from ..tools.browser.connection import LOCAL_BROWSER_SESSION
from ..tools.browser.navigation import MANAGED_BROWSER_SESSION
from ..tracing import AgentRunTrace, AgentTracer, redact_mapping
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
        tool_policy: ToolPolicy | None = None,
        approvals: ApprovalManager | None = None,
    ):
        self.client = client
        self.config = config
        self.bus = bus
        self.tools = tools
        self.context = context
        self.sessions = sessions
        self.tracer = tracer or AgentTracer()
        self.tool_policy = tool_policy or ToolPolicy()
        self.approvals = approvals or ApprovalManager()

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

    def _decode_tool_call(
        self,
        tool_call,
        browser_mode: str,
    ) -> tuple[str, dict | None, ToolResult | None]:
        name = tool_call.function.name
        if browser_mode == BROWSER_MODE_LOCAL and name == "browser_open":
            return name, None, ToolResult(
                success=False,
                error=(
                    "browser_open is blocked because the user explicitly "
                    "requested the local browser. Use browser_attach."
                ),
            )
        if browser_mode == BROWSER_MODE_MANAGED and name == "browser_attach":
            return name, None, ToolResult(
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
            return name, None, ToolResult(
                success=False,
                error=f"Invalid arguments for tool '{name}': {exc}",
            )
        if not isinstance(arguments, dict):
            return name, None, ToolResult(
                success=False,
                error=f"Arguments for tool '{name}' must be a JSON object.",
            )
        if name.startswith("browser_") and name not in {
            "browser_attach",
            "browser_open",
        }:
            arguments = dict(arguments)
            arguments["session"] = _BROWSER_SESSION_BY_MODE[browser_mode]
        return name, arguments, None

    @staticmethod
    def _policy_metadata(
        policy: PolicyResult,
        *,
        approval_id: str | None = None,
        approval_status: str | None = None,
    ) -> dict:
        metadata = {
            "risk_level": policy.risk_level.value,
            "policy_decision": policy.decision.value,
            "policy_rule": policy.rule,
            "policy_reason": policy.reason,
        }
        metadata.update(policy.metadata)
        if approval_id:
            metadata["approval_id"] = approval_id
        if approval_status:
            metadata["approval_status"] = approval_status
        return {key: value for key, value in metadata.items() if value is not None}

    @staticmethod
    def _serialize_tool_call(tool_call) -> dict:
        return {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            },
        }

    @staticmethod
    def _deserialize_tool_call(value: dict):
        function = value.get("function", {})
        return SimpleNamespace(
            id=str(value.get("id", "")),
            function=SimpleNamespace(
                name=str(function.get("name", "")),
                arguments=function.get("arguments", "{}"),
            ),
        )

    async def _execute_normalized_tool(
        self,
        name: str,
        arguments: dict,
    ) -> ToolResult:
        self._trace(
            f"tool call name={name} args="
            f"{json.dumps(arguments, ensure_ascii=False)}"
        )
        result = await self.tools.execute(name, arguments)
        preview = result.to_text()[:300].replace("\n", " ")
        self._trace(f"tool result name={name} result={preview}")
        return result

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

    def _tool_runtime_metadata(self, name: str) -> dict:
        getter = getattr(self.tools, "get_runtime_metadata", None)
        if not callable(getter):
            return {}
        metadata = getter(name)
        return dict(metadata) if isinstance(metadata, dict) else {}

    async def _execute_tool_call(
        self,
        tool_call,
        browser_mode: str = BROWSER_MODE_MANAGED,
    ) -> ToolResult:
        """Decode, policy-check and execute a call used outside the ReAct loop."""
        name, arguments, decode_error = self._decode_tool_call(
            tool_call,
            browser_mode,
        )
        if decode_error:
            return decode_error
        assert arguments is not None
        policy = self.tool_policy.evaluate(
            name,
            arguments,
            tool_metadata=self._tool_runtime_metadata(name),
        )
        metadata = self._policy_metadata(policy)
        if policy.decision == PolicyDecision.BLOCK:
            return ToolResult(
                success=False,
                error=f"Blocked by tool policy: {policy.reason}",
                metadata=metadata,
            )
        if policy.decision == PolicyDecision.REQUIRE_CONFIRMATION:
            return ToolResult(
                success=False,
                error=f"Tool policy requires confirmation: {policy.reason}",
                metadata=metadata,
            )
        return await self._execute_normalized_tool(name, arguments)

    async def run(self):
        while True:
            try:
                message = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            reply, run_trace = await self.handle_inbound_message(message)
            self._trace(run_trace.summary_text().replace("\n", " | "))
            await self.bus.publish_outbound(
                OutboundMessage(channel=message.channel, chat_id=message.chat_id, content=reply)
            )

    async def handle_inbound_message(
        self,
        message: InboundMessage,
    ) -> tuple[str, AgentRunTrace]:
        """Handle one bus message, including pending approval intent."""
        pending = self.approvals.get(message.session_key)
        intent = classify_approval_intent(message.content)
        cancelled_approval_id: str | None = None

        if pending and intent == ApprovalIntent.APPROVE:
            approved = self.approvals.approve(
                message.session_key,
                pending.approval_id,
            )
            assert approved is not None
            reply, trace = await self._resume_approved(
                approved,
                message.content,
            )
        elif pending and intent == ApprovalIntent.REJECT:
            rejected = self.approvals.reject(
                message.session_key,
                pending.approval_id,
            )
            assert rejected is not None
            reply, trace = self._cancelled_trace(rejected, message.content)
        else:
            if pending:
                rejected = self.approvals.reject(
                    message.session_key,
                    pending.approval_id,
                )
                cancelled_approval_id = (
                    rejected.approval_id if rejected else None
                )
            session = self.sessions.get_or_create(message.session_key)
            history = session.build_prompt_history(max_recent_messages=12)
            messages = self.context.build_messages(history, message.content)
            browser_mode = self.context.resolve_browser_mode(message.content)
            reply, trace = await self.run_traced(
                message.content,
                messages,
                browser_mode,
                session_key=message.session_key,
                metadata={
                    "cancelled_approval_id": cancelled_approval_id,
                }
                if cancelled_approval_id
                else None,
            )

        session = self.sessions.get_or_create(message.session_key)
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
        return reply, trace

    async def run_traced(
        self,
        user_input: str,
        messages: list[dict],
        browser_mode: str = BROWSER_MODE_MANAGED,
        *,
        session_key: str = "",
        metadata: dict | None = None,
    ) -> tuple[str, AgentRunTrace]:
        """Run the existing ReAct loop and return its completed in-memory trace."""
        run_metadata = {
            "browser_mode": browser_mode,
            "model": self.config.model,
            "provider": getattr(self.config, "provider", ""),
        }
        run_metadata.update(metadata or {})
        self.tracer.start_run(
            user_input,
            metadata=run_metadata,
        )
        try:
            output, status, error = await self._react_loop_outcome(
                messages,
                browser_mode,
                user_input=user_input,
                session_key=session_key,
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

    def _cancelled_trace(
        self,
        pending: PendingApproval,
        user_input: str,
    ) -> tuple[str, AgentRunTrace]:
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": pending.browser_mode,
                "approval_id": pending.approval_id,
                "approval_status": "rejected",
                "resumed_from_run_id": pending.origin_run_id,
            },
        )
        output = (
            f"已取消操作：{pending.tool_name}。该工具没有执行。"
        )
        return output, self.tracer.finish_run(
            final_output=output,
            status="cancelled",
        )

    async def resume_pending(
        self,
        session_key: str,
        user_input: str,
    ) -> tuple[str, AgentRunTrace]:
        """Deterministically approve, reject, or replace one pending action."""
        pending = self.approvals.get(session_key)
        intent = classify_approval_intent(user_input)
        if pending is None:
            self.tracer.start_run(
                user_input,
                metadata={"session_key": session_key},
            )
            output = "当前会话没有等待确认的操作。"
            return output, self.tracer.finish_run(
                final_output=output,
                status="cancelled",
            )
        if intent == ApprovalIntent.APPROVE:
            approved = self.approvals.approve(session_key, pending.approval_id)
            assert approved is not None
            return await self._resume_approved(approved, user_input)
        rejected = self.approvals.reject(session_key, pending.approval_id)
        assert rejected is not None
        return self._cancelled_trace(rejected, user_input)

    @staticmethod
    def _approval_prompt(pending: PendingApproval) -> str:
        return (
            "准备执行需要确认的操作：\n\n"
            f"Tool: {pending.tool_name}\n"
            f"Risk: {pending.risk_level.value}\n"
            f"Reason: {pending.reason}\n"
            f"Approval ID: {pending.approval_id}\n\n"
            "是否继续？回复“确认”继续，回复“取消”放弃。"
        )

    def _create_pending(
        self,
        *,
        session_key: str,
        name: str,
        arguments: dict,
        policy: PolicyResult,
        tool_call,
        browser_mode: str,
        messages: list[dict],
        remaining_tool_calls: list,
        browser_snapshot: str,
    ) -> PendingApproval:
        current_run = self.tracer.get_current_run()
        effective_session_key = session_key or (
            f"run:{current_run.run_id}" if current_run else "run:untraced"
        )
        return self.approvals.create(
            session_key=effective_session_key,
            tool_name=name,
            arguments=arguments,
            policy=policy,
            origin_run_id=current_run.run_id if current_run else None,
            browser_mode=browser_mode,
            model_tool_call_id=tool_call.id,
            messages=messages,
            remaining_tool_calls=[
                self._serialize_tool_call(item) for item in remaining_tool_calls
            ],
            browser_snapshot=browser_snapshot,
        )

    async def _resume_approved(
        self,
        pending: PendingApproval,
        user_input: str,
    ) -> tuple[str, AgentRunTrace]:
        browser_mode = pending.browser_mode or BROWSER_MODE_MANAGED
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": browser_mode,
                "model": self.config.model,
                "provider": getattr(self.config, "provider", ""),
                "resumed_from_run_id": pending.origin_run_id,
                "approval_id": pending.approval_id,
                "approval_status": "approved",
            },
        )
        messages = copy.deepcopy(pending.messages)
        browser_snapshot = pending.browser_snapshot
        step_trace = self.tracer.start_step(1)
        policy = PolicyResult(
            decision=PolicyDecision.REQUIRE_CONFIRMATION,
            risk_level=pending.risk_level,
            reason=pending.reason,
            rule=pending.policy_rule,
        )
        tool_trace = self.tracer.start_tool_call(
            step_id=step_trace.step_id,
            tool_name=pending.tool_name,
            arguments=pending.arguments,
            metadata={
                "model_tool_call_id": pending.model_tool_call_id,
                **self._tool_runtime_metadata(pending.tool_name),
                **self._policy_metadata(
                    policy,
                    approval_id=pending.approval_id,
                    approval_status="approved",
                ),
            },
        )
        try:
            result = await self._execute_normalized_tool(
                pending.tool_name,
                pending.arguments,
            )
        except Exception as exc:
            self.tracer.finish_tool_call(
                tool_trace,
                error=f"{type(exc).__name__}: {exc}",
            )
            self.tracer.finish_step(status="failed", error=str(exc))
            self.tracer.finish_run(status="failed", error=str(exc))
            raise
        self.tracer.finish_tool_call(tool_trace, result=result)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": pending.model_tool_call_id,
                "content": result.to_text(),
            }
        )
        if pending.tool_name == "browser_snapshot" and result.success:
            browser_snapshot = result.output

        remaining = [
            self._deserialize_tool_call(value)
            for value in pending.remaining_tool_calls
        ]
        for index, tool_call in enumerate(remaining):
            name, arguments, decode_error = self._decode_tool_call(
                tool_call,
                browser_mode,
            )
            traced_arguments = arguments or self._tool_arguments_for_trace(
                tool_call,
                browser_mode,
            )
            next_trace = self.tracer.start_tool_call(
                step_id=step_trace.step_id,
                tool_name=name,
                arguments=traced_arguments,
                metadata={
                    "model_tool_call_id": tool_call.id,
                    **self._tool_runtime_metadata(name),
                },
            )
            if decode_error:
                next_result = decode_error
            else:
                assert arguments is not None
                next_policy = self.tool_policy.evaluate(
                    name,
                    arguments,
                    user_input=user_input,
                    context={"browser_snapshot": browser_snapshot},
                    tool_metadata=self._tool_runtime_metadata(name),
                )
                next_trace.metadata.update(
                    redact_mapping(self._policy_metadata(next_policy))
                )
                if next_policy.decision == PolicyDecision.REQUIRE_CONFIRMATION:
                    next_pending = self._create_pending(
                        session_key=pending.session_key,
                        name=name,
                        arguments=arguments,
                        policy=next_policy,
                        tool_call=tool_call,
                        browser_mode=browser_mode,
                        messages=messages,
                        remaining_tool_calls=remaining[index + 1 :],
                        browser_snapshot=browser_snapshot,
                    )
                    waiting = ToolResult(
                        success=False,
                        error="Awaiting user confirmation; tool was not executed.",
                        metadata=self._policy_metadata(
                            next_policy,
                            approval_id=next_pending.approval_id,
                            approval_status="pending",
                        ),
                    )
                    self.tracer.finish_tool_call(next_trace, result=waiting)
                    self.tracer.finish_step(status="awaiting_confirmation")
                    output = self._approval_prompt(next_pending)
                    trace = self.tracer.finish_run(
                        final_output=output,
                        status="awaiting_confirmation",
                    )
                    return output, trace
                if next_policy.decision == PolicyDecision.BLOCK:
                    next_result = ToolResult(
                        success=False,
                        error=f"Blocked by tool policy: {next_policy.reason}",
                        metadata=self._policy_metadata(next_policy),
                    )
                else:
                    next_result = await self._execute_normalized_tool(
                        name,
                        arguments,
                    )
            self.tracer.finish_tool_call(next_trace, result=next_result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": next_result.to_text(),
                }
            )
            if name == "browser_snapshot" and next_result.success:
                browser_snapshot = next_result.output

        self.tracer.finish_step()
        try:
            output, status, error = await self._react_loop_outcome(
                messages,
                browser_mode,
                user_input=user_input,
                session_key=pending.session_key,
                browser_snapshot=browser_snapshot,
                step_index_offset=1,
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
        *,
        user_input: str = "",
        session_key: str = "",
        browser_snapshot: str = "",
        step_index_offset: int = 0,
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
            step_index = step + 1 + step_index_offset
            self._trace(f"model step={step_index}")
            step_trace = (
                self.tracer.start_step(step_index)
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

            for tool_index, tool_call in enumerate(message.tool_calls):
                name, arguments, decode_error = self._decode_tool_call(
                    tool_call,
                    browser_mode,
                )
                policy = (
                    self.tool_policy.evaluate(
                        name,
                        arguments,
                        user_input=user_input,
                        context={"browser_snapshot": browser_snapshot},
                        tool_metadata=self._tool_runtime_metadata(name),
                    )
                    if arguments is not None and decode_error is None
                    else None
                )
                trace_metadata = {
                    "model_tool_call_id": tool_call.id,
                    **self._tool_runtime_metadata(name),
                }
                if policy:
                    trace_metadata.update(self._policy_metadata(policy))
                tool_trace = (
                    self.tracer.start_tool_call(
                        step_id=step_trace.step_id,
                        tool_name=name,
                        arguments=(
                            arguments
                            or self._tool_arguments_for_trace(
                                tool_call,
                                browser_mode,
                            )
                        ),
                        metadata=trace_metadata,
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

                if decode_error is not None:
                    result = decode_error
                elif (
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
                elif policy and policy.decision == PolicyDecision.BLOCK:
                    result = ToolResult(
                        success=False,
                        error=f"Blocked by tool policy: {policy.reason}",
                        metadata=self._policy_metadata(policy),
                    )
                elif (
                    policy
                    and policy.decision
                    == PolicyDecision.REQUIRE_CONFIRMATION
                ):
                    assert arguments is not None
                    pending = self._create_pending(
                        session_key=session_key,
                        name=name,
                        arguments=arguments,
                        policy=policy,
                        tool_call=tool_call,
                        browser_mode=browser_mode,
                        messages=messages,
                        remaining_tool_calls=message.tool_calls[
                            tool_index + 1 :
                        ],
                        browser_snapshot=browser_snapshot,
                    )
                    waiting = ToolResult(
                        success=False,
                        error="Awaiting user confirmation; tool was not executed.",
                        metadata=self._policy_metadata(
                            policy,
                            approval_id=pending.approval_id,
                            approval_status="pending",
                        ),
                    )
                    if tool_trace:
                        self.tracer.finish_tool_call(
                            tool_trace,
                            result=waiting,
                        )
                    if step_trace:
                        self.tracer.finish_step(
                            status="awaiting_confirmation"
                        )
                    return (
                        self._approval_prompt(pending),
                        "awaiting_confirmation",
                        None,
                    )
                else:
                    assert arguments is not None
                    try:
                        result = await self._execute_normalized_tool(
                            name,
                            arguments,
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
                if name == "browser_snapshot" and result.success:
                    browser_snapshot = result.output

            if step_trace:
                self.tracer.finish_step()

        return (
            f"已达到单次任务的 {react_step_limit} 步执行上限，任务尚未正常结束。",
            "max_steps",
            None,
        )
