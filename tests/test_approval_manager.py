from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from mybot.guardrails import (
    ApprovalIntent,
    ApprovalManager,
    PolicyDecision,
    PolicyResult,
    RiskLevel,
    classify_approval_intent,
)


def confirmation_policy() -> PolicyResult:
    return PolicyResult(
        decision=PolicyDecision.REQUIRE_CONFIRMATION,
        risk_level=RiskLevel.DESTRUCTIVE,
        reason="test deletion",
        rule="test_rule",
    )


class ApprovalManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ApprovalManager()

    def create(self, session="cli:a"):
        return self.manager.create(
            session_key=session,
            tool_name="exec",
            arguments={"command": "rm test.txt"},
            policy=confirmation_policy(),
        )

    def test_create_get_and_clear(self):
        pending = self.create()
        self.assertIs(self.manager.get("cli:a"), pending)
        self.assertIs(self.manager.clear("cli:a"), pending)
        self.assertIsNone(self.manager.get("cli:a"))

    def test_approve_is_single_use_and_checks_id(self):
        pending = self.create()
        self.assertIsNone(self.manager.approve("cli:a", "wrong"))
        approved = self.manager.approve("cli:a", pending.approval_id)
        self.assertEqual(approved.status, "approved")
        self.assertIsNone(self.manager.approve("cli:a", pending.approval_id))

    def test_reject_consumes_pending(self):
        pending = self.create()
        rejected = self.manager.reject("cli:a", pending.approval_id)
        self.assertEqual(rejected.status, "rejected")
        self.assertIsNone(self.manager.get("cli:a"))

    def test_session_isolation(self):
        pending = self.create("cli:a")
        self.assertIsNone(self.manager.approve("cli:b", pending.approval_id))
        self.assertIs(self.manager.get("cli:a"), pending)

    def test_sender_mismatch_does_not_consume_pending(self):
        pending = self.manager.create(
            session_key="feishu:group-1",
            tool_name="exec",
            arguments={"command": "git push"},
            policy=confirmation_policy(),
            requester_sender_id="user-a",
        )

        self.assertIsNone(
            self.manager.approve(
                "feishu:group-1",
                pending.approval_id,
                "user-b",
            )
        )
        self.assertIsNone(
            self.manager.reject(
                "feishu:group-1",
                pending.approval_id,
                "user-b",
            )
        )
        self.assertIs(self.manager.get("feishu:group-1"), pending)
        approved = self.manager.approve(
            "feishu:group-1",
            pending.approval_id,
            "user-a",
        )
        self.assertEqual(approved.status, "approved")

    def test_expired_approval_is_cleared_and_cannot_execute(self):
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        manager = ApprovalManager(
            ttl_seconds=600,
            clock=lambda: now[0],
        )
        pending = manager.create(
            session_key="cli:a",
            tool_name="exec",
            arguments={"command": "git push"},
            policy=confirmation_policy(),
        )
        self.assertIs(manager.get("cli:a"), pending)

        now[0] += timedelta(seconds=600)
        expired = manager.expire("cli:a")

        self.assertIs(expired, pending)
        self.assertEqual(expired.status, "expired")
        self.assertIsNone(manager.get("cli:a"))
        self.assertIsNone(manager.approve("cli:a", pending.approval_id))

    def test_approval_within_ttl_can_be_consumed(self):
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        manager = ApprovalManager(
            ttl_seconds=600,
            clock=lambda: now[0],
        )
        pending = manager.create(
            session_key="cli:a",
            tool_name="exec",
            arguments={"command": "git push"},
            policy=confirmation_policy(),
        )
        now[0] += timedelta(seconds=599)

        approved = manager.approve("cli:a", pending.approval_id)

        self.assertIs(approved, pending)
        self.assertEqual(approved.status, "approved")

    def test_arguments_are_copied_and_exact(self):
        arguments = {"command": "rm test.txt", "options": ["force"]}
        pending = self.manager.create(
            session_key="cli:a",
            tool_name="exec",
            arguments=arguments,
            policy=confirmation_policy(),
        )
        arguments["command"] = "echo changed"
        arguments["options"].append("different")
        self.assertEqual(
            pending.arguments,
            {"command": "rm test.txt", "options": ["force"]},
        )

    def test_task_continuity_state_is_preserved(self):
        pending = self.manager.create(
            session_key="cli:a",
            tool_name="browser_eval",
            arguments={"script": "document.title"},
            policy=confirmation_policy(),
            task_id="task-1",
            loaded_skills=["skills/browser/skill.md"],
            browser_initialized=True,
        )

        self.assertEqual(pending.task_id, "task-1")
        self.assertEqual(
            pending.loaded_skills,
            ["skills/browser/skill.md"],
        )
        self.assertTrue(pending.browser_initialized)

    def test_intent_matching_is_explicit(self):
        for value in ("确认", "继续", "yes", "Y", "approve"):
            self.assertEqual(
                classify_approval_intent(value), ApprovalIntent.APPROVE
            )
        for value in ("取消", "不要执行", "no", "N", "deny"):
            self.assertEqual(
                classify_approval_intent(value), ApprovalIntent.REJECT
            )
        for value in ("也许", "帮我看日志", "yes please"):
            self.assertEqual(
                classify_approval_intent(value), ApprovalIntent.UNKNOWN
            )


if __name__ == "__main__":
    unittest.main()
