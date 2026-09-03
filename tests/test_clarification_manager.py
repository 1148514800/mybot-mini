from __future__ import annotations

import unittest

from mybot.guardrails import ClarificationManager


class ClarificationManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ClarificationManager()

    def test_create_copies_continuation_state_and_resolves_once(self) -> None:
        messages = [{"role": "user", "content": "start"}]
        pending = self.manager.create(
            session_key="cli:a",
            question="Is this the right friend?",
            task_id="task-1",
            browser_mode="managed",
            browser_session="managed_browser",
            messages=messages,
            browser_snapshot="[ref=e1]",
            loaded_skills=["skills/douyin-skills/skill.md"],
            browser_initialized=True,
        )
        messages[0]["content"] = "changed"

        self.assertIs(self.manager.get("cli:a"), pending)
        self.assertEqual(pending.messages[0]["content"], "start")
        self.assertEqual(pending.task_id, "task-1")
        self.assertEqual(pending.browser_session, "managed_browser")
        resolved = self.manager.resolve("cli:a", pending.clarification_id)
        self.assertEqual(resolved.status, "answered")
        self.assertIsNone(self.manager.get("cli:a"))
        self.assertIsNone(
            self.manager.resolve("cli:a", pending.clarification_id)
        )

    def test_session_isolation_and_cancel(self) -> None:
        pending = self.manager.create(
            session_key="cli:a",
            question="Continue?",
        )

        self.assertIsNone(
            self.manager.resolve("cli:b", pending.clarification_id)
        )
        self.assertIs(self.manager.get("cli:a"), pending)
        cancelled = self.manager.cancel("cli:a", pending.clarification_id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertIsNone(self.manager.get("cli:a"))


if __name__ == "__main__":
    unittest.main()
