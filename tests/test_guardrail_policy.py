from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

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

    def test_safe_exec_allowlist_matches_the_whole_command(self):
        for command in (
            "git status",
            "git status --short",
            "git diff",
            "git diff --stat",
            "git log -5",
            "git show HEAD",
            "python --version",
            "node --version",
            "uv --version",
            "pwd",
            "whoami",
        ):
            with self.subTest(command=command):
                self.assert_decision(
                    "exec",
                    {"command": command},
                    PolicyDecision.ALLOW,
                    RiskLevel.READ,
                )

    def test_shell_control_syntax_never_gets_safe_query_allow(self):
        for command in (
            "git status && echo test",
            "git status; echo test",
            "git status | another-command",
            "git status || another-command",
            "python --version && echo test",
            "pwd && another-command",
            "git status > output.txt",
            "git status\necho test",
            "git show `whoami`",
            "git show $(whoami)",
            "git diff --output result.txt",
            "git diff --ext-diff",
        ):
            with self.subTest(command=command):
                result = self.policy.evaluate("exec", {"command": command})
                self.assertNotEqual(result.decision, PolicyDecision.ALLOW)

    def test_unknown_and_state_changing_exec_require_confirmation(self):
        for command in (
            "echo hello",
            "git push",
            "git commit -m test",
            "pip install sample",
            "npm install sample",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    self.policy.evaluate("exec", {"command": command}).decision,
                    PolicyDecision.REQUIRE_CONFIRMATION,
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

    def test_browser_verify_is_allowed_as_read_only(self):
        self.assert_decision(
            "browser_verify",
            {"text": "Saved"},
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

    def test_missing_snapshot_target_requires_confirmation(self):
        result = self.policy.evaluate(
                "browser_click",
                {"target": "e99"},
                context={"browser_snapshot": "- button '删除' [ref=e11]"},
            )
        self.assertEqual(
            result.decision,
            PolicyDecision.REQUIRE_CONFIRMATION,
        )
        self.assertEqual(result.rule, "browser_click_unknown_ref")

    def test_snapshot_refs_are_matched_exactly(self):
        for target, other in (("e1", "e10"), ("e11", "e110")):
            with self.subTest(target=target, other=other):
                result = self.policy.evaluate(
                    "browser_click",
                    {"target": target},
                    context={
                        "browser_snapshot": (
                            f"- button '删除' [ref={other}]"
                        )
                    },
                )
                self.assertEqual(
                    result.decision,
                    PolicyDecision.REQUIRE_CONFIRMATION,
                )
                self.assertEqual(result.rule, "browser_click_unknown_ref")

    def test_browser_submit_paths_require_confirmation(self):
        self.assertEqual(
            self.policy.evaluate(
                "browser_type",
                {"target": "e1", "text": "hello", "submit": False},
            ).decision,
            PolicyDecision.ALLOW,
        )
        self.assertEqual(
            self.policy.evaluate(
                "browser_type",
                {"target": "e1", "text": "hello", "submit": True},
            ).decision,
            PolicyDecision.REQUIRE_CONFIRMATION,
        )
        for key in ("Enter", "Space", "Control+Enter", "NumpadEnter"):
            with self.subTest(key=key):
                self.assertEqual(
                    self.policy.evaluate(
                        "browser_press", {"key": key}
                    ).decision,
                    PolicyDecision.REQUIRE_CONFIRMATION,
                )
        self.assertEqual(
            self.policy.evaluate(
                "browser_press", {"key": "ArrowDown"}
            ).decision,
            PolicyDecision.ALLOW,
        )
        self.assertEqual(
            self.policy.evaluate(
                "browser_type",
                {"target": "e1", "text": "hello", "submit": "false"},
            ).decision,
            PolicyDecision.REQUIRE_CONFIRMATION,
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

    def test_runtime_managed_paths_are_blocked_from_write_file(self):
        for path in (
            "memory/memory.json",
            "sessions/cli_direct.jsonl",
            "browser_profiles/managed_browser/state.json",
            "runs/trace.json",
            "checkpoints/active_tasks.sqlite3",
            "workspace/memory/memory.json",
            "workspace/checkpoints/active_tasks.sqlite3",
        ):
            with self.subTest(path=path):
                result = self.policy.evaluate(
                    "write_file",
                    {"path": path, "content": "overwrite"},
                )
                self.assertEqual(result.decision, PolicyDecision.BLOCK)
                self.assertEqual(
                    result.rule,
                    "runtime_managed_workspace_path",
                )

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            result = ToolPolicy(workspace).evaluate(
                "write_file",
                {
                    "path": str(workspace / "sessions" / "group.jsonl"),
                    "content": "overwrite",
                },
            )
            self.assertEqual(result.decision, PolicyDecision.BLOCK)

    def test_ordinary_workspace_file_remains_allowed(self):
        self.assertEqual(
            self.policy.evaluate(
                "write_file",
                {"path": "notes/status.txt", "content": "ready"},
            ).decision,
            PolicyDecision.ALLOW,
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
