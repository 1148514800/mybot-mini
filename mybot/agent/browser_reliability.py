from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..tools.result import BrowserResult, ToolResult
from ..tools.browser.errors import BrowserErrorType


DEFAULT_MAX_CONSECUTIVE_TOOL_FAILURES = 2
DEFAULT_MAX_FAILED_ACTION_RETRIES = 1
DEFAULT_MAX_BROWSER_EVALS = 1
DEFAULT_MAX_RECOVERY_STEPS = 2
DEFAULT_MAX_BROWSER_OPEN_ATTEMPTS = 1
MAX_RECENT_TOOL_RESULTS = 8

_FINAL_ACTION_TOOLS = frozenset({"browser_click", "browser_type"})
_SUCCESS_CLAIM = re.compile(
    r"(?:已完成|完成了|操作成功|已成功|已发送|已提交|已发布|已保存|"
    r"\bdone\b|\bcompleted\b|\bsuccess(?:ful(?:ly)?)?\b|\bsent\b|"
    r"\bsubmitted\b|\bpublished\b)",
    re.I,
)
_INCOMPLETE_REPORT = re.compile(
    r"(?:失败|未完成|没有完成|没完成|无法完成|未成功|没成功|未发送|"
    r"没有发送|状态不确定|尚未|需要(?:用户|你)|等待确认|已取消|"
    r"\bfailed\b|\bincomplete\b|\bnot completed?\b|\bcould not\b|"
    r"\bunable to\b|\buncertain\b|\bawaiting (?:approval|confirmation)\b|"
    r"\bcancelled\b)",
    re.I,
)
_CONTINUATION_PREFIXES = (
    "继续",
    "你没有完成",
    "你还没有完成",
    "没有完成",
    "没完成",
    "刚才没点成功",
    "刚才没有点成功",
    "刚才失败了",
    "不是这样",
    "不对",
    "重试",
    "再试一次",
    "continue",
    "you did not finish",
    "you didn't finish",
    "that did not work",
    "try again",
)


def normalized_action_signature(name: str, arguments: dict[str, Any]) -> str:
    normalized = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{name}:{normalized}"


def is_final_browser_action(name: str, arguments: dict[str, Any]) -> bool:
    if name in _FINAL_ACTION_TOOLS:
        return True
    return name == "browser_press" and str(arguments.get("key", "")).lower() in {
        "enter",
        "space",
    }


def contains_success_claim(value: str) -> bool:
    return bool(_SUCCESS_CLAIM.search(value))


def contains_incomplete_report(value: str) -> bool:
    return bool(_INCOMPLETE_REPORT.search(value))


def is_recent_task_continuation(value: str) -> bool:
    normalized = " ".join(value.strip().lower().split()).rstrip("。.!！")
    return any(normalized.startswith(prefix) for prefix in _CONTINUATION_PREFIXES)


@dataclass(slots=True)
class BrowserTaskBudget:
    max_browser_open_attempts: int = DEFAULT_MAX_BROWSER_OPEN_ATTEMPTS
    max_consecutive_tool_failures: int = DEFAULT_MAX_CONSECUTIVE_TOOL_FAILURES
    max_failed_action_retries: int = DEFAULT_MAX_FAILED_ACTION_RETRIES
    max_browser_evals: int = DEFAULT_MAX_BROWSER_EVALS
    max_recovery_steps: int = DEFAULT_MAX_RECOVERY_STEPS


