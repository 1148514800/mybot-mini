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
    arguments: dict[str, Any] = field(repr=False)
    risk_level: RiskLevel
    reason: str
    created_at: str
    expires_at: str
    requester_sender_id: str | None = None
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
    task_id: str | None = None
    loaded_skills: list[str] = field(default_factory=list, repr=False)
    browser_initialized: bool = False
    browser_state: dict[str, Any] = field(default_factory=dict, repr=False)
    policy_metadata: dict[str, Any] = field(default_factory=dict, repr=False)
    status: str = "pending"
