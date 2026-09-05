from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import PolicyDecision, PolicyResult, RiskLevel
from .paths import WorkspaceWriteKind, classify_workspace_write_path


_SAFE_EXEC_PATTERNS = (
    re.compile(r"(?:python|python3|py|node|uv|pip|npm)\s+--version", re.I),
    re.compile(
        r"git\s+status(?:\s+(?:--short|-s|--branch|-b|"
        r"--porcelain(?:=v[12])?|--untracked-files(?:=(?:all|normal|no))?))*",
        re.I,
    ),
    re.compile(
        r"git\s+diff(?:\s+(?:--stat|--name-only|--name-status|--cached|"
        r"--staged|--check|--summary|HEAD(?:~\d+|\^\d*)?|"
        r"[0-9a-f]{4,40}|--|[A-Za-z0-9_./][A-Za-z0-9_./-]*))*",
        re.I,
    ),
    re.compile(
        r"git\s+log(?:\s+(?:-\d+|--max-count=\d+|--oneline|--stat|"
        r"--decorate|--graph|--all|HEAD(?:~\d+|\^\d*)?))*",
        re.I,
    ),
    re.compile(
        r"git\s+show(?:\s+(?:--stat|--name-only|--name-status|--oneline|"
        r"--summary|HEAD(?:~\d+|\^\d*)?|[0-9a-f]{4,40}))*",
        re.I,
    ),
    re.compile(r"(?:pwd|whoami|status)", re.I),
    re.compile(
        r"ls(?:\s+(?:-[A-Za-z]+|--(?:all|almost-all|long)|"
        r"[A-Za-z0-9_./~][A-Za-z0-9_./~-]*))*",
        re.I,
    ),
    re.compile(r"dir(?:\s+(?:/[A-Za-z]+|[A-Za-z0-9_:.\\/-]+))*", re.I),
)
_SHELL_CONTROL_PATTERN = re.compile(
    r"(?:&&|\|\||[;&|><`\r\n^]|\$\(|\$\{|%[^%\r\n]+%|![^!\r\n]+!)"
)
_REF_TARGET_PATTERN = re.compile(r"^e\d+$", re.I)
_PAGE_URL_PATTERN = re.compile(r"(?m)^- Page URL:\s*(.+?)\s*$")
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

    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = workspace.resolve() if workspace else None

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        user_input: str = "",
        context: Any = None,
        tool_metadata: dict[str, Any] | None = None,
    ) -> PolicyResult:
        del user_input  # Explicitly not trusted as a model-provided safety flag.
        name = tool_name.strip().lower()
        metadata = tool_metadata or {}

        if metadata.get("tool_source") == "mcp":
            return self._evaluate_mcp(metadata)

        if name in {
            "read_file",
            "browser_snapshot",
            "browser_links",
            "browser_inspect",
            "browser_verify",
            "request_user_input",
        }:
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
            if _REF_TARGET_PATTERN.fullmatch(target) and target_text is None:
                return self._confirm(
                    RiskLevel.SENSITIVE,
                    "browser_click_unknown_ref",
                    "The target ref is absent from the latest accessibility snapshot",
                    metadata={
                        "target": target,
                        **self._browser_context_metadata(snapshot),
                    },
                )
            keyword = next(
                (
                    item
                    for item in _RISKY_CLICK_KEYWORDS
                    if item in (target_text or "").lower()
                ),
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
                    metadata={
                        "target_text": (target_text or "")[:500],
                        **self._browser_context_metadata(snapshot),
                    },
                )
            return self._allow(
                RiskLevel.LOW_WRITE,
                "browser_click_default",
                "No high-confidence destructive meaning was found for this click",
            )

        if name == "browser_type":
            submit = arguments.get("submit", False)
            if submit is not False:
                return self._confirm(
                    RiskLevel.SENSITIVE,
                    "browser_type_submit",
                    "Submitting browser input can commit an unknown consequential action",
                )
            return self._allow(
                RiskLevel.LOW_WRITE,
                "browser_type_input",
                "Typing without submission is a low-risk browser interaction",
            )

        if name == "browser_press":
            key = str(arguments.get("key", "")).strip().lower()
            key_parts = {part for part in re.split(r"[+\s]+", key) if part}
            if key_parts & {
                "enter",
                "return",
                "numpadenter",
                "space",
                "spacebar",
            }:
                return self._confirm(
                    RiskLevel.SENSITIVE,
                    "browser_press_submit_key",
                    "Enter or Space can submit or activate an unknown consequential action",
                )
            return self._allow(
                RiskLevel.LOW_WRITE,
                "browser_press_routine_key",
                "This key is not treated as an implicit submit action",
            )

        if name == "browser_close":
            return self._allow(
                RiskLevel.LOW_WRITE,
                "browser_interaction",
                "Routine browser interaction is allowed",
            )

        if name == "write_file":
            path = str(arguments.get("path", ""))
            path_kind = classify_workspace_write_path(path, self.workspace)
            if path_kind == WorkspaceWriteKind.RUNTIME_MANAGED:
                return PolicyResult(
                    PolicyDecision.BLOCK,
                    RiskLevel.SENSITIVE,
                    "Runtime-managed state must be changed through its dedicated runtime API",
                    "runtime_managed_workspace_path",
                    metadata={"path": path},
                )
            if path_kind == WorkspaceWriteKind.SENSITIVE:
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

    def _evaluate_mcp(self, metadata: dict[str, Any]) -> PolicyResult:
        destructive = metadata.get("destructive_hint") is True
        read_only = metadata.get("read_only_hint") is True
        risk = (
            RiskLevel.DESTRUCTIVE
            if destructive
            else RiskLevel.READ
            if read_only
            else RiskLevel.SENSITIVE
        )
        override = str(metadata.get("mcp_policy_override", "")).lower()
        if override == "allow":
            return PolicyResult(
                PolicyDecision.ALLOW,
                risk,
                "MCP tool is allowed by an explicit local policy override",
                "mcp_explicit_override",
            )
        if override == "confirm":
            return self._confirm(
                risk,
                "mcp_explicit_override",
                "MCP tool requires confirmation by explicit local policy override",
            )
        if override == "block":
            return PolicyResult(
                PolicyDecision.BLOCK,
                risk,
                "MCP tool is blocked by an explicit local policy override",
                "mcp_explicit_override",
            )

        if destructive:
            return self._confirm(
                RiskLevel.DESTRUCTIVE,
                "mcp_destructive_hint",
                "External MCP tool declares a destructive action",
            )
        if metadata.get("trust_annotations") is True and read_only:
            return self._allow(
                RiskLevel.READ,
                "mcp_trusted_read_only",
                "Trusted MCP annotations declare this tool read-only",
            )
        return self._confirm(
            RiskLevel.SENSITIVE,
            "mcp_external_default",
            "External MCP tools require confirmation unless locally allowed",
        )

    def _evaluate_exec(self, command: str) -> PolicyResult:
        stripped = command.strip()
        normalized = " ".join(stripped.split())
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
        if (
            not _SHELL_CONTROL_PATTERN.search(stripped)
            and any(pattern.fullmatch(normalized) for pattern in _SAFE_EXEC_PATTERNS)
        ):
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
    def _snapshot_from_context(context: Any) -> str:
        if isinstance(context, dict):
            value = context.get("browser_snapshot", "")
        else:
            value = getattr(context, "browser_snapshot", "") if context else ""
        return value if isinstance(value, str) else ""

    @staticmethod
    def _snapshot_target_text(snapshot: str, target: str) -> str | None:
        if not snapshot or not target:
            return None
        ref_pattern = re.compile(
            rf"\[ref\s*=\s*['\"]?{re.escape(target)}['\"]?\]",
            re.I,
        )
        lines = snapshot.splitlines()
        for index, line in enumerate(lines):
            if ref_pattern.search(line):
                start = max(0, index - 1)
                end = min(len(lines), index + 2)
                return " ".join(lines[start:end]).strip()
        return None

    @staticmethod
    def _browser_context_metadata(snapshot: str) -> dict[str, str]:
        match = _PAGE_URL_PATTERN.search(snapshot)
        return {"current_url": match.group(1).strip()} if match else {}

    @staticmethod
    def _allow(risk: RiskLevel, rule: str, reason: str) -> PolicyResult:
        return PolicyResult(PolicyDecision.ALLOW, risk, reason, rule)

    @staticmethod
    def _confirm(
        risk: RiskLevel,
        rule: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyResult:
        return PolicyResult(
            PolicyDecision.REQUIRE_CONFIRMATION,
            risk,
            reason,
            rule,
            metadata or {},
        )
