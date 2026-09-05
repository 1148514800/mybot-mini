from __future__ import annotations

import asyncio
import copy
import json
import uuid
from datetime import datetime
from types import SimpleNamespace

from openai import APITimeoutError, AsyncOpenAI

from ..core.config import GatewayConfig
from ..guardrails import (
    DEFAULT_APPROVAL_TTL_SECONDS,
    ApprovalIntent,
    ApprovalManager,
    ClarificationManager,
    PendingApproval,
    PendingClarification,
    ToolPolicy,
    classify_approval_intent,
)
from ..messaging import InboundMessage, MessageBus, OutboundMessage
from ..storage.session import SessionManager
from ..storage.checkpoints.store import ActiveTaskCheckpointStore
from ..tools import ToolRegistry, ToolResult
from ..tools.browser.connection import LOCAL_BROWSER_SESSION
from ..tools.browser.navigation import MANAGED_BROWSER_SESSION
from ..tracing import (
    REDACTED,
    AgentRunTrace,
    AgentTracer,
    redact_text,
    redact_tool_arguments,
)
from .browser_reliability import (
    BrowserRecoveryPolicy,
    BrowserTaskBudget,
    BrowserTaskState,
    RecentBrowserTask,
    RecentTaskManager,
    contains_incomplete_report,
    contains_success_claim,
    is_recent_task_continuation,
)
from .task_state import AgentTaskState, AgentTaskStatus
from .runtime_manager import TaskRuntimeManager
from .tool_execution import (
    ToolExecutionContext,
    ToolExecutionPipeline,
    ToolExecutionRequest,
    ToolExecutionStatus,
)
from .context import (
    BROWSER_MODE_LOCAL,
    BROWSER_MODE_MANAGED,
    ContextBuilder,
)


MAX_REACT_STEPS_HARD_LIMIT = 30
MAX_RATE_LIMIT_RETRIES_HARD_LIMIT = 10
MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS = 2
MAX_EMPTY_MODEL_RESPONSES = 2
DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 60.0

_BROWSER_SESSION_BY_MODE = {
    BROWSER_MODE_LOCAL: LOCAL_BROWSER_SESSION,
    BROWSER_MODE_MANAGED: MANAGED_BROWSER_SESSION,
}


