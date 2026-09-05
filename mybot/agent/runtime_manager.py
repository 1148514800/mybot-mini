from __future__ import annotations

import uuid
from typing import Any

from ..guardrails import ApprovalManager, ClarificationManager
from ..storage.checkpoints.store import ActiveTaskCheckpointStore
from .browser_reliability import RecentTaskManager
from .checkpoint_recovery import (
    approval_from_checkpoint,
    clarification_from_checkpoint,
    recent_task_from_checkpoint,
)
from .task_state import AgentTaskState, AgentTaskStatus


class TaskRuntimeManager:
    """Owns task lifecycle and durable waiting-state coordination."""

    def __init__(
        self,
        *,
        approvals: ApprovalManager,
        clarifications: ClarificationManager,
        recent_tasks: RecentTaskManager,
        checkpoint_store: ActiveTaskCheckpointStore | None,
    ) -> None:
        self.approvals = approvals
        self.clarifications = clarifications
        self.recent_tasks = recent_tasks
        self.checkpoint_store = checkpoint_store
        self.task_states: dict[str, AgentTaskState] = {}

    def task_state(self, task_id: str, session_key: str, sender_id: str | None) -> AgentTaskState:
        state = self.task_states.get(task_id)
        if state is None or state.status in {
            AgentTaskStatus.COMPLETED,
            AgentTaskStatus.FAILED,
            AgentTaskStatus.MAX_STEPS,
            AgentTaskStatus.CANCELLED,
        }:
            state = AgentTaskState(task_id=task_id, session_key=session_key, requester_sender_id=sender_id)
            self.task_states[task_id] = state
        return state

    def restore(self) -> None:
        store = self.checkpoint_store
        if store is None:
            return
        recent_identities: set[tuple[str, str]] = set()
        for payload in store.load_recent():
            try:
                recent = recent_task_from_checkpoint(payload)
                self.recent_tasks.save(recent)
                recent_identities.add((recent.session_key, recent.task_id))
            except (KeyError, TypeError, ValueError):
                session_key = str(payload.get("session_key", ""))
                if session_key:
                    store.clear_recent(session_key)
        for recovered in store.load_active():
            try:
                state = AgentTaskState.from_dict(recovered.task_state)
                if recovered.kind == "verification" and (state.session_key, state.task_id) not in recent_identities:
                    store.clear_active(state.session_key)
                    continue
                if recovered.kind == "approval":
                    restored = self.approvals.restore(approval_from_checkpoint(recovered.payload))
                elif recovered.kind == "clarification":
                    restored = self.clarifications.restore(clarification_from_checkpoint(recovered.payload))
                else:
                    restored = True
                if not restored:
                    store.clear_active(state.session_key)
                    continue
                self.task_states[state.task_id] = state
            except (KeyError, TypeError, ValueError):
                session_key = str(recovered.task_state.get("session_key", ""))
                if session_key:
                    store.clear_active(session_key)

    def sync(self, state: AgentTaskState) -> None:
        store = self.checkpoint_store
        if store is None or not state.session_key:
            return
        if state.status == AgentTaskStatus.WAITING_APPROVAL:
            pending = self.approvals.get(state.session_key)
            if pending and pending.approval_id == state.active_approval_id:
                store.save_approval(state, pending)
                return
        elif state.status == AgentTaskStatus.WAITING_CLARIFICATION:
            pending = self.clarifications.get(state.session_key)
            if pending and pending.clarification_id == state.active_clarification_id:
                store.save_clarification(state, pending)
                return
        elif state.status == AgentTaskStatus.WAITING_VERIFICATION:
            store.save_verification(state)
            return
        store.clear_active(state.session_key)

    def consume(self, session_key: str) -> bool:
        store = self.checkpoint_store
        if store is None or not store.enabled:
            return True
        return store.consume_active(session_key)

    def clear(self, session_key: str) -> bool:
        store = self.checkpoint_store
        return True if store is None or not store.enabled else store.clear_active(session_key)
