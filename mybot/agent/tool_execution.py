from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ..tools import ToolRegistry, ToolResult
from ..tools.browser.connection import LOCAL_BROWSER_SESSION
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

class ToolExecutionStatus(str, Enum):
    EXECUTED = "executed"
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
    tool_call_trace: Any = field(default=None, repr=False)


class ToolExecutionPipeline:
    """Single execution, result, and trace boundary for tool calls."""

    def __init__(
        self,
        tools: ToolRegistry,
        tracer: AgentTracer,
        browser_recovery_policy: BrowserRecoveryPolicy | None = None,
        *,
        debug_trace: Callable[[str], None] | None = None,
    ) -> None:
        self.tools = tools
        self.tracer = tracer
        self.browser_recovery_policy = (
            browser_recovery_policy or BrowserRecoveryPolicy()
        )
        self.debug_trace = debug_trace or (lambda message: None)

    async def execute(
        self,
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
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

        if request.execution_guard is not None:
            return self._finish(
                ToolExecutionStatus.FAILED,
                name,
                arguments,
                request.execution_guard,
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
        return self._finish(
            ToolExecutionStatus.EXECUTED,
            name,
            arguments,
            result,
            tool_trace=tool_trace,
        )

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
    ):
        if not request.step_id or not self._tracing_active():
            return None
        metadata = {
            "model_tool_call_id": request.model_tool_call_id,
            **self._runtime_metadata(name),
        }
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
        tool_trace=None,
    ) -> ToolExecutionOutcome:
        if tool_trace is not None:
            self.tracer.finish_tool_call(tool_trace, result=result)
        return ToolExecutionOutcome(
            status=status,
            tool_name=name,
            arguments=arguments,
            tool_result=result,
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
