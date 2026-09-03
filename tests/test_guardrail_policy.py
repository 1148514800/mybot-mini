from __future__ import annotations

import unittest

from mybot.guardrails import PolicyDecision, RiskLevel, ToolPolicy


class ToolPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = ToolPolicy()

    def assert_decision(self, tool, arguments, decision, risk, context=None):
        result = self.policy.evaluate(tool, arguments, context=context)
        self.assertEqual(result.decision, decision)
        self.assertEqual(result.risk_level, risk)
        self.assertTrue(result.reason)
        self.assertTrue(result.rule)

    def test_read_tool_is_allowed(self):
        self.assert_decision(
            "read_file",
            {"path": "README.md"},
            PolicyDecision.ALLOW,
            RiskLevel.READ,
        )

    def test_safe_exec_is_allowed(self):
        self.assert_decision(
            "exec",
            {"command": "python --version"},
            PolicyDecision.ALLOW,
            RiskLevel.READ,
        )

    def test_destructive_exec_requires_confirmation(self):
        self.assert_decision(
            "exec",
            {"command": "rm -rf tests/output"},
            PolicyDecision.REQUIRE_CONFIRMATION,
            RiskLevel.DESTRUCTIVE,
        )

    def test_critical_exec_is_blocked(self):
        self.assert_decision(
            "exec",
            {"command": "rm -rf /"},
            PolicyDecision.BLOCK,
            RiskLevel.DESTRUCTIVE,
        )

    def test_browser_eval_requires_confirmation(self):
        self.assert_decision(
            "browser_eval",
            {"script": "document.body.remove()"},
            PolicyDecision.REQUIRE_CONFIRMATION,
            RiskLevel.SENSITIVE,
        )

    def test_browser_inspect_is_allowed_as_read_only(self):
        self.assert_decision(
            "browser_inspect",
            {"role": "button", "text": "Send"},
            PolicyDecision.ALLOW,
            RiskLevel.READ,
        )

    def test_normal_browser_click_is_allowed(self):
        self.assert_decision(
            "browser_click",
            {"target": "e10"},
            PolicyDecision.ALLOW,
            RiskLevel.LOW_WRITE,
            {"browser_snapshot": "- link 'Next page' [ref=e10]"},
        )

    def test_destructive_snapshot_click_requires_confirmation(self):
        self.assert_decision(
            "browser_click",
            {"target": "e11"},
            PolicyDecision.REQUIRE_CONFIRMATION,
            RiskLevel.DESTRUCTIVE,
            {"browser_snapshot": "- button '永久删除' [ref=e11]"},
        )

    def test_missing_snapshot_target_falls_back_to_allow(self):
        self.assertEqual(
            self.policy.evaluate(
                "browser_click",
                {"target": "e99"},
                context={"browser_snapshot": "- button '删除' [ref=e11]"},
            ).decision,
            PolicyDecision.ALLOW,
        )

    def test_sensitive_write_requires_confirmation(self):
        for path in (
            "config/config.json",
            "workspace/instructions/runtime.md",
            "AGENTS.md",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.policy.evaluate(
                        "write_file",
                        {"path": path, "content": "new"},
                    ).decision,
                    PolicyDecision.REQUIRE_CONFIRMATION,
                )

    def test_memory_policy(self):
        self.assertEqual(
            self.policy.evaluate(
                "memory_write", {"key": "name", "value": "Ada"}
            ).decision,
            PolicyDecision.ALLOW,
        )
        self.assertEqual(
            self.policy.evaluate("memory_delete", {"key": "name"}).decision,
            PolicyDecision.REQUIRE_CONFIRMATION,
        )

    def test_unknown_tool_requires_confirmation(self):
        result = self.policy.evaluate("future_tool", {"value": "x"})
        self.assertEqual(
            result.decision,
            PolicyDecision.REQUIRE_CONFIRMATION,
        )
        self.assertEqual(result.risk_level, RiskLevel.SENSITIVE)


if __name__ == "__main__":
    unittest.main()
