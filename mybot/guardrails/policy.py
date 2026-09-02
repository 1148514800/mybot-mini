from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any

from .models import PolicyDecision, PolicyResult, RiskLevel


_SAFE_EXEC_PATTERNS = (
    re.compile(r"^(?:python|python3|py|node|uv|pip|npm)\s+--version$", re.I),
    re.compile(r"^git\s+(?:status|diff|log|show)(?:\s|$)", re.I),
    re.compile(r"^(?:pwd|ls|dir|whoami|status)(?:\s|$)", re.I),
)
_CRITICAL_EXEC_PATTERNS = (
    re.compile(r"\brm\s+-[^\n]*r[^\n]*f[^\n]*(?:\s+/\s*$|\s+~(?:/|\s|$))", re.I),
    re.compile(r"\bmkfs(?:\.|\s)", re.I),
    re.compile(r"\bformat\s+[a-z]:", re.I),
    re.compile(r"\b(?:shutdown|reboot|halt|poweroff)\b", re.I),
    re.compile(r"\bdiskpart\b[^\n]*(?:clean|delete\s+(?:disk|partition))", re.I),
    re.compile(r"\bclear-disk\b", re.I),
    re.compile(r"\bdd\s+[^\n]*\bof=/dev/", re.I),
    re.compile(r"\bdel\s+/[sq][^\n]*\s+[a-z]:\\(?:\*|$)", re.I),
)
_DESTRUCTIVE_EXEC_PATTERNS = (
    re.compile(r"(?:^|[;&|]\s*)rm(?:\s|$)", re.I),
    re.compile(r"(?:^|[;&|]\s*)(?:del|rmdir|rd)(?:\s|$)", re.I),
    re.compile(r"\bremove-item\b", re.I),
    re.compile(r"\bgit\s+(?:push|commit|reset|clean|checkout)\b", re.I),
    re.compile(r"(?:^|[;&|]\s*)(?:mv|move)(?:\s|$)", re.I),
)
_WRITE_EXEC_PATTERNS = (
    re.compile(r"\b(?:pip|uv\s+pip|npm|pnpm|yarn)\s+install\b", re.I),
    re.compile(r"\bgit\s+(?:add|merge|rebase|tag)\b", re.I),
    re.compile(r"(?:^|[;&|]\s*)(?:cp|copy|mkdir|md)(?:\s|$)", re.I),
    re.compile(r"\b(?:set-content|add-content|new-item)\b", re.I),
    re.compile(r"(?:>|>>)", re.I),
)
_SENSITIVE_WRITE_NAMES = frozenset(
    {"agents.md", "soul.md", "user.md", "tools.md"}
)
_RISKY_CLICK_KEYWORDS = (
    "永久删除",
    "确认删除",
    "删除",
    "付款",
    "支付",
    "购买",
    "提交订单",
    "发布",
    "发送",
    "注销",
    "清空",
    "delete",
    "remove",
    "pay",
    "purchase",
    "buy",
    "submit order",
    "publish",
    "send",
    "terminate",
)


