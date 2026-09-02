from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    READ = "read"
    LOW_WRITE = "low_write"
    SENSITIVE = "sensitive"
    DESTRUCTIVE = "destructive"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK = "block"


@dataclass(slots=True)
class PolicyResult:
    decision: PolicyDecision
    risk_level: RiskLevel
    reason: str
    rule: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PendingApproval:
    approval_id: str
    session_key: str
    tool_name: str
    arguments: dict[str, Any]
    risk_level: RiskLevel
    reason: str
    created_at: str
    origin_run_id: str | None = None
    browser_mode: str | None = None
    model_tool_call_id: str | None = None
    policy_rule: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list, repr=False)
    remaining_tool_calls: list[dict[str, Any]] = field(
        default_factory=list,
        repr=False,
    )
    browser_snapshot: str = field(default="", repr=False)
    status: str = "pending"