class AgentLoop:
    def __init__(
        self,
        client: AsyncOpenAI,
        config: GatewayConfig,
        bus: MessageBus,
        tools: ToolRegistry,
        context: ContextBuilder,
        sessions: SessionManager,
        tracer: AgentTracer | None = None,
        tool_policy: ToolPolicy | None = None,
        approvals: ApprovalManager | None = None,
        clarifications: ClarificationManager | None = None,
        recent_tasks: RecentTaskManager | None = None,
        browser_recovery_policy: BrowserRecoveryPolicy | None = None,
        checkpoint_store: ActiveTaskCheckpointStore | None = None,
    ):
        self.client = client
        self.config = config
        self.bus = bus
        self.tools = tools
        self.context = context
        self.sessions = sessions
        self.tracer = tracer or AgentTracer()
        self.tool_policy = tool_policy or ToolPolicy(
            getattr(config, "workspace", None)
        )
        self.approvals = approvals or ApprovalManager(
            getattr(
                config,
                "approval_ttl_seconds",
                DEFAULT_APPROVAL_TTL_SECONDS,
            )
        )
        self.clarifications = clarifications or ClarificationManager()
        self.recent_tasks = recent_tasks or RecentTaskManager(
            clock=(getattr(checkpoint_store, "_clock", None) if checkpoint_store else None),
            on_expire=(checkpoint_store.clear_recent if checkpoint_store else None),
            ttl_seconds=(getattr(checkpoint_store, "recent_task_ttl_seconds", 86_400) if checkpoint_store else 86_400),
        )
        self.browser_recovery_policy = (
            browser_recovery_policy or BrowserRecoveryPolicy()
        )
        self.tool_execution = ToolExecutionPipeline(
            self.tools,
            self.tool_policy,
            self.approvals,
            self.tracer,
            self.browser_recovery_policy,
            debug_trace=self._trace,
        )
        self.checkpoint_store = checkpoint_store
        if hasattr(self.context, "max_context_chars"):
            self.context.max_context_chars = getattr(config, "max_context_chars", self.context.max_context_chars)
            self.context.max_recent_messages = getattr(config, "max_recent_messages", self.context.max_recent_messages)
            self.context.max_tool_result_chars = getattr(config, "max_tool_result_chars", self.context.max_tool_result_chars)
            self.context.max_memory_chars = getattr(config, "max_memory_chars", self.context.max_memory_chars)
        self.runtime = TaskRuntimeManager(
            approvals=self.approvals,
            clarifications=self.clarifications,
            recent_tasks=self.recent_tasks,
            checkpoint_store=self.checkpoint_store,
        )
        self.task_states = self.runtime.task_states
        self._restore_checkpoints()

    def _restore_checkpoints(self) -> None:
        self.runtime.restore()

    def _pipeline(self) -> ToolExecutionPipeline:
        """Keep injected test/runtime dependencies aligned with the pipeline."""
        self.tool_execution.tools = self.tools
        self.tool_execution.policy = self.tool_policy
        self.tool_execution.approvals = self.approvals
        self.tool_execution.tracer = self.tracer
        self.tool_execution.browser_recovery_policy = self.browser_recovery_policy
        return self.tool_execution

    def _task_state(
        self,
        task_id: str,
        session_key: str,
        requester_sender_id: str | None,
    ) -> AgentTaskState:
        return self.runtime.task_state(task_id, session_key, requester_sender_id)

    @staticmethod
    def _start_or_resume_task(state: AgentTaskState) -> None:
        if state.status != AgentTaskStatus.RUNNING:
            state.transition(AgentTaskStatus.RUNNING)

    def _finish_run_for_task(
        self,
        task_state: AgentTaskState,
        *,
        final_output: str = "",
        runtime_status: str = "success",
        error: str | None = None,
    ) -> AgentRunTrace:
        trace = self.tracer.finish_run(
            final_output=final_output,
            status=runtime_status,
            error=error,
            task_status=task_state.status.value,
        )
        self.runtime.sync(task_state)
        return trace

    def _sync_task_checkpoint(self, state: AgentTaskState) -> None:
        self.runtime.sync(state)

    def _clear_active_checkpoint(self, session_key: str) -> None:
        self.runtime.clear(session_key)

    def _consume_durable_approval(self, session_key: str) -> bool:
        return self.runtime.consume(session_key)

    def _consume_durable_active(self, session_key: str) -> bool:
        return self._consume_durable_approval(session_key)

    def _trace(self, message: str) -> None:
        if self.config.show_internal_process:
            print(f"[trace] {redact_text(message)}")

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

    def _effective_request_timeout_seconds(self) -> float:
        raw_timeout = getattr(
            self.config,
            "request_timeout_seconds",
            DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
        )
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            timeout = DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS
        return timeout if timeout > 0 else DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS

    def _browser_task_budget(self) -> BrowserTaskBudget:
        return BrowserTaskBudget(
            max_browser_open_attempts=max(
                0,
                int(
                    getattr(self.config, "browser_max_open_attempts", 1)
                ),
            ),
            max_consecutive_tool_failures=max(
                0,
                int(
                    getattr(
                        self.config,
                        "browser_max_consecutive_tool_failures",
                        2,
                    )
                ),
            ),
            max_failed_action_retries=max(
                0,
                int(
                    getattr(
                        self.config,
                        "browser_max_failed_action_retries",
                        1,
                    )
                ),
            ),
            max_browser_evals=max(
                0,
                int(
                    getattr(self.config, "browser_max_eval_fallbacks", 1)
                ),
            ),
            max_recovery_steps=max(
                0,
                int(
                    getattr(self.config, "browser_max_recovery_steps", 2)
                ),
            ),
        )

    @staticmethod
    def _timeout_error(timeout_seconds: float) -> str:
        return f"LLM request timeout after {timeout_seconds:g}s"

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

    def _execution_context(
        self,
        *,
        browser_mode: str,
        browser_snapshot: str,
        loaded_skills: set[str],
        browser_initialized: bool,
        browser_state: BrowserTaskState,
    ) -> ToolExecutionContext:
        return ToolExecutionContext(
            browser_mode=browser_mode,
            browser_snapshot=browser_snapshot,
            loaded_skills=loaded_skills,
            browser_initialized=browser_initialized,
            browser_state=browser_state,
            browser_budget=self._browser_task_budget(),
        )

    async def _execute_tool_batch(
        self,
        tool_calls: list,
        *,
        messages: list[dict],
        execution_context: ToolExecutionContext,
        task_state: AgentTaskState,
        user_input: str,
        requester_sender_id: str | None,
        step_id: str | None,
        repeat_tracker: dict[str, object] | None = None,
    ) -> tuple[str | None, str | None]:
        """Execute a model tool batch through the shared execution pipeline."""
        for tool_index, tool_call in enumerate(tool_calls):
            execution_guard = None
            if repeat_tracker is not None:
                signature = self._tool_call_signature(tool_call)
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

            if task_state.status == AgentTaskStatus.WAITING_VERIFICATION:
                task_state.transition(
                    AgentTaskStatus.RUNNING,
                    reason="verification_action_started",
                )
            request = ToolExecutionRequest(
                tool_name=tool_call.function.name,
                arguments=tool_call.function.arguments or "{}",
                session_key=task_state.session_key,
                sender_id=requester_sender_id,
                task_id=task_state.task_id,
                model_tool_call_id=tool_call.id,
                user_input=user_input,
                step_id=step_id,
                messages=messages,
                remaining_tool_calls=[
                    self._serialize_tool_call(item)
                    for item in tool_calls[tool_index + 1 :]
                ],
                execution_guard=execution_guard,
            )
            outcome = await self._pipeline().execute(
                request,
                execution_context,
            )
            result = outcome.tool_result

            if (
                outcome.tool_name == "request_user_input"
                and outcome.status == ToolExecutionStatus.EXECUTED
                and result.success
            ):
                pending = self._create_clarification(
                    session_key=task_state.session_key,
                    question=result.output,
                    tool_call=tool_call,
                    browser_mode=execution_context.browser_mode,
                    messages=messages,
                    remaining_tool_calls=tool_calls[tool_index + 1 :],
                    browser_snapshot=execution_context.browser_snapshot,
                    task_id=task_state.task_id,
                    loaded_skills=execution_context.loaded_skills,
                    browser_initialized=execution_context.browser_initialized,
                    browser_state=execution_context.browser_state,
                    requester_sender_id=requester_sender_id,
                )
                result.metadata.update(
                    {
                        "clarification_id": pending.clarification_id,
                        "clarification_status": "pending",
                    }
                )
                if outcome.tool_call_trace is not None:
                    outcome.tool_call_trace.metadata.update(
                        {
                            "clarification_id": pending.clarification_id,
                            "clarification_status": "pending",
                        }
                    )
                task_state.transition(
                    AgentTaskStatus.WAITING_CLARIFICATION,
                    reason="user_input_required",
                    clarification_id=pending.clarification_id,
                )
                return result.output, "awaiting_clarification"

            if outcome.status == ToolExecutionStatus.WAITING_APPROVAL:
                pending = outcome.pending_approval
                assert pending is not None
                task_state.transition(
                    AgentTaskStatus.WAITING_APPROVAL,
                    reason=outcome.policy_result.reason
                    if outcome.policy_result
                    else "approval_required",
                    approval_id=pending.approval_id,
                )
                return self._approval_prompt(pending), "awaiting_confirmation"

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result.to_text(),
                }
            )
            self._sync_verification_task_state(task_state, execution_context)
        return None, None

    @staticmethod
    def _sync_verification_task_state(
        task_state: AgentTaskState,
        execution_context: ToolExecutionContext,
    ) -> None:
        if (
            execution_context.browser_state.completion_state
            == "verification_required"
            and task_state.status == AgentTaskStatus.RUNNING
        ):
            task_state.transition(
                AgentTaskStatus.WAITING_VERIFICATION,
                reason="browser_postcondition_required",
            )
        elif (
            execution_context.browser_state.completion_state == "verified"
            and task_state.status == AgentTaskStatus.WAITING_VERIFICATION
        ):
            task_state.transition(
                AgentTaskStatus.RUNNING,
                reason="browser_postcondition_verified",
            )

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

    async def _execute_tool_call(
        self,
        tool_call,
        browser_mode: str = BROWSER_MODE_MANAGED,
    ) -> ToolResult:
        """Execute a call outside ReAct through the same runtime boundary."""
        outcome = await self._pipeline().execute(
            ToolExecutionRequest(
                tool_name=tool_call.function.name,
                arguments=tool_call.function.arguments or "{}",
            ),
            ToolExecutionContext(
                browser_mode=browser_mode,
                browser_budget=self._browser_task_budget(),
            ),
        )
        return outcome.tool_result

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
        intent = classify_approval_intent(message.content)
        expired = self.approvals.expire(message.session_key)
        pending = self.approvals.get(message.session_key)
        pending_clarification = self.clarifications.get(message.session_key)
        cancelled_approval_id: str | None = None

        if expired and intent in {
            ApprovalIntent.APPROVE,
            ApprovalIntent.REJECT,
        }:
            reply, trace = self._expired_approval_trace(
                expired,
                message.content,
            )
        elif (
            pending
            and intent in {ApprovalIntent.APPROVE, ApprovalIntent.REJECT}
            and pending.requester_sender_id is not None
            and pending.requester_sender_id != message.sender_id
        ):
            reply, trace = self._approval_authorization_mismatch_trace(
                pending,
                message.content,
            )
        elif pending and intent == ApprovalIntent.APPROVE:
            if not self._consume_durable_approval(message.session_key):
                reply, trace = self._checkpoint_consume_failed_trace(
                    pending, message.content
                )
                return self._save_message_result(message, reply, trace)
            approved = self.approvals.approve(
                message.session_key,
                pending.approval_id,
                message.sender_id,
            )
            assert approved is not None
            self._clear_active_checkpoint(message.session_key)
            reply, trace = await self._resume_approved(
                approved,
                message.content,
                message.sender_id,
            )
        elif pending and intent == ApprovalIntent.REJECT:
            rejected = self.approvals.reject(
                message.session_key,
                pending.approval_id,
                message.sender_id,
            )
            assert rejected is not None
            self._clear_active_checkpoint(message.session_key)
            reply, trace = self._cancelled_trace(rejected, message.content)
        elif pending_clarification is not None:
            if (
                pending_clarification.requester_sender_id is not None
                and pending_clarification.requester_sender_id != message.sender_id
            ):
                reply, trace = self._clarification_authorization_mismatch_trace(
                    pending_clarification, message.content
                )
                return self._save_message_result(message, reply, trace)
            if not self._consume_durable_active(message.session_key):
                reply, trace = self._checkpoint_consume_failed_trace(
                    pending_clarification, message.content, kind="clarification"
                )
                return self._save_message_result(message, reply, trace)
            resolved = self.clarifications.resolve(
                message.session_key,
                pending_clarification.clarification_id,
                message.sender_id,
            )
            if resolved is None:
                reply, trace = self._clarification_authorization_mismatch_trace(
                    pending_clarification, message.content
                )
                return self._save_message_result(message, reply, trace)
            assert resolved is not None
            self._clear_active_checkpoint(message.session_key)
            reply, trace = await self._resume_clarification(
                resolved,
                message.content,
            )
        elif (
            is_recent_task_continuation(message.content)
            and self.recent_tasks.get(message.session_key) is not None
        ):
            recent = self.recent_tasks.get(message.session_key)
            assert recent is not None
            reply, trace = await self._resume_recent_task(
                recent,
                message.content,
                requester_sender_id=message.sender_id,
            )
        else:
            if pending and (
                pending.requester_sender_id is None
                or pending.requester_sender_id == message.sender_id
            ):
                rejected = self.approvals.reject(
                    message.session_key,
                    pending.approval_id,
                    message.sender_id,
                )
                cancelled_approval_id = (
                    rejected.approval_id if rejected else None
                )
                if rejected is not None:
                    self._clear_active_checkpoint(message.session_key)
                if rejected and rejected.task_id:
                    cancelled_state = self.task_states.get(rejected.task_id)
                    if (
                        cancelled_state is not None
                        and cancelled_state.status
                        == AgentTaskStatus.WAITING_APPROVAL
                    ):
                        cancelled_state.transition(
                            AgentTaskStatus.CANCELLED,
                            reason="replaced_by_new_task",
                        )
            session = self.sessions.get_or_create(message.session_key)
            history = session.build_prompt_history(
                max_recent_messages=getattr(self.config, "max_recent_messages", 12)
            )
            messages = self.context.build_messages(history, message.content)
            browser_mode = self.context.resolve_browser_mode(message.content)
            reply, trace = await self.run_traced(
                message.content,
                messages,
                browser_mode,
                session_key=message.session_key,
                requester_sender_id=message.sender_id,
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

    def _save_message_result(self, message, reply, trace):
        session = self.sessions.get_or_create(message.session_key)
        session.messages.extend([
            {"role": "user", "content": message.content, "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": reply, "timestamp": datetime.now().isoformat()},
        ])
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
        task_id: str | None = None,
        browser_snapshot: str = "",
        loaded_skills: set[str] | None = None,
        browser_initialized: bool = False,
        browser_state: BrowserTaskState | dict | None = None,
        requester_sender_id: str | None = None,
    ) -> tuple[str, AgentRunTrace]:
        """Run the existing ReAct loop and return its completed in-memory trace."""
        supplied_metadata = dict(metadata or {})
        effective_task_id = (
            task_id
            or str(supplied_metadata.get("task_id", "")).strip()
            or uuid.uuid4().hex
        )
        run_metadata = {
            "browser_mode": browser_mode,
            "model": self.config.model,
            "provider": getattr(self.config, "provider", ""),
            "task_id": effective_task_id,
        }
        run_metadata.update(supplied_metadata)
        run_metadata["task_id"] = effective_task_id
        task_state = self._task_state(
            effective_task_id,
            session_key,
            requester_sender_id,
        )
        self._start_or_resume_task(task_state)
        run_metadata["task_status_at_start"] = task_state.status.value
        self.tracer.start_run(
            user_input,
            metadata=run_metadata,
        )
        task_browser_state = (
            browser_state
            if isinstance(browser_state, BrowserTaskState)
            else BrowserTaskState.from_dict(browser_state)
        )
        if browser_snapshot and not task_browser_state.latest_snapshot:
            task_browser_state.latest_snapshot = browser_snapshot
        task_browser_state.browser_initialized = (
            task_browser_state.browser_initialized or browser_initialized
        )
        task_loaded_skills = loaded_skills if loaded_skills is not None else set()
        try:
            output, status, error = await self._react_loop_outcome(
                messages,
                browser_mode,
                user_input=user_input,
                session_key=session_key,
                browser_snapshot=browser_snapshot,
                task_id=effective_task_id,
                loaded_skills=task_loaded_skills,
                browser_initialized=browser_initialized,
                browser_state=task_browser_state,
                requester_sender_id=requester_sender_id,
                task_state=task_state,
            )
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            if task_state.status not in {
                AgentTaskStatus.FAILED,
                AgentTaskStatus.COMPLETED,
                AgentTaskStatus.MAX_STEPS,
                AgentTaskStatus.CANCELLED,
            }:
                task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason="runtime_exception",
                )
            self._finish_run_for_task(
                task_state,
                runtime_status="failed",
                error=error,
            )
            raise
        trace = self._finish_run_for_task(
            task_state,
            final_output=output,
            runtime_status=status,
            error=error,
        )
        self._remember_browser_task(
            session_key=session_key,
            task_id=effective_task_id,
            trace=trace,
            browser_mode=browser_mode,
            messages=messages,
            output=output,
            browser_snapshot=browser_snapshot,
            loaded_skills=task_loaded_skills,
            browser_state=task_browser_state,
        )
        return output, trace

    def _remember_browser_task(
        self,
        *,
        session_key: str,
        task_id: str,
        trace: AgentRunTrace,
        browser_mode: str,
        messages: list[dict],
        output: str,
        browser_snapshot: str,
        loaded_skills: set[str],
        browser_state: BrowserTaskState,
    ) -> None:
        if not session_key or not browser_state.browser_used:
            return
        recent = RecentBrowserTask(
            session_key=session_key,
            task_id=task_id,
            origin_run_id=trace.run_id,
            browser_mode=browser_mode,
            messages=[
                *copy.deepcopy(messages),
                {"role": "assistant", "content": output},
            ],
            browser_snapshot=(
                browser_state.latest_snapshot or browser_snapshot
            ),
            loaded_skills=sorted(loaded_skills),
            browser_initialized=browser_state.browser_initialized,
            browser_state=browser_state.to_dict(),
        )
        self.recent_tasks.save(recent)
        if self.checkpoint_store is not None:
            self.checkpoint_store.save_recent(recent)

    async def _resume_recent_task(
        self,
        recent: RecentBrowserTask,
        user_input: str,
        requester_sender_id: str | None = None,
    ) -> tuple[str, AgentRunTrace]:
        messages = copy.deepcopy(recent.messages)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{user_input}\n\n"
                    "Runtime continuation: this corrects or continues the recent "
                    "browser task. Reuse its task_id, loaded Skills, recent tool "
                    "results, completion state, and budgets. "
                    + (
                        "This task was recovered after restart: persisted browser "
                        "state is historical only. Reinitialize/reconnect as needed "
                        "and read fresh browser state before acting. "
                        if recent.recovered_from_checkpoint
                        else "Reuse its browser session, current page, and latest snapshot. "
                    )
                    + "This is not approval for any risky action; "
                    "all new tool calls still require normal policy evaluation."
                ),
            }
        )
        return await self.run_traced(
            user_input,
            messages,
            recent.browser_mode,
            session_key=recent.session_key,
            metadata={
                "resumed_from_run_id": recent.origin_run_id,
                "continuation": True,
                "continuation_kind": "recent_task_correction",
            },
            task_id=recent.task_id,
            browser_snapshot=recent.browser_snapshot,
            loaded_skills=set(recent.loaded_skills),
            browser_initialized=recent.browser_initialized,
            browser_state=recent.browser_state,
            requester_sender_id=requester_sender_id,
        )

    async def resume_recent_task(
        self,
        session_key: str,
        user_input: str,
        requester_sender_id: str | None = None,
    ) -> tuple[str, AgentRunTrace]:
        """Resume the most recent browser task without implying approval."""
        recent = self.recent_tasks.get(session_key)
        if recent is None:
            self.tracer.start_run(
                user_input,
                metadata={
                    "session_key": session_key,
                    "task_id": uuid.uuid4().hex,
                },
            )
            output = "当前会话没有可继续的浏览器任务。"
            return output, self.tracer.finish_run(
                final_output=output,
                status="cancelled",
            )
        return await self._resume_recent_task(
            recent,
            user_input,
            requester_sender_id=requester_sender_id,
        )

    def _cancelled_trace(
        self,
        pending: PendingApproval,
        user_input: str,
    ) -> tuple[str, AgentRunTrace]:
        task_id = pending.task_id or uuid.uuid4().hex
        task_state = self._task_state(
            task_id,
            pending.session_key,
            pending.requester_sender_id,
        )
        if task_state.status == AgentTaskStatus.NEW:
            task_state.transition(AgentTaskStatus.RUNNING)
        task_state.transition(
            AgentTaskStatus.CANCELLED,
            reason="approval_rejected",
        )
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": pending.browser_mode,
                "approval_id": pending.approval_id,
                "approval_status": "rejected",
                "resumed_from_run_id": pending.origin_run_id,
                "task_id": task_id,
            },
        )
        output = (
            f"已取消操作：{pending.tool_name}。该工具没有执行。"
        )
        return output, self._finish_run_for_task(
            task_state,
            final_output=output,
            runtime_status="cancelled",
        )

    def _approval_authorization_mismatch_trace(
        self,
        pending: PendingApproval,
        user_input: str,
    ) -> tuple[str, AgentRunTrace]:
        task_id = pending.task_id or uuid.uuid4().hex
        task_state = self._task_state(
            task_id,
            pending.session_key,
            pending.requester_sender_id,
        )
        if task_state.status == AgentTaskStatus.NEW:
            task_state.transition(AgentTaskStatus.RUNNING)
            task_state.transition(
                AgentTaskStatus.WAITING_APPROVAL,
                reason="approval_required",
                approval_id=pending.approval_id,
            )
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": pending.browser_mode,
                "approval_id": pending.approval_id,
                "approval_status": "authorization_mismatch",
                "resumed_from_run_id": pending.origin_run_id,
                "task_id": task_id,
            },
        )
        output = "该待确认操作只能由原操作发起人确认。"
        return output, self._finish_run_for_task(
            task_state,
            final_output=output,
            runtime_status="cancelled",
        )

    def _checkpoint_consume_failed_trace(self, pending, user_input, *, kind="approval"):
        task_id = pending.task_id or uuid.uuid4().hex
        task_state = self._task_state(task_id, pending.session_key, pending.requester_sender_id)
        if task_state.status == AgentTaskStatus.NEW:
            task_state.transition(AgentTaskStatus.RUNNING)
            if kind == "approval":
                task_state.transition(AgentTaskStatus.WAITING_APPROVAL, reason="approval_required", approval_id=pending.approval_id)
            else:
                task_state.transition(AgentTaskStatus.WAITING_CLARIFICATION, reason="clarification_required", clarification_id=pending.clarification_id)
        metadata = {"approval_status" if kind == "approval" else "clarification_status": "checkpoint_consume_failed", "task_id": task_id}
        self.tracer.start_run(user_input, metadata=metadata)
        output = "无法安全消费已持久化的继续请求，操作未恢复，请稍后重试。"
        return output, self._finish_run_for_task(task_state, final_output=output, runtime_status="failed", error="checkpoint consume failed")

    def _clarification_authorization_mismatch_trace(self, pending, user_input):
        task_id = pending.task_id or uuid.uuid4().hex
        task_state = self._task_state(task_id, pending.session_key, pending.requester_sender_id)
        self.tracer.start_run(user_input, metadata={"clarification_id": pending.clarification_id, "clarification_status": "authorization_mismatch", "task_id": task_id})
        output = "该澄清问题只能由原操作发起人回答。"
        return output, self._finish_run_for_task(task_state, final_output=output, runtime_status="cancelled")

    def _expired_approval_trace(
        self,
        pending: PendingApproval,
        user_input: str,
    ) -> tuple[str, AgentRunTrace]:
        task_id = pending.task_id or uuid.uuid4().hex
        task_state = self._task_state(
            task_id,
            pending.session_key,
            pending.requester_sender_id,
        )
        if task_state.status == AgentTaskStatus.NEW:
            task_state.transition(AgentTaskStatus.RUNNING)
        task_state.transition(
            AgentTaskStatus.FAILED,
            reason="approval_expired",
        )
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": pending.browser_mode,
                "approval_id": pending.approval_id,
                "approval_status": "expired",
                "resumed_from_run_id": pending.origin_run_id,
                "task_id": task_id,
            },
        )
        output = "该确认请求已经过期，请重新发起操作。"
        return output, self._finish_run_for_task(
            task_state,
            final_output=output,
            runtime_status="cancelled",
        )

    async def resume_pending(
        self,
        session_key: str,
        user_input: str,
        sender_id: str | None = None,
    ) -> tuple[str, AgentRunTrace]:
        """Deterministically approve, reject, or replace one pending action."""
        intent = classify_approval_intent(user_input)
        expired = self.approvals.expire(session_key)
        if expired is not None:
            return self._expired_approval_trace(expired, user_input)
        pending = self.approvals.get(session_key)
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
            if not self._consume_durable_approval(session_key):
                return self._checkpoint_consume_failed_trace(pending, user_input)
            approved = self.approvals.approve(
                session_key,
                pending.approval_id,
                sender_id,
            )
            if approved is None:
                return self._approval_authorization_mismatch_trace(
                    pending,
                    user_input,
                )
            self._clear_active_checkpoint(session_key)
            return await self._resume_approved(
                approved,
                user_input,
                sender_id,
            )
        rejected = self.approvals.reject(
            session_key,
            pending.approval_id,
            sender_id,
        )
        if rejected is None:
            return self._approval_authorization_mismatch_trace(
                pending,
                user_input,
            )
        self._clear_active_checkpoint(session_key)
        return self._cancelled_trace(rejected, user_input)

    async def resume_clarification(
        self,
        session_key: str,
        user_input: str,
        sender_id: str | None = None,
    ) -> tuple[str, AgentRunTrace]:
        """Resume one ordinary question without rebuilding task context."""
        pending = self.clarifications.get(session_key)
        if pending is None:
            self.tracer.start_run(
                user_input,
                metadata={
                    "session_key": session_key,
                    "task_id": uuid.uuid4().hex,
                },
            )
            output = "当前会话没有等待回答的澄清问题。"
            return output, self.tracer.finish_run(
                final_output=output,
                status="cancelled",
            )
        if (
            pending.requester_sender_id is not None
            and sender_id is not None
            and pending.requester_sender_id != sender_id
        ):
            return self._clarification_authorization_mismatch_trace(pending, user_input)
        if not self._consume_durable_active(session_key):
            return self._checkpoint_consume_failed_trace(
                pending, user_input, kind="clarification"
            )
        resolved = self.clarifications.resolve(
            session_key,
            pending.clarification_id,
            sender_id,
        )
        if resolved is None:
            return self._clarification_authorization_mismatch_trace(pending, user_input)
        self._clear_active_checkpoint(session_key)
        return await self._resume_clarification(resolved, user_input)

    async def _resume_clarification(
        self,
        pending: PendingClarification,
        user_input: str,
    ) -> tuple[str, AgentRunTrace]:
        self._clear_active_checkpoint(pending.session_key)
        browser_mode = pending.browser_mode or BROWSER_MODE_MANAGED
        task_id = pending.task_id or uuid.uuid4().hex
        task_state = self._task_state(
            task_id,
            pending.session_key,
            pending.requester_sender_id,
        )
        self._start_or_resume_task(task_state)
        loaded_skills = set(pending.loaded_skills)
        browser_state = BrowserTaskState.from_dict(pending.browser_state)
        browser_state.browser_initialized = (
            browser_state.browser_initialized or pending.browser_initialized
        )
        if pending.browser_snapshot and not browser_state.latest_snapshot:
            browser_state.latest_snapshot = pending.browser_snapshot
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": browser_mode,
                "browser_session": pending.browser_session,
                "model": self.config.model,
                "provider": getattr(self.config, "provider", ""),
                "resumed_from_run_id": pending.origin_run_id,
                "clarification_id": pending.clarification_id,
                "clarification_status": "answered",
                "task_id": task_id,
                "task_status_at_start": task_state.status.value,
            },
        )
        messages = copy.deepcopy(pending.messages)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": pending.model_tool_call_id,
                "content": (
                    "User answered the clarification question.\n"
                    f"Question: {pending.question}\n"
                    f"Answer: {user_input}\n"
                    "Continue the original task using the prior Skill instructions."
                    + (
                        " This clarification was recovered after restart; persisted "
                        "browser state is historical only. Reinitialize/reconnect "
                        "as needed and read fresh browser state before acting."
                        if pending.recovered_from_checkpoint
                        else " Reuse the preserved browser session."
                    )
                ),
            }
        )
        for serialized_call in pending.remaining_tool_calls:
            stale_call = self._deserialize_tool_call(serialized_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": stale_call.id,
                    "content": (
                        "Skipped: this tool call was proposed before the user "
                        "answered the clarification. Re-evaluate it now."
                    ),
                }
            )

        try:
            output, status, error = await self._react_loop_outcome(
                messages,
                browser_mode,
                user_input=user_input,
                session_key=pending.session_key,
                browser_snapshot=pending.browser_snapshot,
                task_id=task_id,
                loaded_skills=loaded_skills,
                browser_initialized=pending.browser_initialized,
                browser_state=browser_state,
                requester_sender_id=pending.requester_sender_id,
                task_state=task_state,
            )
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            if task_state.status not in {
                AgentTaskStatus.FAILED,
                AgentTaskStatus.COMPLETED,
                AgentTaskStatus.MAX_STEPS,
                AgentTaskStatus.CANCELLED,
            }:
                task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason="clarification_resume_exception",
                )
            self._finish_run_for_task(
                task_state,
                runtime_status="failed",
                error=error,
            )
            raise
        trace = self._finish_run_for_task(
            task_state,
            final_output=output,
            runtime_status=status,
            error=error,
        )
        self._remember_browser_task(
            session_key=pending.session_key,
            task_id=task_id,
            trace=trace,
            browser_mode=browser_mode,
            messages=messages,
            output=output,
            browser_snapshot=pending.browser_snapshot,
            loaded_skills=loaded_skills,
            browser_state=browser_state,
        )
        return output, trace

    @staticmethod
    def _approval_action_preview(pending: PendingApproval) -> str:
        arguments = redact_tool_arguments(
            pending.tool_name,
            pending.arguments,
        )
        if pending.tool_name == "exec":
            command = redact_text(str(arguments.get("command", "")))
            return f"Arguments:\n  command: {command}"
        if pending.tool_name == "browser_click":
            lines = [f"Target: {arguments.get('target', '')}"]
            target_text = pending.policy_metadata.get("target_text")
            current_url = pending.policy_metadata.get("current_url")
            if target_text:
                lines.append(f"Target text: {redact_text(str(target_text))}")
            if current_url:
                lines.append(f"Current URL: {redact_text(str(current_url))}")
            return "\n".join(lines)
        if pending.tool_name == "browser_type":
            return "\n".join(
                [
                    f"Target: {arguments.get('target', '')}",
                    f"Submit: {bool(arguments.get('submit', False))}",
                    f"Text: {REDACTED}",
                ]
            )
        if pending.tool_name == "write_file":
            return f"Path: {arguments.get('path', '')}"
        serialized = json.dumps(
            arguments,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return f"Arguments:\n{serialized}"

    @classmethod
    def _approval_prompt(cls, pending: PendingApproval) -> str:
        return (
            "准备执行需要确认的操作：\n\n"
            f"Tool: {pending.tool_name}\n"
            f"Risk: {pending.risk_level.value}\n"
            f"Reason: {pending.reason}\n"
            f"{cls._approval_action_preview(pending)}\n"
            f"Approval ID: {pending.approval_id}\n\n"
            "是否继续？回复“确认”继续，回复“取消”放弃。"
        )

    def _create_clarification(
        self,
        *,
        session_key: str,
        question: str,
        tool_call,
        browser_mode: str,
        messages: list[dict],
        remaining_tool_calls: list,
        browser_snapshot: str,
        task_id: str,
        loaded_skills: set[str],
        browser_initialized: bool,
        browser_state: BrowserTaskState,
        requester_sender_id: str | None,
    ) -> PendingClarification:
        current_run = self.tracer.get_current_run()
        effective_session_key = session_key or (
            f"run:{current_run.run_id}" if current_run else "run:untraced"
        )
        return self.clarifications.create(
            session_key=effective_session_key,
            question=question,
            requester_sender_id=requester_sender_id,
            origin_run_id=current_run.run_id if current_run else None,
            task_id=task_id,
            browser_mode=browser_mode,
            browser_session=_BROWSER_SESSION_BY_MODE[browser_mode],
            model_tool_call_id=tool_call.id,
            messages=messages,
            remaining_tool_calls=[
                self._serialize_tool_call(item) for item in remaining_tool_calls
            ],
            browser_snapshot=browser_snapshot,
            loaded_skills=sorted(loaded_skills),
            browser_initialized=browser_initialized,
            browser_state=browser_state.to_dict(),
        )

    async def _resume_approved(
        self,
        pending: PendingApproval,
        user_input: str,
        sender_id: str | None = None,
    ) -> tuple[str, AgentRunTrace]:
        self._clear_active_checkpoint(pending.session_key)
        browser_mode = pending.browser_mode or BROWSER_MODE_MANAGED
        task_id = pending.task_id or uuid.uuid4().hex
        task_state = self._task_state(
            task_id,
            pending.session_key,
            pending.requester_sender_id,
        )
        self._start_or_resume_task(task_state)
        browser_state = BrowserTaskState.from_dict(pending.browser_state)
        browser_state.browser_initialized = (
            browser_state.browser_initialized or pending.browser_initialized
        )
        if pending.browser_snapshot and not browser_state.latest_snapshot:
            browser_state.latest_snapshot = pending.browser_snapshot
        execution_context = self._execution_context(
            browser_mode=browser_mode,
            browser_snapshot=pending.browser_snapshot,
            loaded_skills=set(pending.loaded_skills),
            browser_initialized=pending.browser_initialized,
            browser_state=browser_state,
        )
        self.tracer.start_run(
            user_input,
            metadata={
                "browser_mode": browser_mode,
                "model": self.config.model,
                "provider": getattr(self.config, "provider", ""),
                "resumed_from_run_id": pending.origin_run_id,
                "approval_id": pending.approval_id,
                "approval_status": "approved",
                "task_id": task_id,
                "task_status_at_start": task_state.status.value,
            },
        )
        messages = copy.deepcopy(pending.messages)
        step_trace = self.tracer.start_step(1)
        approved_request = ToolExecutionRequest(
            tool_name=pending.tool_name,
            arguments=pending.arguments,
            session_key=pending.session_key,
            sender_id=sender_id,
            task_id=task_id,
            model_tool_call_id=pending.model_tool_call_id,
            user_input=user_input,
            step_id=step_trace.step_id,
            messages=messages,
            remaining_tool_calls=pending.remaining_tool_calls,
        )
        try:
            approved_outcome = await self._pipeline().execute_approved(
                pending,
                approved_request,
                execution_context,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": pending.model_tool_call_id,
                    "content": approved_outcome.tool_result.to_text(),
                }
            )
            self._sync_verification_task_state(task_state, execution_context)
            if approved_outcome.status in {
                ToolExecutionStatus.FAILED,
                ToolExecutionStatus.BLOCKED,
            }:
                error = (
                    approved_outcome.tool_result.error
                    or "Approved action failed runtime precondition validation."
                )
                task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason="approval_precondition_failed",
                )
                self.tracer.finish_step(status="failed", error=error)
                output = approved_outcome.tool_result.to_text()
                trace = self._finish_run_for_task(
                    task_state,
                    final_output=output,
                    runtime_status="failed",
                    error=error,
                )
                return output, trace
            if pending.recovered_from_checkpoint:
                for serialized_call in pending.remaining_tool_calls:
                    stale_call = self._deserialize_tool_call(serialized_call)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": stale_call.id,
                            "content": (
                                "Skipped after restart: this unapproved batched "
                                "tool call was not replayed. Re-evaluate it now."
                            ),
                        }
                    )
                remaining = []
            else:
                remaining = [
                    self._deserialize_tool_call(value)
                    for value in pending.remaining_tool_calls
                ]
            pause_output, pause_status = await self._execute_tool_batch(
                remaining,
                messages=messages,
                execution_context=execution_context,
                task_state=task_state,
                user_input=user_input,
                requester_sender_id=pending.requester_sender_id,
                step_id=step_trace.step_id,
            )
            if pause_status is not None:
                self.tracer.finish_step(status=pause_status)
                trace = self._finish_run_for_task(
                    task_state,
                    final_output=pause_output or "",
                    runtime_status=pause_status,
                )
                return pause_output or "", trace

            self.tracer.finish_step()
            output, status, error = await self._react_loop_outcome(
                messages,
                browser_mode,
                user_input=user_input,
                session_key=pending.session_key,
                browser_snapshot=execution_context.browser_snapshot,
                step_index_offset=1,
                task_id=task_id,
                loaded_skills=execution_context.loaded_skills,
                browser_initialized=execution_context.browser_initialized,
                browser_state=execution_context.browser_state,
                requester_sender_id=pending.requester_sender_id,
                task_state=task_state,
            )
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            if task_state.status not in {
                AgentTaskStatus.FAILED,
                AgentTaskStatus.COMPLETED,
                AgentTaskStatus.MAX_STEPS,
                AgentTaskStatus.CANCELLED,
            }:
                task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason="approval_resume_exception",
                )
            self._finish_run_for_task(
                task_state,
                runtime_status="failed",
                error=error,
            )
            raise

        trace = self._finish_run_for_task(
            task_state,
            final_output=output,
            runtime_status=status,
            error=error,
        )
        self._remember_browser_task(
            session_key=pending.session_key,
            task_id=task_id,
            trace=trace,
            browser_mode=browser_mode,
            messages=messages,
            output=output,
            browser_snapshot=execution_context.browser_snapshot,
            loaded_skills=execution_context.loaded_skills,
            browser_state=execution_context.browser_state,
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
        task_id: str = "",
        loaded_skills: set[str] | None = None,
        browser_initialized: bool = False,
        browser_state: BrowserTaskState | None = None,
        requester_sender_id: str | None = None,
        task_state: AgentTaskState | None = None,
    ) -> tuple[str, str, str | None]:
        current_run = self.tracer.get_current_run()
        effective_task_id = (
            task_id
            or str(
                current_run.metadata.get("task_id", "")
                if current_run
                else ""
            ).strip()
            or uuid.uuid4().hex
        )
        task_loaded_skills = (
            loaded_skills if loaded_skills is not None else set()
        )
        task_browser_state = browser_state or BrowserTaskState()
        effective_task_state = task_state or self._task_state(
            effective_task_id,
            session_key,
            requester_sender_id,
        )
        if effective_task_state.status in {
            AgentTaskStatus.NEW,
            AgentTaskStatus.WAITING_APPROVAL,
            AgentTaskStatus.WAITING_CLARIFICATION,
        }:
            self._start_or_resume_task(effective_task_state)
        task_browser_state.browser_initialized = (
            task_browser_state.browser_initialized or browser_initialized
        )
        if browser_snapshot and not task_browser_state.latest_snapshot:
            task_browser_state.latest_snapshot = browser_snapshot
        final_parts: list[str] = []
        rate_limit_retries = 0
        rate_limit_retry_limit = self._effective_rate_limit_retries()
        react_step_limit = self._effective_react_steps()
        empty_response_count = 0
        repeat_tracker: dict[str, object] = {
            "last_signature": "",
            "count": 0,
        }
        request_timeout = self._effective_request_timeout_seconds()
        for step in range(react_step_limit):
            step_index = step + 1 + step_index_offset
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
            model_messages = messages
            context_metadata = {}
            if hasattr(self.context, "prepare_messages"):
                model_messages, context_metadata = self.context.prepare_messages(
                    messages, task_anchor=user_input
                )
                if llm_trace:
                    llm_trace.metadata.update(context_metadata)
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.config.model,
                        messages=model_messages,
                        tools=tool_definitions or None,
                        temperature=0.1,
                        max_tokens=self.config.max_completion_tokens,
                    ),
                    timeout=request_timeout,
                )
            except (TimeoutError, APITimeoutError):
                error = self._timeout_error(request_timeout)
                if llm_trace:
                    self.tracer.finish_llm_call(llm_trace, error=error)
                if step_trace:
                    self.tracer.finish_step(status="failed", error=error)
                effective_task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason="llm_timeout",
                )
                return error, "failed", error
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
                effective_task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason="llm_error",
                )
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
                    completion_block = task_browser_state.completion_block_reason()
                    if completion_block:
                        current_run = self.tracer.get_current_run()
                        claimed_success = contains_success_claim(content)
                        if current_run:
                            current_run.metadata.update(
                                {
                                    "browser_completion_state": (
                                        task_browser_state.completion_state
                                    ),
                                    "completion_claim_blocked": claimed_success,
                                }
                            )
                        if contains_incomplete_report(content):
                            final_parts.append(content)
                            if step_trace:
                                self.tracer.finish_step()
                            if (
                                effective_task_state.status
                                == AgentTaskStatus.RUNNING
                            ):
                                effective_task_state.transition(
                                    AgentTaskStatus.WAITING_VERIFICATION,
                                    reason="browser_task_reported_incomplete",
                                )
                            return "".join(final_parts).strip(), "success", None
                        if (
                            task_browser_state.completion_gate_prompts < 1
                            and step + 1 < react_step_limit
                        ):
                            task_browser_state.completion_gate_prompts += 1
                            messages.append(
                                {"role": "assistant", "content": content}
                            )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "Runtime completion gate: do not claim this "
                                        f"browser task succeeded. {completion_block} "
                                        "Use browser_verify with a concrete structured "
                                        "postcondition, perform one bounded recovery, or "
                                        "report that the task is incomplete."
                                    ),
                                }
                            )
                            if step_trace:
                                self.tracer.finish_step(
                                    status="completion_verification_required"
                                )
                            if (
                                effective_task_state.status
                                == AgentTaskStatus.RUNNING
                            ):
                                effective_task_state.transition(
                                    AgentTaskStatus.WAITING_VERIFICATION,
                                    reason="browser_postcondition_required",
                                )
                            continue
                        error = "Browser task completion was not verified"
                        output = (
                            "浏览器任务尚未完成："
                            + completion_block
                            + " Runtime 未取得可验证的任务完成证据。"
                        )
                        if step_trace:
                            self.tracer.finish_step(
                                status="failed",
                                error=error,
                            )
                        effective_task_state.transition(
                            AgentTaskStatus.FAILED,
                            reason="browser_verification_failed",
                        )
                        return output, "failed", error
                    final_parts.append(content)
                    current_run = self.tracer.get_current_run()
                    if current_run and task_browser_state.browser_used:
                        current_run.metadata.update(
                            {
                                "browser_completion_state": (
                                    task_browser_state.completion_state
                                ),
                                "completion_verified": (
                                    task_browser_state.completion_state == "verified"
                                ),
                                "completion_evidence": (
                                    task_browser_state.completion_evidence
                                ),
                            }
                        )
                    if step_trace:
                        self.tracer.finish_step()
                    effective_task_state.transition(
                        AgentTaskStatus.COMPLETED,
                        reason="model_final_response",
                    )
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
                effective_task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason="empty_model_response",
                )
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
                browser_mode=browser_mode,
                browser_snapshot=browser_snapshot,
                loaded_skills=task_loaded_skills,
                browser_initialized=browser_initialized,
                browser_state=task_browser_state,
            )
            pause_output, pause_status = await self._execute_tool_batch(
                list(message.tool_calls),
                messages=messages,
                execution_context=execution_context,
                task_state=effective_task_state,
                user_input=user_input,
                requester_sender_id=requester_sender_id,
                step_id=step_trace.step_id if step_trace else None,
                repeat_tracker=repeat_tracker,
            )
            browser_initialized = execution_context.browser_initialized
            browser_snapshot = execution_context.browser_snapshot
            if pause_status is not None:
                if step_trace:
                    self.tracer.finish_step(status=pause_status)
                return pause_output or "", pause_status, None
            if step_trace:
                self.tracer.finish_step()

        current_run = self.tracer.get_current_run()
        if current_run and task_browser_state.browser_used:
            current_run.metadata["browser_completion_state"] = (
                task_browser_state.completion_state
            )
        effective_task_state.transition(
            AgentTaskStatus.MAX_STEPS,
            reason="react_step_limit",
        )
        return (
            f"已达到单次任务的 {react_step_limit} 步执行上限，任务尚未正常结束。",
            "max_steps",
            None,
        )