class ToolPolicy:
    """Deterministic first-line runtime policy, not a system sandbox."""

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        user_input: str = "",
        context: Any = None,
    ) -> PolicyResult:
        del user_input  # Explicitly not trusted as a model-provided safety flag.
        name = tool_name.strip().lower()

        if name in {"read_file", "browser_snapshot", "browser_links"}:
            return self._allow(RiskLevel.READ, "read_only_tool", "Read-only tool")

        if name in {"browser_open", "browser_attach", "browser_goto"}:
            return self._allow(
                RiskLevel.READ,
                "browser_navigation",
                "Browser navigation does not itself commit a destructive action",
            )

        if name == "browser_tab":
            action = str(arguments.get("action", "list")).strip().lower()
            if action in {"list", "select"}:
                return self._allow(
                    RiskLevel.READ,
                    "browser_tab_read",
                    "Listing or selecting a browser tab is allowed",
                )
            return self._allow(
                RiskLevel.LOW_WRITE,
                "browser_tab_lifecycle",
                "Browser tab lifecycle change is low risk",
            )

        if name == "browser_eval":
            return self._confirm(
                RiskLevel.SENSITIVE,
                "browser_eval",
                "browser_eval can run arbitrary JavaScript in the page",
            )

        if name == "browser_click":
            snapshot = self._snapshot_from_context(context)
            target = str(arguments.get("target", "")).strip()
            target_text = self._snapshot_target_text(snapshot, target)
            keyword = next(
                (item for item in _RISKY_CLICK_KEYWORDS if item in target_text.lower()),
                None,
            )
            if keyword:
                return PolicyResult(
                    decision=PolicyDecision.REQUIRE_CONFIRMATION,
                    risk_level=RiskLevel.DESTRUCTIVE,
                    reason=(
                        "The latest accessibility snapshot labels this target as "
                        f"a consequential action ({keyword})"
                    ),
                    rule="browser_click_snapshot_keyword",
                    metadata={"target_text": target_text[:500]},
                )
            return self._allow(
                RiskLevel.LOW_WRITE,
                "browser_click_default",
                "No high-confidence destructive meaning was found for this click",
            )

        if name in {"browser_type", "browser_press", "browser_close"}:
            return self._allow(
                RiskLevel.LOW_WRITE,
                "browser_interaction",
                "Routine browser interaction is allowed",
            )

        if name == "write_file":
            path = str(arguments.get("path", ""))
            if self._is_sensitive_write_path(path):
                return self._confirm(
                    RiskLevel.SENSITIVE,
                    "sensitive_workspace_file",
                    "Writing this core configuration or instruction path may change runtime behavior",
                )
            return self._allow(
                RiskLevel.LOW_WRITE,
                "workspace_write",
                "Ordinary workspace file writes are allowed",
            )

        if name == "memory_write":
            return self._allow(
                RiskLevel.LOW_WRITE,
                "memory_write",
                "Writing or updating one memory is a low-risk state change",
            )

        if name == "memory_delete":
            return self._confirm(
                RiskLevel.SENSITIVE,
                "memory_delete",
                "Deleting long-term memory requires explicit confirmation",
            )

        if name == "exec":
            return self._evaluate_exec(str(arguments.get("command", "")))

        return self._confirm(
            RiskLevel.SENSITIVE,
            "unknown_tool",
            "This tool has no explicit runtime policy rule",
        )

    def _evaluate_exec(self, command: str) -> PolicyResult:
        normalized = " ".join(command.strip().split())
        if not normalized:
            return self._confirm(
                RiskLevel.SENSITIVE,
                "exec_unknown",
                "An empty or unrecognized shell command is not auto-approved",
            )
        if any(pattern.search(normalized) for pattern in _CRITICAL_EXEC_PATTERNS):
            return PolicyResult(
                decision=PolicyDecision.BLOCK,
                risk_level=RiskLevel.DESTRUCTIVE,
                reason="The command matches a high-confidence system-destructive pattern",
                rule="exec_critical_system_operation",
            )
        if any(pattern.search(normalized) for pattern in _DESTRUCTIVE_EXEC_PATTERNS):
            return self._confirm(
                RiskLevel.DESTRUCTIVE,
                "exec_destructive_change",
                "The command can delete, move, overwrite, or publish state",
            )
        if any(pattern.search(normalized) for pattern in _WRITE_EXEC_PATTERNS):
            return self._confirm(
                RiskLevel.SENSITIVE,
                "exec_state_change",
                "The shell command changes local or remote state",
            )
        if any(pattern.search(normalized) for pattern in _SAFE_EXEC_PATTERNS):
            return self._allow(
                RiskLevel.READ,
                "exec_safe_query",
                "The command matches a high-confidence read-only query",
            )
        return self._confirm(
            RiskLevel.SENSITIVE,
            "exec_unknown",
            "Unrecognized shell commands require confirmation before execution",
        )

    @staticmethod
    def _is_sensitive_write_path(path: str) -> bool:
        normalized = path.strip().replace("\\", "/").lstrip("./").lower()
        parts = PurePath(normalized).parts
        if not parts:
            return False
        if parts[-1] in _SENSITIVE_WRITE_NAMES:
            return True
        if "config" in parts[:-1]:
            return True
        return any(
            parts[index : index + 2] == ("workspace", "instructions")
            for index in range(max(0, len(parts) - 1))
        )

    @staticmethod
    def _snapshot_from_context(context: Any) -> str:
        if isinstance(context, dict):
            value = context.get("browser_snapshot", "")
        else:
            value = getattr(context, "browser_snapshot", "") if context else ""
        return value if isinstance(value, str) else ""

    @staticmethod
    def _snapshot_target_text(snapshot: str, target: str) -> str:
        if not snapshot or not target:
            return ""
        lines = snapshot.splitlines()
        for index, line in enumerate(lines):
            if target in line:
                start = max(0, index - 1)
                end = min(len(lines), index + 2)
                return " ".join(lines[start:end]).strip()
        return ""

    @staticmethod
    def _allow(risk: RiskLevel, rule: str, reason: str) -> PolicyResult:
        return PolicyResult(PolicyDecision.ALLOW, risk, reason, rule)

    @staticmethod
    def _confirm(risk: RiskLevel, rule: str, reason: str) -> PolicyResult:
        return PolicyResult(
            PolicyDecision.REQUIRE_CONFIRMATION,
            risk,
            reason,
            rule,
        )
