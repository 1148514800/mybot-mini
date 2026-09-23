from __future__ import annotations

import asyncio
import copy
import uuid
from datetime import datetime

from openai import AsyncOpenAI

from ..core.config import GatewayConfig
from ..core.concurrency import SessionExecutionCoordinator
from ..storage.session import SessionManager
from ..storage.checkpoints.store import ActiveTaskCheckpointStore
from ..tools import ToolRegistry, ToolResult
from ..tracing import (
    AgentRunTrace,
    AgentTracer,
    redact_text,
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
from .model_execution import ModelExecutor
from .artifact_results import externalize_tool_result
from .tool_calls import (
    tool_call_signature,
)
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
        sessions: SessionManager,
        tracer: AgentTracer | None = None,
        recent_tasks: RecentTaskManager | None = None,
        browser_recovery_policy: BrowserRecoveryPolicy | None = None,
        checkpoint_store: ActiveTaskCheckpointStore | None = None,
        artifact_store=None,
    ):
        self.client = client
        self.config = config
        self.tools = tools
        self.context = context
        self.sessions = sessions
        self.tracer = tracer or AgentTracer()
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
            self.tracer,
            self.browser_recovery_policy,
            debug_trace=self._trace,
        )
        self.checkpoint_store = checkpoint_store
        self.artifact_store = artifact_store
        if hasattr(self.context, "max_context_chars"):
            self.context.max_context_chars = getattr(config, "max_context_chars", self.context.max_context_chars)
            self.context.max_recent_messages = getattr(config, "max_recent_messages", self.context.max_recent_messages)
            self.context.max_tool_result_chars = getattr(config, "max_tool_result_chars", self.context.max_tool_result_chars)
        self.runtime = TaskRuntimeManager(
            recent_tasks=self.recent_tasks,
            checkpoint_store=self.checkpoint_store,
        )
        self.task_states = self.runtime.task_states
        self.runtime.restore()
        self.model_execution = ModelExecutor(
            client=self.client,
            config=self.config,
            context=self.context,
            tracer=self.tracer,
        )
        self.coordinator = SessionExecutionCoordinator(
            getattr(config, "max_concurrent_sessions", 4)
        )

    def _pipeline(self) -> ToolExecutionPipeline:
        """Keep injected test/runtime dependencies aligned with the pipeline."""
        self.tool_execution.tools = self.tools
        self.tool_execution.tracer = self.tracer
        self.tool_execution.browser_recovery_policy = self.browser_recovery_policy
        return self.tool_execution

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

    def _trace(self, message: str) -> None:
        if self.config.show_internal_process:
            print(f"[trace] {redact_text(message)}")

    def _model_tool_result_text(
        self,
        result: ToolResult,
        *,
        tool_name: str,
        arguments: dict,
        session_key: str,
        task_id: str | None,
    ) -> str:
        text, record = externalize_tool_result(
            result,
            tool_name=tool_name,
            arguments=arguments,
            session_key=session_key,
            task_id=task_id,
            store=self.artifact_store,
            enabled=getattr(self.config, "artifact_enabled", False),
            threshold_chars=getattr(self.config, "artifact_externalize_threshold_chars", 8000),
        )
        if record is not None:
            run = self.tracer.get_current_run()
            if run is not None and run.status == "running":
                run.metadata["artifact_count"] = int(run.metadata.get("artifact_count", 0)) + 1
                run.metadata["artifact_chars_externalized"] = int(run.metadata.get("artifact_chars_externalized", 0)) + record.original_chars
                if record.storage_truncated:
                    run.metadata["artifact_storage_truncated_count"] = int(run.metadata.get("artifact_storage_truncated_count", 0)) + 1
        return text

    def _effective_react_steps(self) -> int:
        return max(
            1,
            min(self.config.max_react_steps, MAX_REACT_STEPS_HARD_LIMIT),
        )

    def _effective_rate_limit_retries(self) -> int:
        """Compatibility access for callers that inspect configured limits."""
        return self.model_execution._effective_rate_limit_retries()

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

    def _execution_context(
        self,
        *,
        session_key: str = "",
        task_id: str | None = None,
        browser_mode: str,
        browser_snapshot: str,
        loaded_skills: set[str],
        browser_initialized: bool,
        browser_state: BrowserTaskState,
    ) -> ToolExecutionContext:
        return ToolExecutionContext(
            session_key=session_key,
            task_id=task_id,
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

            if task_state.status == AgentTaskStatus.WAITING_VERIFICATION:
                task_state.transition(
                    AgentTaskStatus.RUNNING,
                    reason="verification_action_started",
                )
            request = ToolExecutionRequest(
                tool_name=tool_call.function.name,
                arguments=tool_call.function.arguments or "{}",
                session_key=task_state.session_key,
                task_id=task_state.task_id,
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
                    "content": self._model_tool_result_text(
                        result,
                        tool_name=tool_call.function.name,
                        arguments=tool_call.function.arguments or {},
                        session_key=task_state.session_key,
                        task_id=task_state.task_id,
                    ),
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
        """Run the local CLI conversation until the user exits."""
        try:
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

        finally:
            await self.coordinator.shutdown()

    async def handle_inbound_message(
        self,
        user_input: str,
        *,
        session_key: str = "cli:direct",
        sender_id: str | None = "user",
    ) -> tuple[str, AgentRunTrace]:
        """Handle one user message and record it in the session history."""

        async def operation() -> tuple[str, AgentRunTrace]:
            recent = self.recent_tasks.get(session_key)
            if recent is not None and is_recent_task_continuation(user_input):
                return await self._resume_recent_task(
                    recent,
                    user_input,
                    requester_sender_id=sender_id,
                )
            session = self.sessions.get_or_create(session_key)
            history = session.build_prompt_history(
                max_recent_messages=getattr(self.config, "max_recent_messages", 12)
            )
            messages = self.context.build_messages(history, user_input)
            browser_mode = self.context.resolve_browser_mode(user_input)
            return await self.run_traced(
                user_input,
                messages,
                browser_mode,
                session_key=session_key,
                requester_sender_id=sender_id,
            )

        reply, trace = await self.coordinator.execute(session_key, operation)
        session = self.sessions.get_or_create(session_key)
        session.messages.append(
            {
                "role": "user",
                "content": user_input,
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
        task_state = self.runtime.task_state(
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
                    "all new tool calls still require normal validation."
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
        effective_task_state = task_state or self.runtime.task_state(
            effective_task_id,
            session_key,
            requester_sender_id,
        )
        if effective_task_state.status in {
            AgentTaskStatus.NEW,
        }:
            self._start_or_resume_task(effective_task_state)
        task_browser_state.browser_initialized = (
            task_browser_state.browser_initialized or browser_initialized
        )
        if browser_snapshot and not task_browser_state.latest_snapshot:
            task_browser_state.latest_snapshot = browser_snapshot
        final_parts: list[str] = []
        react_step_limit = self._effective_react_steps()
        empty_response_count = 0
        repeat_tracker: dict[str, object] = {
            "last_signature": "",
            "count": 0,
        }
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
                effective_task_state.transition(
                    AgentTaskStatus.FAILED,
                    reason=model_turn.error_reason or "llm_error",
                )
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
                session_key=effective_task_state.session_key,
                task_id=effective_task_id,
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