@dataclass(slots=True)
class BrowserTaskState:
    browser_used: bool = False
    browser_initialized: bool = False
    current_url: str = ""
    latest_snapshot: str = ""
    completion_state: str = "not_started"
    pending_verification: dict[str, Any] | None = None
    completion_evidence: dict[str, Any] | None = None
    last_failure: dict[str, Any] | None = None
    recent_tool_results: list[dict[str, Any]] = field(default_factory=list)
    failed_action_counts: dict[str, int] = field(default_factory=dict)
    blocked_actions: list[str] = field(default_factory=list)
    last_failed_tool: str = ""
    consecutive_tool_failures: int = 0
    browser_eval_count: int = 0
    browser_open_attempts: int = 0
    recovery_steps: int = 0
    pending_recovery_tool: str = ""
    pending_recovery_retry_used: bool = False
    completion_gate_prompts: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> BrowserTaskState:
        if not value:
            return cls()
        allowed = cls.__dataclass_fields__
        return cls(
            **{
                key: copy.deepcopy(item)
                for key, item in value.items()
                if key in allowed
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def preflight(
        self,
        name: str,
        arguments: dict[str, Any],
        budget: BrowserTaskBudget,
    ) -> ToolResult | None:
        if not name.startswith("browser_"):
            return None
        signature = normalized_action_signature(name, arguments)
        if (
            name in {"browser_open", "browser_attach"}
            and self.browser_open_attempts >= budget.max_browser_open_attempts
        ):
            return self._budget_failure(
                "The browser initialization attempt limit was reached for this task.",
                "browser_open_budget",
            )
        if signature in self.blocked_actions:
            return self._budget_failure(
                "The same non-recoverable browser action is blocked after its first failure.",
                "non_recoverable_action_repeat",
            )
        failed_count = self.failed_action_counts.get(signature, 0)
        if failed_count > budget.max_failed_action_retries:
            return self._budget_failure(
                "The same failed browser action exhausted its one retry.",
                "failed_action_retry_budget",
            )
        if (
            self.last_failed_tool == name
            and self.consecutive_tool_failures
            >= budget.max_consecutive_tool_failures
        ):
            return self._budget_failure(
                "This browser tool reached the consecutive failure limit.",
                "consecutive_tool_failure_budget",
            )
        if name == "browser_eval" and self.browser_eval_count >= budget.max_browser_evals:
            return self._budget_failure(
                "browser_eval reached the per-task fallback limit.",
                "browser_eval_budget",
            )
        if self.pending_recovery_tool == name:
            if self.pending_recovery_retry_used:
                return self._budget_failure(
                    "The recovery retry for this browser action was already consumed.",
                    "recovery_retry_budget",
                )
            self.pending_recovery_retry_used = True
        return None

    def note_result(
        self,
        name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        if not name.startswith("browser_"):
            return
        self.browser_used = True
        if name == "browser_eval":
            self.browser_eval_count += 1
        if name in {"browser_open", "browser_attach"}:
            self.browser_open_attempts += 1
        if isinstance(result, BrowserResult) and result.url:
            self.current_url = result.url
        if name == "browser_snapshot" and result.success:
            self.latest_snapshot = result.output
        entry = {
            "tool_name": name,
            "success": result.success,
            "error": result.error,
            "metadata": copy.deepcopy(result.metadata),
        }
        self.recent_tool_results.append(entry)
        del self.recent_tool_results[:-MAX_RECENT_TOOL_RESULTS]

        signature = normalized_action_signature(name, arguments)
        if not result.success:
            self.failed_action_counts[signature] = (
                self.failed_action_counts.get(signature, 0) + 1
            )
            if self.last_failed_tool == name:
                self.consecutive_tool_failures += 1
            else:
                self.last_failed_tool = name
                self.consecutive_tool_failures = 1
            error_type = str(result.metadata.get("error_type", "unknown"))
            self.last_failure = {
                "tool_name": name,
                "error": result.error or "Browser tool failed",
                "error_type": error_type,
                "recoverable": bool(result.metadata.get("recoverable", False)),
            }
            if error_type == BrowserErrorType.TOOL_SYNTAX_ERROR.value:
                if signature not in self.blocked_actions:
                    self.blocked_actions.append(signature)
            if is_final_browser_action(name, arguments) or name == "browser_verify":
                self.completion_state = (
                    "verification_failed"
                    if name == "browser_verify"
                    else "final_action_failed"
                )
            elif self.completion_state in {"not_started", "in_progress"}:
                self.completion_state = "browser_action_failed"
            return

        self.last_failed_tool = ""
        self.consecutive_tool_failures = 0
        if name == self.pending_recovery_tool:
            self.pending_recovery_tool = ""
            self.pending_recovery_retry_used = False
        if name == "browser_verify":
            self.completion_state = "verified"
            self.completion_evidence = {
                "tool_name": name,
                "arguments": copy.deepcopy(arguments),
                "postcondition_met": True,
            }
            self.pending_verification = None
            self.last_failure = None
        elif is_final_browser_action(name, arguments):
            self.completion_state = "verification_required"
            self.pending_verification = {
                "tool_name": name,
                "arguments": copy.deepcopy(arguments),
            }
            self.completion_evidence = None
            self.last_failure = None
        else:
            if self.last_failure and not is_final_browser_action(
                str(self.last_failure.get("tool_name", "")), {}
            ):
                self.last_failure = None
            if self.completion_state in {
                "not_started",
                "browser_action_failed",
            }:
                self.completion_state = "in_progress"

    @staticmethod
    def _budget_failure(reason: str, rule: str) -> ToolResult:
        return ToolResult(
            success=False,
            error=f"Browser task budget blocked this action: {reason}",
            metadata={
                "error_type": BrowserErrorType.BUDGET_EXCEEDED.value,
                "recoverable": False,
                "budget_exceeded": True,
                "budget_rule": rule,
            },
        )

    def completion_block_reason(self) -> str | None:
        if self.completion_state == "verification_required":
            action = (self.pending_verification or {}).get("tool_name", "browser action")
            return (
                f"{action} succeeded as an action, but its task postcondition has not "
                "been verified with browser_verify."
            )
        if self.completion_state == "final_action_failed":
            return "The last required browser action failed."
        if self.completion_state == "verification_failed":
            return "The browser postcondition check failed."
        if self.last_failure is not None:
            return (
                f"The latest browser failure is unresolved: "
                f"{self.last_failure.get('error_type', 'unknown')}."
            )
        return None


@dataclass(slots=True)
class RecentBrowserTask:
    session_key: str
    task_id: str
    origin_run_id: str
    browser_mode: str
    messages: list[dict[str, Any]]
    browser_snapshot: str
    loaded_skills: list[str]
    browser_initialized: bool
    browser_state: dict[str, Any]


class RecentTaskManager:
    """In-memory browser task continuation state, separate from approval."""

    def __init__(self) -> None:
        self._recent: dict[str, RecentBrowserTask] = {}

    def save(self, task: RecentBrowserTask) -> None:
        self._recent[task.session_key] = copy.deepcopy(task)

    def get(self, session_key: str) -> RecentBrowserTask | None:
        task = self._recent.get(session_key)
        return copy.deepcopy(task) if task else None

    def clear(self, session_key: str) -> RecentBrowserTask | None:
        return self._recent.pop(session_key, None)


@dataclass(slots=True)
class RecoveryPlan:
    refresh_snapshot: bool
    retry_allowed: bool
    hint: str


class BrowserRecoveryPolicy:
    """Finite, deterministic recovery advice for classified browser failures."""

    def plan(
        self,
        result: ToolResult,
        state: BrowserTaskState,
        budget: BrowserTaskBudget,
    ) -> RecoveryPlan | None:
        error_type = str(result.metadata.get("error_type", ""))
        if not result.metadata.get("recoverable"):
            return None
        if error_type in {
            BrowserErrorType.STALE_TARGET.value,
            BrowserErrorType.TARGET_NOT_FOUND.value,
        }:
            can_refresh = (
                state.recovery_steps < budget.max_recovery_steps
                and not state.pending_recovery_retry_used
            )
            return RecoveryPlan(
                refresh_snapshot=can_refresh,
                retry_allowed=can_refresh,
                hint=(
                    "Use the refreshed snapshot to relocate the element, then retry "
                    "the failed action at most once."
                ),
            )
        if error_type == BrowserErrorType.AMBIGUOUS_TARGET.value:
            return RecoveryPlan(
                refresh_snapshot=False,
                retry_allowed=True,
                hint=(
                    "Narrow the target with browser_inspect; if it remains ambiguous, "
                    "call request_user_input."
                ),
            )
        if error_type == BrowserErrorType.PAGE_TIMEOUT.value:
            return RecoveryPlan(
                refresh_snapshot=False,
                retry_allowed=True,
                hint="Re-check page state and retry one read/navigation action at most once.",
            )
        if error_type == BrowserErrorType.AUTH_REQUIRED.value:
            return RecoveryPlan(
                refresh_snapshot=False,
                retry_allowed=False,
                hint="Ask the user to complete login with request_user_input.",
            )
        if error_type == BrowserErrorType.NAVIGATION_FAILURE.value:
            return RecoveryPlan(
                refresh_snapshot=False,
                retry_allowed=True,
                hint="Retry navigation once only if the URL and browser mode are unchanged.",
            )
        return None
