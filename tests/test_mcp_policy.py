from __future__ import annotations

import unittest

from mybot.evals.fakes import build_fake_agent
from mybot.evals.models import EvalCase
from mybot.guardrails import PolicyDecision, RiskLevel, ToolPolicy
from mybot.tracing import REDACTED


def metadata(**values):
    result = {
        "tool_source": "mcp",
        "mcp_server": "demo",
        "mcp_tool_name": "tool",
        "trust_annotations": False,
    }
    result.update(values)
    return result


class MCPPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = ToolPolicy()

    def evaluate(self, tool_metadata):
        return self.policy.evaluate(
            "mcp__demo__tool",
            {"value": 1},
            tool_metadata=tool_metadata,
        )

    def test_untrusted_read_only_hint_still_requires_confirmation(self):
        result = self.evaluate(metadata(read_only_hint=True))
        self.assertEqual(result.decision, PolicyDecision.REQUIRE_CONFIRMATION)
        self.assertEqual(result.risk_level, RiskLevel.SENSITIVE)

    def test_trusted_read_only_hint_is_allowed(self):
        result = self.evaluate(
            metadata(trust_annotations=True, read_only_hint=True)
        )
        self.assertEqual(result.decision, PolicyDecision.ALLOW)
        self.assertEqual(result.risk_level, RiskLevel.READ)

    def test_destructive_hint_requires_confirmation(self):
        result = self.evaluate(metadata(destructive_hint=True))
        self.assertEqual(result.decision, PolicyDecision.REQUIRE_CONFIRMATION)
        self.assertEqual(result.risk_level, RiskLevel.DESTRUCTIVE)

    def test_explicit_overrides_have_highest_priority(self):
        expected = {
            "allow": PolicyDecision.ALLOW,
            "confirm": PolicyDecision.REQUIRE_CONFIRMATION,
            "block": PolicyDecision.BLOCK,
        }
        for override, decision in expected.items():
            with self.subTest(override=override):
                result = self.evaluate(
                    metadata(
                        trust_annotations=True,
                        read_only_hint=True,
                        destructive_hint=True,
                        mcp_policy_override=override,
                    )
                )
                self.assertEqual(result.decision, decision)
                self.assertEqual(result.rule, "mcp_explicit_override")


class MCPAgentPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_uses_existing_trace_and_exact_single_use_approval(self):
        case = EvalCase(
            id="mcp-agent",
            name="mcp agent",
            input="create external item",
            metadata={
                "fake_tools": [
                    {
                        "name": "mcp__demo__create_item",
                        "arguments": {
                            "title": "exact title",
                            "token": "raw-secret-token",
                        },
                        "output": "created",
                        "runtime_metadata": {
                            "tool_source": "mcp",
                            "mcp_server": "demo",
                            "mcp_tool_name": "create_item",
                            "local_tool_name": "mcp__demo__create_item",
                            "transport": "stdio",
                            "protocol_version": "sdk-negotiated",
                            "trust_annotations": False,
                        },
                    }
                ],
                "fake_output": "complete",
            },
        )
        agent = build_fake_agent(case)
        _, pending_trace = await agent.run_traced(
            case.input,
            [{"role": "user", "content": case.input}],
            session_key="cli:mcp",
        )
        self.assertEqual(pending_trace.status, "awaiting_confirmation")
        self.assertEqual(agent.tools.execution_count, 0)
        pending_call = pending_trace.tool_calls[0]
        self.assertEqual(pending_call.metadata["tool_source"], "mcp")
        self.assertEqual(pending_call.metadata["mcp_server"], "demo")
        self.assertEqual(
            pending_call.metadata["policy_decision"],
            "require_confirmation",
        )
        self.assertEqual(pending_call.arguments["token"], REDACTED)

        pending = agent.approvals.get("cli:mcp")
        output, approved_trace = await agent.resume_pending(
            "cli:mcp",
            "确认",
        )
        self.assertEqual(output, "complete")
        self.assertEqual(agent.tools.execution_count, 1)
        self.assertEqual(
            agent.tools.executed_calls[0][1],
            {"title": "exact title", "token": "raw-secret-token"},
        )
        approved_call = approved_trace.tool_calls[0]
        self.assertEqual(approved_call.metadata["approval_status"], "approved")
        self.assertEqual(approved_call.metadata["approval_id"], pending.approval_id)
        self.assertEqual(approved_call.metadata["protocol_version"], "sdk-negotiated")
        self.assertIsNone(agent.approvals.get("cli:mcp"))


if __name__ == "__main__":
    unittest.main()
