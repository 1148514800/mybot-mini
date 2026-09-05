from __future__ import annotations

import re
from enum import Enum


class BrowserErrorType(str, Enum):
    """Stable browser failure categories exposed to Runtime and tracing."""

    STALE_TARGET = "stale_target"
    TARGET_NOT_FOUND = "target_not_found"
    AMBIGUOUS_TARGET = "ambiguous_target"
    TOOL_SYNTAX_ERROR = "tool_syntax_error"
    PAGE_TIMEOUT = "page_timeout"
    NAVIGATION_FAILURE = "navigation_failure"
    AUTH_REQUIRED = "auth_required"
    POLICY_BLOCKED = "policy_blocked"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNKNOWN = "unknown"


_STALE_TARGET = re.compile(
    r"(?:stale\s+(?:element|target)|ref(?:erence)?\s+[^\n]*not\s+found|"
    r"not\s+found\s+in\s+(?:the\s+)?current\s+(?:page\s+)?snapshot)",
    re.I,
)
_AMBIGUOUS_TARGET = re.compile(
    r"(?:strict\s+mode\s+violation|resolved\s+to\s+\d+\s+elements|"
    r"multiple\s+(?:matching\s+)?elements|ambiguous\s+target)",
    re.I,
)
_TOOL_SYNTAX_ERROR = re.compile(
    r"(?:syntaxerror|unexpected\s+token|unknown\s+engine|invalid\s+selector|"
    r"selector\s+parse\s+error)",
    re.I,
)
_PAGE_TIMEOUT = re.compile(r"(?:timed?\s*out|timeouterror|timeout\s+exceeded)", re.I)
_NAVIGATION_FAILURE = re.compile(
    r"(?:net::err_|navigation\s+(?:failed|aborted)|page\s+crashed|"
    r"cannot\s+navigate|failed\s+to\s+load)",
    re.I,
)
_AUTH_REQUIRED = re.compile(
    r"(?:auth(?:entication)?\s+required|not\s+authenticated|login\s+required|"
    r"sign[ -]?in\s+required|unauthorized|forbidden\s*\(?(?:401|403)\)?)",
    re.I,
)
_TARGET_NOT_FOUND = re.compile(
    r"(?:target\s+[^\n]*not\s+found|element\s+[^\n]*not\s+found|"
    r"no\s+element\s+(?:found|matches)|waiting\s+for\s+locator[^\n]*failed|"
    r"postcondition_not_met)",
    re.I,
)


def classify_browser_error(
    error: str | None,
    output: str = "",
    *,
    action: str = "",
) -> tuple[BrowserErrorType, bool]:
    """Classify high-confidence CLI failures without asking the model."""

    text = "\n".join(part for part in (error or "", output) if part)
    if _STALE_TARGET.search(text):
        return BrowserErrorType.STALE_TARGET, True
    if _AMBIGUOUS_TARGET.search(text):
        return BrowserErrorType.AMBIGUOUS_TARGET, True
    if _TOOL_SYNTAX_ERROR.search(text):
        return BrowserErrorType.TOOL_SYNTAX_ERROR, False
    if _PAGE_TIMEOUT.search(text):
        return BrowserErrorType.PAGE_TIMEOUT, True
    if _AUTH_REQUIRED.search(text):
        return BrowserErrorType.AUTH_REQUIRED, True
    if action == "goto" or _NAVIGATION_FAILURE.search(text):
        return BrowserErrorType.NAVIGATION_FAILURE, True
    if _TARGET_NOT_FOUND.search(text):
        return BrowserErrorType.TARGET_NOT_FOUND, True
    return BrowserErrorType.UNKNOWN, False


def browser_failure_metadata(
    error: str | None,
    output: str = "",
    *,
    action: str = "",
) -> dict[str, object]:
    error_type, recoverable = classify_browser_error(
        error,
        output,
        action=action,
    )
    return {
        "error_type": error_type.value,
        "recoverable": recoverable,
    }
