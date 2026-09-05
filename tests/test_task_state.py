from __future__ import annotations

import unittest

from mybot.agent.task_state import AgentTaskState, AgentTaskStatus


class AgentTaskStateTests(unittest.TestCase):
    def new_state(self) -> AgentTaskState:
        return AgentTaskState(
            task_id="task-1",
            session_key="cli:test",
            requester_sender_id="user-a",
        )

    def test_primary_state_transitions(self) -> None:
        state = self.new_state()
        self.assertEqual(state.status, AgentTaskStatus.NEW)

        state.transition(AgentTaskStatus.RUNNING)
        state.transition(
            AgentTaskStatus.WAITING_APPROVAL,
            approval_id="approval-1",
        )
        self.assertEqual(state.active_approval_id, "approval-1")
        state.transition(AgentTaskStatus.RUNNING)
        state.transition(
            AgentTaskStatus.WAITING_CLARIFICATION,
            clarification_id="clarification-1",
        )
        self.assertEqual(state.active_clarification_id, "clarification-1")
        state.transition(AgentTaskStatus.RUNNING)
        state.transition(AgentTaskStatus.WAITING_VERIFICATION)
        state.transition(AgentTaskStatus.RUNNING)
        state.transition(AgentTaskStatus.COMPLETED)

        self.assertEqual(state.status, AgentTaskStatus.COMPLETED)

    def test_terminal_and_failure_states(self) -> None:
        for terminal in (
            AgentTaskStatus.FAILED,
            AgentTaskStatus.MAX_STEPS,
            AgentTaskStatus.CANCELLED,
        ):
            with self.subTest(terminal=terminal):
                state = self.new_state()
                state.transition(AgentTaskStatus.RUNNING)
                state.transition(terminal, reason=terminal.value)
                self.assertEqual(state.status, terminal)
                with self.assertRaises(ValueError):
                    state.transition(AgentTaskStatus.RUNNING)

    def test_waiting_approval_can_fail_when_expired(self) -> None:
        state = self.new_state()
        state.transition(AgentTaskStatus.RUNNING)
        state.transition(AgentTaskStatus.WAITING_APPROVAL)
        state.transition(AgentTaskStatus.FAILED, reason="approval_expired")
        self.assertEqual(state.status, AgentTaskStatus.FAILED)
        self.assertEqual(state.status_reason, "approval_expired")

    def test_round_trip_is_serializable_and_contains_no_tool_arguments(self) -> None:
        state = self.new_state()
        state.transition(AgentTaskStatus.RUNNING)
        state.transition(
            AgentTaskStatus.WAITING_APPROVAL,
            approval_id="approval-1",
        )

        data = state.to_dict()
        restored = AgentTaskState.from_dict(data)

        self.assertEqual(restored.to_dict(), data)
        self.assertNotIn("arguments", data)
        self.assertNotIn("messages", data)

    def test_invalid_transition_is_rejected(self) -> None:
        state = self.new_state()
        with self.assertRaises(ValueError):
            state.transition(AgentTaskStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
