from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AgentTaskStatus(str, Enum):
    NEW = "new"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_CLARIFICATION = "waiting_clarification"
    WAITING_VERIFICATION = "waiting_verification"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_STEPS = "max_steps"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[AgentTaskStatus, frozenset[AgentTaskStatus]] = {
    AgentTaskStatus.NEW: frozenset(
        {AgentTaskStatus.RUNNING, AgentTaskStatus.CANCELLED}
    ),
    AgentTaskStatus.RUNNING: frozenset(
        {
            AgentTaskStatus.WAITING_APPROVAL,
            AgentTaskStatus.WAITING_CLARIFICATION,
            AgentTaskStatus.WAITING_VERIFICATION,
            AgentTaskStatus.COMPLETED,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.MAX_STEPS,
            AgentTaskStatus.CANCELLED,
        }
    ),
    AgentTaskStatus.WAITING_APPROVAL: frozenset(
        {
            AgentTaskStatus.RUNNING,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.CANCELLED,
        }
    ),
    AgentTaskStatus.WAITING_CLARIFICATION: frozenset(
        {
            AgentTaskStatus.RUNNING,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.CANCELLED,
        }
    ),
    AgentTaskStatus.WAITING_VERIFICATION: frozenset(
        {
            AgentTaskStatus.RUNNING,
            AgentTaskStatus.COMPLETED,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.MAX_STEPS,
            AgentTaskStatus.CANCELLED,
        }
    ),
    AgentTaskStatus.COMPLETED: frozenset(),
    AgentTaskStatus.FAILED: frozenset(),
    AgentTaskStatus.MAX_STEPS: frozenset(),
    AgentTaskStatus.CANCELLED: frozenset(),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class AgentTaskState:
    """Small serializable state; persistence belongs to the storage layer."""

    task_id: str
    session_key: str
    requester_sender_id: str | None = None
    status: AgentTaskStatus = AgentTaskStatus.NEW
    status_reason: str | None = None
    active_approval_id: str | None = None
    active_clarification_id: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def transition(
        self,
        status: AgentTaskStatus,
        *,
        reason: str | None = None,
        approval_id: str | None = None,
        clarification_id: str | None = None,
    ) -> None:
        if status == self.status:
            self.status_reason = reason
            self.updated_at = _now()
            return
        if status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(
                f"invalid task state transition: {self.status.value} -> "
                f"{status.value}"
            )
        self.status = status
        self.status_reason = reason
        self.active_approval_id = (
            approval_id if status == AgentTaskStatus.WAITING_APPROVAL else None
        )
        self.active_clarification_id = (
            clarification_id
            if status == AgentTaskStatus.WAITING_CLARIFICATION
            else None
        )
        self.updated_at = _now()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AgentTaskState:
        data = dict(value)
        data["status"] = AgentTaskStatus(data.get("status", "new"))
        return cls(**data)
