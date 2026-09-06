from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ..guardrails import (
    ApprovalManager,
    PendingApproval,
    PolicyDecision,
    PolicyResult,
    ToolPolicy,
)
from ..tools import BrowserResult, ToolRegistry, ToolResult
from ..tools.browser.connection import LOCAL_BROWSER_SESSION
from ..tools.browser.errors import BrowserErrorType
from ..tools.browser.navigation import MANAGED_BROWSER_SESSION
from ..tracing import (
    AgentTracer,
    redact_mapping,
    redact_tool_arguments,
    redact_tool_text,
)
from .browser_reliability import (
    BrowserRecoveryPolicy,
    BrowserTaskBudget,
    BrowserTaskState,
)
from .context import BROWSER_MODE_LOCAL, BROWSER_MODE_MANAGED


_BROWSER_SESSION_BY_MODE = {
    BROWSER_MODE_LOCAL: LOCAL_BROWSER_SESSION,
    BROWSER_MODE_MANAGED: MANAGED_BROWSER_SESSION,
}

_PAGE_URL_PATTERN = re.compile(r"(?m)^- Page URL:\s*(.+?)\s*$")
_SUBMIT_KEYS = frozenset(
    {"enter", "return", "numpadenter", "space", "spacebar"}
)
_INPUT_ROLES = frozenset(
    {"combobox", "input", "searchbox", "spinbutton", "textbox", "textarea"}
)
_BROWSER_APPROVAL_ERROR = (
    "浏览器页面在确认期间发生了变化，原操作已失效，请重新发起操作。"
)
_BROWSER_APPROVAL_UNVERIFIABLE = (
    "无法验证当前浏览器状态，已取消执行已批准操作，请重新发起。"
)


class ToolExecutionStatus(str, Enum):
    EXECUTED = "executed"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(slots=True)
class ToolExecutionRequest:
    tool_name: str
    arguments: Any
    session_key: str = ""
    sender_id: str | None = None
    task_id: str | None = None
    model_tool_call_id: str | None = None
    user_input: str = ""
    step_id: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list, repr=False)
    remaining_tool_calls: list[dict[str, Any]] = field(
        default_factory=list,
        repr=False,
    )
    execution_guard: ToolResult | None = field(default=None, repr=False)


@dataclass(slots=True)
class ToolExecutionContext:
    session_key: str = ""
    task_id: str | None = None
    browser_mode: str = BROWSER_MODE_MANAGED
    browser_snapshot: str = ""
    loaded_skills: set[str] = field(default_factory=set)
    browser_initialized: bool = False
    browser_state: BrowserTaskState = field(default_factory=BrowserTaskState)
    browser_budget: BrowserTaskBudget = field(default_factory=BrowserTaskBudget)


@dataclass(slots=True)
class ToolExecutionOutcome:
    status: ToolExecutionStatus
    tool_name: str
    arguments: dict[str, Any]
    tool_result: ToolResult
    policy_result: PolicyResult | None = None
    pending_approval: PendingApproval | None = None
    tool_call_trace: Any = field(default=None, repr=False)


class ToolExecutionPipeline:
    """Single policy, execution, result, and trace boundary for tool calls."""

    def __init__(
        self,
        tools: ToolRegistry,
        policy: ToolPolicy,
        approvals: ApprovalManager,
        tracer: AgentTracer,
        browser_recovery_policy: BrowserRecoveryPolicy | None = None,
        *,
        debug_trace: Callable[[str], None] | None = None,
    ) -> None:
        self.tools = tools
        self.policy = policy
        self.approvals = approvals
        self.tracer = tracer
        self.browser_recovery_policy = (
            browser_recovery_policy or BrowserRecoveryPolicy()
        )
        self.debug_trace = debug_trace or (lambda message: None)

    async def execute(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
        *,
        approved: PendingApproval | None = None,
    ) -> ToolExecutionOutcome:
        name = str(request.tool_name).strip()
        arguments, normalization_error = self._normalize_arguments(
            name,
            request.arguments,
            context.browser_mode,
        )
        trace_arguments = arguments or self._arguments_for_trace(request.arguments)
        tool_trace = self._start_trace(
            request,
            name,
            trace_arguments,
            approved,
        )

        if normalization_error is not None:
            return self._finish(
                ToolExecutionStatus.FAILED,
                name,
                trace_arguments,
                normalization_error,
                tool_trace=tool_trace,
            )
        assert arguments is not None
        context.session_key = request.session_key
        context.task_id = request.task_id

        if not self._tool_exists(name):
            return self._finish(
                ToolExecutionStatus.FAILED,
                name,
                arguments,
                ToolResult(
                    success=False,
                    error=f"Unknown tool '{name}'",
                    metadata={"execution_error": "unknown_tool"},
                ),
                tool_trace=tool_trace,
            )

        validation_error = self._validate_arguments(name, arguments)
        if validation_error:
            return self._finish(
                ToolExecutionStatus.FAILED,
                name,
                arguments,
                ToolResult(
                    success=False,
                    error=f"Invalid arguments for tool '{name}': {validation_error}",
                    metadata={"execution_error": "invalid_arguments"},
                ),
                tool_trace=tool_trace,
            )

        policy = self.policy.evaluate(
            name,
            arguments,
            user_input=request.user_input,
            context={"browser_snapshot": context.browser_snapshot},
            tool_metadata=self._runtime_metadata(name),
        )
        policy_metadata = self.policy_metadata(policy)
        if tool_trace is not None:
            tool_trace.metadata.update(redact_mapping(policy_metadata))

        live_precondition_metadata: dict[str, Any] = {}
        if approved is not None:
            authorization_error = self._validate_approved_action(
                request,
                context,
                arguments,
                policy,
                approved,
            )
            if authorization_error:
                result = ToolResult(
                    success=False,
                    error=authorization_error,
                    metadata={
                        **policy_metadata,
                        "approval_id": approved.approval_id,
                        "approval_status": "precondition_failed",
                    },
                )
                return self._finish(
                    ToolExecutionStatus.FAILED,
                    name,
                    arguments,
                    result,
                    policy=policy,
                    tool_trace=tool_trace,
                )

            if self._requires_live_browser_precondition(name, arguments):
                precondition_error, precondition_reason = (
                    await self._validate_live_browser_precondition(
                        name,
                        arguments,
                        context,
                        approved,
                    )
                )
                live_precondition_metadata = {
                    "runtime_precondition_check": True,
                    "approval_id": approved.approval_id,
                    "precondition_type": "browser_live_state",
                    "precondition_result": (
                        "failed" if precondition_error else "passed"
                    ),
                    **(
                        {"precondition_reason": precondition_reason}
                        if precondition_reason
                        else {}
                    ),
                }
                if tool_trace is not None:
                    tool_trace.metadata.update(
                        redact_mapping(live_precondition_metadata)
                    )
                if precondition_error:
                    result = ToolResult(
                        success=False,
                        error=precondition_error,
                        metadata={
                            **policy_metadata,
                            **live_precondition_metadata,
                            "approval_status": "precondition_failed",
                        },
                    )
                    return self._finish(
                        ToolExecutionStatus.FAILED,
                        name,
                        arguments,
                        result,
                        policy=policy,
                        tool_trace=tool_trace,
                    )

                policy = self.policy.evaluate(
                    name,
                    arguments,
                    user_input=request.user_input,
                    context={"browser_snapshot": context.browser_snapshot},
                    tool_metadata=self._runtime_metadata(name),
                )
                policy_metadata = self.policy_metadata(policy)
                if tool_trace is not None:
                    tool_trace.metadata.update(redact_mapping(policy_metadata))
                policy_error = self._validate_approved_policy(policy, approved)
                if policy_error:
                    failed_metadata = {
                        **live_precondition_metadata,
                        "precondition_result": "failed",
                        "precondition_reason": "target_changed",
                    }
                    if tool_trace is not None:
                        tool_trace.metadata.update(redact_mapping(failed_metadata))
                    result = ToolResult(
                        success=False,
                        error=policy_error,
                        metadata={
                            **policy_metadata,
                            **failed_metadata,
                            "approval_status": "precondition_failed",
                        },
                    )
                    return self._finish(
                        ToolExecutionStatus.FAILED,
                        name,
                        arguments,
                        result,
                        policy=policy,
                        tool_trace=tool_trace,
                    )

        if policy.decision == PolicyDecision.BLOCK:
            result = ToolResult(
                success=False,
                error=f"Blocked by tool policy: {policy.reason}",
                metadata={
                    **policy_metadata,
                    **(
                        {
                            "error_type": BrowserErrorType.POLICY_BLOCKED.value,
                            "recoverable": False,
                        }
                        if name.startswith("browser_")
                        else {}
                    ),
                },
            )
            context.browser_state.note_result(name, arguments, result)
            return self._finish(
                ToolExecutionStatus.BLOCKED,
                name,
                arguments,
                result,
                policy=policy,
                tool_trace=tool_trace,
            )

        if approved is not None and not approved.resumable:
            result = ToolResult(
                success=False,
                error=(
                    "This approved action cannot be safely resumed after restart; "
                    "please submit it again."
                ),
                metadata={
                    **policy_metadata,
                    **live_precondition_metadata,
                    "approval_id": approved.approval_id,
                    "approval_status": "non_resumable",
                },
            )
            return self._finish(
                ToolExecutionStatus.FAILED,
                name,
                arguments,
                result,
                policy=policy,
                tool_trace=tool_trace,
            )

        if (
            policy.decision == PolicyDecision.REQUIRE_CONFIRMATION
            and approved is None
        ):
            pending = self._create_pending(request, context, arguments, policy)
            result = ToolResult(
                success=False,
                error="Awaiting user confirmation; tool was not executed.",
                metadata=self.policy_metadata(
                    policy,
                    approval_id=pending.approval_id,
                    approval_status="pending",
                ),
            )
            return self._finish(
                ToolExecutionStatus.WAITING_APPROVAL,
                name,
                arguments,
                result,
                policy=policy,
                pending=pending,
                tool_trace=tool_trace,
            )

        if tool_trace is not None and approved is not None:
            tool_trace.metadata.update(
                redact_mapping(
                    {
                        "approval_id": approved.approval_id,
                        "approval_status": "approved",
                    }
                )
            )

        if request.execution_guard is not None:
            return self._finish(
                ToolExecutionStatus.FAILED,
                name,
                arguments,
                request.execution_guard,
                policy=policy,
                tool_trace=tool_trace,
            )

        try:
            result = await self._execute_task_tool(name, arguments, context)
        except Exception as exc:
            result = ToolResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"execution_error": "pipeline_exception"},
            )
        if live_precondition_metadata:
            result.metadata.update(live_precondition_metadata)
        return self._finish(
            ToolExecutionStatus.EXECUTED,
            name,
            arguments,
            result,
            policy=policy,
            tool_trace=tool_trace,
        )

    async def execute_approved(
        self,
        pending: PendingApproval,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """Execute only the exact action frozen in a consumed approval."""
        frozen = ToolExecutionRequest(
            tool_name=pending.tool_name,
            arguments=copy.deepcopy(pending.arguments),
            session_key=request.session_key,
            sender_id=request.sender_id,
            task_id=request.task_id,
            model_tool_call_id=(
                request.model_tool_call_id or pending.model_tool_call_id
            ),
            user_input=request.user_input,
            step_id=request.step_id,
            messages=request.messages,
            remaining_tool_calls=request.remaining_tool_calls,
        )
        return await self.execute(frozen, context, approved=pending)

    def _create_pending(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
        arguments: dict[str, Any],
        policy: PolicyResult,
    ) -> PendingApproval:
        current_run = self.tracer.get_current_run()
        effective_session_key = request.session_key or (
            f"run:{current_run.run_id}" if current_run else "run:untraced"
        )
        return self.approvals.create(
            session_key=effective_session_key,
            tool_name=request.tool_name,
            arguments=arguments,
            policy=policy,
            requester_sender_id=request.sender_id,
            origin_run_id=current_run.run_id if current_run else None,
            browser_mode=context.browser_mode,
            model_tool_call_id=request.model_tool_call_id,
            messages=request.messages,
            remaining_tool_calls=request.remaining_tool_calls,
            browser_snapshot=context.browser_snapshot,
            task_id=request.task_id,
            loaded_skills=sorted(context.loaded_skills),
            browser_initialized=context.browser_initialized,
            browser_state=context.browser_state.to_dict(),
        )

    def _validate_approved_action(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
        arguments: dict[str, Any],
        policy: PolicyResult,
        pending: PendingApproval,
    ) -> str | None:
        if pending.status != "approved":
            return "Approval authorization is not in the approved state."
        if self.approvals.is_expired(pending):
            return "Approval authorization expired before execution."
        if request.session_key != pending.session_key:
            return "Approval session no longer matches the frozen action."
        if pending.task_id and request.task_id != pending.task_id:
            return "Approval task no longer matches the frozen action."
        if (
            pending.requester_sender_id is not None
            and request.sender_id != pending.requester_sender_id
        ):
            return "Approval requester no longer matches the frozen action."
        if request.tool_name != pending.tool_name or arguments != pending.arguments:
            return "Approval does not match the frozen tool call."
        if (
            pending.browser_mode
            and context.browser_mode != pending.browser_mode
        ):
            return "Browser mode changed after approval was requested."
        if context.browser_snapshot != pending.browser_snapshot:
            return "Browser snapshot changed after approval was requested."
        approved_url = str(pending.policy_metadata.get("current_url", ""))
        if (
            approved_url
            and context.browser_state.current_url
            and context.browser_state.current_url != approved_url
        ):
            return "Browser URL changed after approval was requested."
        return self._validate_approved_policy(policy, pending)

    @staticmethod
    def _validate_approved_policy(
        policy: PolicyResult,
        pending: PendingApproval,
    ) -> str | None:
        if (
            policy.decision == PolicyDecision.REQUIRE_CONFIRMATION
            and (
                policy.rule != pending.policy_rule
                or policy.risk_level != pending.risk_level
            )
        ):
            return "Tool policy changed after approval was requested."
        return None

    @staticmethod
    def _requires_live_browser_precondition(
        name: str,
        arguments: dict[str, Any],
    ) -> bool:
        if name in {"browser_click", "browser_eval"}:
            return True
        if name == "browser_type":
            return arguments.get("submit") is not False
        if name != "browser_press":
            return False
        key_parts = {
            part
            for part in re.split(
                r"[+\s]+",
                str(arguments.get("key", "")).strip().lower(),
            )
            if part
        }
        return bool(key_parts & _SUBMIT_KEYS)

    async def _validate_live_browser_precondition(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
        pending: PendingApproval,
    ) -> tuple[str | None, str | None]:
        refresh, refresh_trace = await self._refresh_approval_browser_state(
            context,
            pending,
        )
        if not refresh.success:
            reason = "snapshot_refresh_failed"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_UNVERIFIABLE, reason

        expected_session = _BROWSER_SESSION_BY_MODE[context.browser_mode]
        if (
            isinstance(refresh, BrowserResult)
            and refresh.session
            and refresh.session != expected_session
        ):
            reason = "browser_not_initialized"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_UNVERIFIABLE, reason

        approved_url = self._approval_url(pending)
        fresh_url = (
            refresh.url
            if isinstance(refresh, BrowserResult) and refresh.url
            else self._snapshot_url(refresh.output)
        )
        if not approved_url or not fresh_url:
            reason = "unsupported_precondition"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_UNVERIFIABLE, reason
        if fresh_url != approved_url:
            reason = "url_changed"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_ERROR, reason

        if name == "browser_eval":
            self._finish_precondition_trace(refresh_trace, "passed")
            return None, None

        if name == "browser_press":
            reason = "unsupported_precondition"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_UNVERIFIABLE, reason

        target = str(arguments.get("target", "")).strip()
        approved_target = self._snapshot_target_semantics(
            pending.browser_snapshot,
            target,
        )
        fresh_target = self._snapshot_target_semantics(refresh.output, target)
        if fresh_target is None:
            reason = "target_missing"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_ERROR, reason
        if approved_target is None:
            reason = "unsupported_precondition"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_UNVERIFIABLE, reason

        approved_role, approved_semantics = approved_target
        fresh_role, fresh_semantics = fresh_target
        if name == "browser_type" and (
            approved_role not in _INPUT_ROLES or fresh_role not in _INPUT_ROLES
        ):
            reason = "target_changed"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_ERROR, reason
        if (
            fresh_role != approved_role
            or fresh_semantics != approved_semantics
        ):
            reason = "target_changed"
            self._finish_precondition_trace(refresh_trace, "failed", reason)
            return _BROWSER_APPROVAL_ERROR, reason

        self._finish_precondition_trace(refresh_trace, "passed")
        return None, None

    async def _refresh_approval_browser_state(
        self,
        context: ToolExecutionContext,
        pending: PendingApproval,
    ) -> tuple[ToolResult, Any]:
        refresh_arguments = {
            "session": _BROWSER_SESSION_BY_MODE[context.browser_mode]
        }
        current_step = self.tracer.get_current_step()
        refresh_trace = (
            self.tracer.start_tool_call(
                step_id=current_step.step_id,
                tool_name="browser_snapshot",
                arguments=refresh_arguments,
                metadata={
                    "runtime_internal": True,
                    "runtime_precondition_check": True,
                    "approval_id": pending.approval_id,
                    "precondition_type": "browser_live_state",
                },
            )
            if current_step is not None and self._tracing_active()
            else None
        )
        try:
            refresh = await self._execute_registry(
                "browser_snapshot",
                refresh_arguments,
                session_key=context.session_key,
                task_id=context.task_id,
            )
        except Exception as exc:
            refresh = ToolResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"execution_error": "snapshot_refresh_exception"},
            )
        if refresh_trace is not None:
            self.tracer.finish_tool_call(refresh_trace, result=refresh)
        context.browser_state.note_result(
            "browser_snapshot",
            refresh_arguments,
            refresh,
        )
        self._record_task_result(
            "browser_snapshot",
            refresh_arguments,
            refresh,
            context,
        )
        fresh_url = (
            refresh.url
            if isinstance(refresh, BrowserResult) and refresh.url
            else self._snapshot_url(refresh.output)
        )
        if refresh.success and fresh_url:
            context.browser_state.current_url = fresh_url
        return refresh, refresh_trace

    @staticmethod
    def _finish_precondition_trace(
        trace: Any,
        result: str,
        reason: str | None = None,
    ) -> None:
        if trace is None:
            return
        trace.metadata["precondition_result"] = result
        if reason:
            trace.metadata["precondition_reason"] = reason

    @classmethod
    def _approval_url(cls, pending: PendingApproval) -> str:
        return (
            str(pending.policy_metadata.get("current_url", "")).strip()
            or str(pending.browser_state.get("current_url", "")).strip()
            or cls._snapshot_url(pending.browser_snapshot)
        )

    @staticmethod
    def _snapshot_url(snapshot: str) -> str:
        match = _PAGE_URL_PATTERN.search(snapshot or "")
        return match.group(1).strip() if match else ""

    @staticmethod
    def _snapshot_target_semantics(
        snapshot: str,
        target: str,
    ) -> tuple[str, str] | None:
        if not snapshot or not re.fullmatch(r"e\d+", target, re.I):
            return None
        ref_pattern = re.compile(
            rf"\[ref\s*=\s*['\"]?{re.escape(target)}['\"]?\]",
            re.I,
        )
        for line in snapshot.splitlines():
            match = ref_pattern.search(line)
            if not match:
                continue
            semantic_text = re.sub(
                r"\s+",
                " ",
                line[: match.start()].lstrip(" -*\t").strip(),
            ).casefold()
            if not semantic_text:
                return None
            role = semantic_text.split(" ", 1)[0]
            return role, semantic_text
        return None

    async def _execute_task_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        if (
            context.browser_initialized
            and name == self.browser_entry_tool(context.browser_mode)
        ):
            context.browser_state.browser_initialized = True
            return ToolResult(
                success=True,
                output=(
                    "Browser session is already initialized for this task; "
                    "reuse the existing session."
                ),
                metadata={"execution_skipped": "browser_already_initialized"},
            )

        skill_path = self.skill_path(name, arguments)
        if skill_path and skill_path in context.loaded_skills:
            return ToolResult(
                success=True,
                output=(
                    "This Skill was already loaded in this task. Reuse the "
                    "earlier SKILL.md instructions."
                ),
                metadata={
                    "execution_skipped": "skill_already_loaded",
                    "skill_cache_hit": True,
                    "skill_path": skill_path,
                },
            )

        budget_result = context.browser_state.preflight(
            name,
            arguments,
            context.browser_budget,
        )
        if budget_result is not None:
            context.browser_state.note_result(name, arguments, budget_result)
            return budget_result

        result = await self._execute_registry(
            name,
            arguments,
            session_key=context.session_key,
            task_id=context.task_id,
        )
        context.browser_state.note_result(name, arguments, result)
        self._record_task_result(name, arguments, result, context)

        recovery = self.browser_recovery_policy.plan(
            result,
            context.browser_state,
            context.browser_budget,
        )
        if recovery is not None:
            result.metadata.update(
                {
                    "recovery_hint": recovery.hint,
                    "recovery_retry_allowed": recovery.retry_allowed,
                }
            )
            if recovery.refresh_snapshot and context.browser_initialized:
                await self._refresh_recovery_snapshot(name, result, context)
        return result

    async def _refresh_recovery_snapshot(
        self,
        failed_tool: str,
        result: ToolResult,
        context: ToolExecutionContext,
    ) -> None:
        state = context.browser_state
        state.recovery_steps += 1
        state.pending_recovery_tool = failed_tool
        state.pending_recovery_retry_used = False
        refresh_arguments = {
            "session": _BROWSER_SESSION_BY_MODE[context.browser_mode]
        }
        current_step = self.tracer.get_current_step()
        recovery_trace = (
            self.tracer.start_tool_call(
                step_id=current_step.step_id,
                tool_name="browser_snapshot",
                arguments=refresh_arguments,
                metadata={
                    "runtime_recovery": True,
                    "recovery_for": failed_tool,
                    "recovery_step": state.recovery_steps,
                },
            )
            if current_step is not None and self._tracing_active()
            else None
        )
        refresh = await self._execute_registry(
            "browser_snapshot",
            refresh_arguments,
            session_key=context.session_key,
            task_id=context.task_id,
        )
        if recovery_trace is not None:
            self.tracer.finish_tool_call(recovery_trace, result=refresh)
        state.note_result("browser_snapshot", refresh_arguments, refresh)
        result.metadata.update(
            {
                "recovery_action": "browser_snapshot",
                "recovery_succeeded": refresh.success,
                "recovery_steps": state.recovery_steps,
            }
        )
        if refresh.success:
            state.browser_used = True
            context.browser_snapshot = refresh.output
            result.output = "\n\n".join(
                part
                for part in (
                    result.output,
                    "Runtime recovery snapshot:\n" + refresh.output,
                )
                if part
            )
        elif refresh.error:
            result.output = "\n\n".join(
                part
                for part in (
                    result.output,
                    "Runtime recovery snapshot failed: " + refresh.error,
                )
                if part
            )

    async def _execute_registry(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_key: str = "",
        task_id: str | None = None,
    ) -> ToolResult:
        safe_arguments = redact_tool_arguments(name, arguments)
        self.debug_trace(
            f"tool call name={name} args="
            f"{json.dumps(safe_arguments, ensure_ascii=False)}"
        )
        if isinstance(self.tools, ToolRegistry):
            result = await self.tools.execute(
                name,
                arguments,
                session_key=session_key,
                task_id=task_id,
            )
        else:
            result = await self.tools.execute(name, arguments)
        safe_result = {
            "success": result.success,
            "output": redact_tool_text(name, result.output, arguments),
            "error": (
                redact_tool_text(name, result.error, arguments)
                if result.error
                else None
            ),
            "metadata": redact_mapping(result.metadata),
        }
        preview = json.dumps(safe_result, ensure_ascii=False)[:300].replace(
            "\n",
            " ",
        )
        self.debug_trace(f"tool result name={name} result={preview}")
        return result

    def _record_task_result(
        self,
        name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        context: ToolExecutionContext,
    ) -> None:
        skill_path = self.skill_path(name, arguments)
        if result.success and skill_path:
            context.loaded_skills.add(skill_path)
            result.metadata.setdefault("skill_path", skill_path)
            result.metadata.setdefault("skill_loaded", True)
        if result.success and name == self.browser_entry_tool(
            context.browser_mode
        ):
            context.browser_initialized = True
        elif result.success and name == "browser_close":
            context.browser_initialized = False
        context.browser_state.browser_initialized = context.browser_initialized
        if name == "browser_snapshot" and result.success:
            context.browser_snapshot = result.output
        elif context.browser_state.latest_snapshot:
            context.browser_snapshot = context.browser_state.latest_snapshot

    def _normalize_arguments(
        self,
        name: str,
        raw_arguments: Any,
        browser_mode: str,
    ) -> tuple[dict[str, Any] | None, ToolResult | None]:
        if browser_mode == BROWSER_MODE_LOCAL and name == "browser_open":
            return None, ToolResult(
                success=False,
                error=(
                    "browser_open is blocked because the user explicitly "
                    "requested the local browser. Use browser_attach."
                ),
            )
        if browser_mode == BROWSER_MODE_MANAGED and name == "browser_attach":
            return None, ToolResult(
                success=False,
                error=(
                    "browser_attach is blocked because managed_browser is the "
                    "default for this request. Use browser_open."
                ),
            )

        if raw_arguments is None or raw_arguments == "":
            arguments: Any = {}
        elif isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                return None, ToolResult(
                    success=False,
                    error=f"Invalid arguments for tool '{name}': {exc}",
                    metadata={"execution_error": "invalid_arguments"},
                )
        else:
            arguments = copy.deepcopy(raw_arguments)
        if not isinstance(arguments, dict):
            return None, ToolResult(
                success=False,
                error=f"Arguments for tool '{name}' must be a JSON object.",
                metadata={"execution_error": "invalid_arguments"},
            )
        if name.startswith("browser_") and name not in {
            "browser_attach",
            "browser_open",
        }:
            arguments["session"] = _BROWSER_SESSION_BY_MODE[browser_mode]
        return arguments, None

    def _validate_arguments(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        schema = self._tool_parameters(name)
        if not schema:
            return None
        for required in schema.get("required", []):
            if required not in arguments:
                return f"missing required field '{required}'"
        properties = schema.get("properties", {})
        for key, value in arguments.items():
            rule = properties.get(key)
            if not isinstance(rule, dict):
                continue
            expected = rule.get("type")
            if expected and not self._matches_json_type(value, str(expected)):
                return f"field '{key}' must be {expected}"
            if "enum" in rule and value not in rule["enum"]:
                return f"field '{key}' must be one of {rule['enum']}"
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                if "minimum" in rule and value < rule["minimum"]:
                    return f"field '{key}' must be >= {rule['minimum']}"
                if "maximum" in rule and value > rule["maximum"]:
                    return f"field '{key}' must be <= {rule['maximum']}"
        return None

    @staticmethod
    def _matches_json_type(value: Any, expected: str) -> bool:
        if expected == "string":
            return isinstance(value, str)
        if expected == "boolean":
            return isinstance(value, bool)
        if expected == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected == "number":
            return (
                isinstance(value, (int, float)) and not isinstance(value, bool)
            )
        if expected == "object":
            return isinstance(value, dict)
        if expected == "array":
            return isinstance(value, list)
        if expected == "null":
            return value is None
        return True

    def _tool_exists(self, name: str) -> bool:
        checker = getattr(self.tools, "has_tool", None)
        if callable(checker):
            return bool(checker(name))
        return any(
            item.get("function", {}).get("name") == name
            for item in self.tools.get_definitions()
        )

    def _tool_parameters(self, name: str) -> dict[str, Any]:
        getter = getattr(self.tools, "get_parameters", None)
        if callable(getter):
            value = getter(name)
            return dict(value) if isinstance(value, dict) else {}
        for item in self.tools.get_definitions():
            function = item.get("function", {})
            if function.get("name") == name:
                parameters = function.get("parameters", {})
                return dict(parameters) if isinstance(parameters, dict) else {}
        return {}

    def _runtime_metadata(self, name: str) -> dict[str, Any]:
        getter = getattr(self.tools, "get_runtime_metadata", None)
        if not callable(getter):
            return {}
        metadata = getter(name)
        return dict(metadata) if isinstance(metadata, dict) else {}

    def _start_trace(
        self,
        request: ToolExecutionRequest,
        name: str,
        arguments: dict[str, Any],
        approved: PendingApproval | None,
    ):
        if not request.step_id or not self._tracing_active():
            return None
        metadata = {
            "model_tool_call_id": request.model_tool_call_id,
            **self._runtime_metadata(name),
        }
        if approved is not None:
            metadata.update(
                {
                    "approval_id": approved.approval_id,
                    "approval_status": "approved",
                }
            )
        return self.tracer.start_tool_call(
            step_id=request.step_id,
            tool_name=name,
            arguments=arguments,
            metadata=metadata,
        )

    def _finish(
        self,
        status: ToolExecutionStatus,
        name: str,
        arguments: dict[str, Any],
        result: ToolResult,
        *,
        policy: PolicyResult | None = None,
        pending: PendingApproval | None = None,
        tool_trace=None,
    ) -> ToolExecutionOutcome:
        if tool_trace is not None:
            self.tracer.finish_tool_call(tool_trace, result=result)
        return ToolExecutionOutcome(
            status=status,
            tool_name=name,
            arguments=arguments,
            tool_result=result,
            policy_result=policy,
            pending_approval=pending,
            tool_call_trace=tool_trace,
        )

    def _tracing_active(self) -> bool:
        run = self.tracer.get_current_run()
        return run is not None and run.status == "running"

    @staticmethod
    def _arguments_for_trace(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError):
                return {"arguments_parse_error": True}
            if isinstance(parsed, dict):
                return parsed
            return {"arguments_type": type(parsed).__name__}
        return {"arguments_type": type(raw_arguments).__name__}

    @staticmethod
    def skill_path(name: str, arguments: dict[str, Any]) -> str | None:
        if name != "read_file":
            return None
        path = str(arguments.get("path", "")).strip().replace("\\", "/")
        if not path or path.rsplit("/", 1)[-1].lower() != "skill.md":
            return None
        return path.lower()

    @staticmethod
    def browser_entry_tool(browser_mode: str) -> str:
        return (
            "browser_attach"
            if browser_mode == BROWSER_MODE_LOCAL
            else "browser_open"
        )

    @staticmethod
    def policy_metadata(
        policy: PolicyResult,
        *,
        approval_id: str | None = None,
        approval_status: str | None = None,
    ) -> dict[str, Any]:
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
        return {
            key: value for key, value in metadata.items() if value is not None
        }
