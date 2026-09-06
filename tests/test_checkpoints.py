from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from mybot.agent.task_state import AgentTaskStatus
from mybot.evals.fakes import build_fake_agent
from mybot.evals.models import EvalCase
from mybot.guardrails import (
    ApprovalManager,
    PolicyDecision,
    PolicyResult,
    RiskLevel,
)
from mybot.storage.checkpoint import ActiveTaskCheckpointStore
from mybot.storage.artifacts import ArtifactStore
from mybot.tools.artifact import ArtifactReadTool
from mybot.tracing import REDACTED


def checkpoint_case(
    tools: list[dict],
    *,
    output: str = "task complete",
    responses: list[dict] | None = None,
) -> EvalCase:
    metadata = {"fake_tools": tools, "fake_output": output}
    if responses is not None:
        metadata["fake_response_sequence"] = responses
    return EvalCase(
        id="checkpoint",
        name="checkpoint",
        input="continue task",
        metadata=metadata,
    )


def exec_call() -> dict:
    return {
        "name": "exec",
        "arguments": {"command": "git commit -m exact"},
        "output": "committed",
    }


class ActiveTaskCheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_result_reference_survives_approval_checkpoint_restart(self):
        sentinel = "LARGE_SENTINEL_FULL_BODY_12345"
        large_result = "A" * 5000 + sentinel + "B" * 5000
        read_call = {
            "name": "read_file",
            "arguments": {"path": "large.txt"},
            "output": large_result,
        }
        dangerous_call = exec_call()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            workspace = Path(directory)
            checkpoint_store = ActiveTaskCheckpointStore(workspace)
            first = build_fake_agent(
                checkpoint_case([read_call, dangerous_call]),
                checkpoint_store=checkpoint_store,
            )
            first.artifact_store = ArtifactStore(workspace)
            prompt, trace = await first.run_traced(
                "read and commit",
                [{"role": "user", "content": "read and commit"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            self.assertEqual(trace.status, "awaiting_confirmation")
            self.assertIn("确认", prompt)

            payload = checkpoint_store.path.read_bytes()
            self.assertIn(b"art_", payload)
            self.assertNotIn(sentinel.encode(), payload)
            self.assertNotIn(large_result.encode(), payload)
            with sqlite3.connect(checkpoint_store.path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT schema_version FROM active_tasks WHERE session_key='cli:a'"
                    ).fetchone()[0],
                    1,
                )

            restarted = build_fake_agent(
                checkpoint_case([], output="unused"),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            pending = restarted.approvals.get("cli:a")
            self.assertIsNotNone(pending)
            reference = next(
                item["content"].split("artifact_id=", 1)[1].split("\n", 1)[0]
                for item in pending.messages
                if item.get("role") == "tool" and "artifact_id=art_" in item.get("content", "")
            )
            reader = ArtifactReadTool(ArtifactStore(workspace), read_max_chars=4000)
            available = await reader.execute(
                reference,
                max_chars=100,
                session_key="cli:a",
            )
            self.assertTrue(available.success)
            denied = await reader.execute(
                available.metadata["artifact_id"], max_chars=100, session_key="cli:b"
            )
            self.assertFalse(denied.success)
            self.assertEqual(denied.metadata["error_type"], "artifact_unavailable")
    async def create_exec_approval(
        self,
        workspace: Path,
        *,
        clock=None,
    ):
        store = ActiveTaskCheckpointStore(workspace, clock=clock)
        approvals = ApprovalManager(clock=clock) if clock else None
        agent = build_fake_agent(
            checkpoint_case([exec_call()]),
            checkpoint_store=store,
            approvals=approvals,
        )
        prompt, trace = await agent.run_traced(
            "commit changes",
            [{"role": "user", "content": "commit changes"}],
            session_key="cli:a",
            requester_sender_id="user-a",
        )
        self.assertEqual(trace.status, "awaiting_confirmation")
        self.assertIn("回复“确认”", prompt)
        return store, trace

    async def test_approval_restart_does_not_replay_and_executes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store, first_trace = await self.create_exec_approval(workspace)
            self.assertEqual(store.active_count(), 1)

            restarted = build_fake_agent(
                checkpoint_case(
                    [exec_call()],
                    responses=[{"output": "task complete"}],
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            self.assertEqual(restarted.tools.execution_count, 0)
            self.assertEqual(
                len(restarted.client.chat.completions.requests),
                0,
            )
            pending = restarted.approvals.get("cli:a")
            self.assertIsNotNone(pending)
            self.assertTrue(pending.recovered_from_checkpoint)
            self.assertFalse(pending.browser_initialized)

            denied, denied_trace = await restarted.resume_pending(
                "cli:a", "确认", "user-b"
            )
            self.assertIn("只能由原操作发起人", denied)
            self.assertEqual(denied_trace.task_status, "waiting_approval")
            self.assertEqual(restarted.tools.execution_count, 0)

            output, resumed = await restarted.resume_pending(
                "cli:a", "确认", "user-a"
            )
            self.assertEqual(output, "task complete")
            self.assertEqual(resumed.task_id, first_trace.task_id)
            self.assertEqual(restarted.tools.execution_count, 1)
            self.assertEqual(
                restarted.tools.executed_calls[0][1]["command"],
                "git commit -m exact",
            )
            self.assertEqual(restarted.checkpoint_store.active_count(), 0)

    async def test_persisted_approval_delete_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store, _ = await self.create_exec_approval(workspace)
            original = store.consume_active
            store.consume_active = lambda session_key: False
            agent = build_fake_agent(
                checkpoint_case([exec_call()], output="must not execute"),
                checkpoint_store=store,
            )
            output, _ = await agent.resume_pending("cli:a", "确认", "user-a")
            self.assertIn("无法安全消费", output)
            self.assertEqual(agent.tools.execution_count, 0)
            store.consume_active = original

    async def test_restart_skips_unapproved_remaining_batch_side_effects(self):
        unapproved_secret = "unapproved-batch-secret-value"
        write_call = {
            "name": "write_file",
            "arguments": {
                "path": "notes/after.txt",
                "content": unapproved_secret,
            },
            "output": "must not execute",
        }
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            case = checkpoint_case([exec_call(), write_call])
            case.metadata["fake_tool_batches"] = [[exec_call(), write_call]]
            first = build_fake_agent(
                case,
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            await first.run_traced(
                "commit and write",
                [{"role": "user", "content": "commit and write"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            for checkpoint_file in (workspace / "checkpoints").iterdir():
                self.assertNotIn(
                    unapproved_secret.encode(),
                    checkpoint_file.read_bytes(),
                )

            restarted = build_fake_agent(
                checkpoint_case(
                    [exec_call()],
                    responses=[{"output": "re-evaluated"}],
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            self.assertEqual(restarted.tools.execution_count, 0)
            output, _ = await restarted.resume_pending(
                "cli:a", "确认", "user-a"
            )

            self.assertEqual(output, "re-evaluated")
            self.assertEqual(
                [name for name, _ in restarted.tools.executed_calls],
                ["exec"],
            )

    async def test_expired_approval_is_not_restored(self):
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store, _ = await self.create_exec_approval(
                workspace,
                clock=lambda: now[0],
            )
            self.assertEqual(store.active_count(), 1)
            now[0] += timedelta(seconds=601)

            restarted = build_fake_agent(
                checkpoint_case(
                    [exec_call()],
                    responses=[{"output": "unused"}],
                ),
                checkpoint_store=ActiveTaskCheckpointStore(
                    workspace,
                    clock=lambda: now[0],
                ),
                approvals=ApprovalManager(clock=lambda: now[0]),
            )
            self.assertIsNone(restarted.approvals.get("cli:a"))
            self.assertEqual(restarted.tools.execution_count, 0)
            self.assertEqual(restarted.checkpoint_store.active_count(), 0)

    async def test_restored_approval_rechecks_current_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            await self.create_exec_approval(workspace)
            restarted = build_fake_agent(
                checkpoint_case(
                    [exec_call()],
                    responses=[{"output": "unused"}],
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            restarted.tool_policy = SimpleNamespace(
                evaluate=lambda *args, **kwargs: PolicyResult(
                    decision=PolicyDecision.BLOCK,
                    risk_level=RiskLevel.DESTRUCTIVE,
                    reason="policy changed",
                    rule="test_block",
                )
            )

            output, trace = await restarted.resume_pending(
                "cli:a", "确认", "user-a"
            )

            self.assertIn("Blocked by tool policy", output)
            self.assertEqual(trace.status, "failed")
            self.assertEqual(restarted.tools.execution_count, 0)
            self.assertEqual(restarted.checkpoint_store.active_count(), 0)

    async def test_clarification_resumes_same_task_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = build_fake_agent(
                checkpoint_case(
                    [
                        {
                            "name": "request_user_input",
                            "arguments": {"question": "Which friend?"},
                            "output": "Which friend?",
                        }
                    ]
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            question, first_trace = await first.run_traced(
                "send message",
                [{"role": "user", "content": "send message"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            self.assertEqual(question, "Which friend?")

            restarted = build_fake_agent(
                checkpoint_case([], output="original task complete"),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            pending = restarted.clarifications.get("cli:a")
            self.assertIsNotNone(pending)
            self.assertTrue(pending.recovered_from_checkpoint)
            self.assertEqual(restarted.tools.execution_count, 0)

            output, resumed = await restarted.resume_clarification(
                "cli:a", "Alice"
            )
            self.assertEqual(output, "original task complete")
            self.assertEqual(resumed.task_id, first_trace.task_id)
            self.assertEqual(resumed.task_status, "completed")
            self.assertEqual(restarted.checkpoint_store.active_count(), 0)

    async def test_recent_browser_task_restores_as_stale_and_expires(self):
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first_store = ActiveTaskCheckpointStore(
                workspace,
                recent_task_ttl_seconds=10,
                clock=lambda: now[0],
            )
            first = build_fake_agent(
                checkpoint_case(
                    [
                        {
                            "name": "browser_snapshot",
                            "arguments": {},
                            "output": "- Page URL: https://example.com",
                        }
                    ],
                    output="initial check complete",
                ),
                checkpoint_store=first_store,
            )
            _, first_trace = await first.run_traced(
                "inspect page",
                [{"role": "user", "content": "inspect page"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )

            restarted = build_fake_agent(
                checkpoint_case([], output="continued"),
                checkpoint_store=ActiveTaskCheckpointStore(
                    workspace,
                    recent_task_ttl_seconds=10,
                    clock=lambda: now[0],
                ),
            )
            recent = restarted.recent_tasks.get("cli:a")
            self.assertIsNotNone(recent)
            self.assertTrue(recent.recovered_from_checkpoint)
            self.assertEqual(recent.browser_snapshot, "")
            self.assertFalse(recent.browser_initialized)
            self.assertEqual(recent.browser_state["latest_snapshot"], "")

            output, resumed = await restarted.resume_recent_task(
                "cli:a", "继续", "user-a"
            )
            self.assertEqual(output, "continued")
            self.assertEqual(resumed.task_id, first_trace.task_id)

            now[0] += timedelta(seconds=11)
            expired = build_fake_agent(
                checkpoint_case([], output="unused"),
                checkpoint_store=ActiveTaskCheckpointStore(
                    workspace,
                    recent_task_ttl_seconds=10,
                    clock=lambda: now[0],
                ),
            )
            self.assertIsNone(expired.recent_tasks.get("cli:a"))
            self.assertEqual(expired.checkpoint_store.recent_count(), 0)

    async def test_recent_browser_task_expires_without_restart(self):
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store = ActiveTaskCheckpointStore(
                workspace, recent_task_ttl_seconds=10, clock=lambda: now[0]
            )
            agent = build_fake_agent(
                checkpoint_case(
                    [{"name": "browser_snapshot", "arguments": {}, "output": "page"}],
                    output="done",
                ),
                checkpoint_store=store,
            )
            await agent.run_traced(
                "inspect", [{"role": "user", "content": "inspect"}],
                session_key="cli:a", requester_sender_id="user-a",
            )
            self.assertIsNotNone(agent.recent_tasks.get("cli:a"))
            now[0] += timedelta(seconds=11)
            self.assertIsNone(agent.recent_tasks.get("cli:a"))
            self.assertEqual(store.recent_count(), 0)

    async def test_waiting_verification_task_state_restores_without_work(self):
        click = {
            "name": "browser_click",
            "arguments": {"target": "#submit"},
            "output": "clicked",
        }
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store = ActiveTaskCheckpointStore(workspace)
            first = build_fake_agent(
                checkpoint_case(
                    [click],
                    output="无法完成验证，任务尚未完成",
                ),
                checkpoint_store=store,
            )
            _, trace = await first.run_traced(
                "点击提交",
                [{"role": "user", "content": "点击提交"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            self.assertEqual(trace.task_status, "waiting_verification")
            self.assertEqual(store.active_count(), 1)

            restarted = build_fake_agent(
                checkpoint_case([], output="unused"),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )

            state = restarted.task_states[trace.task_id]
            self.assertEqual(state.status, AgentTaskStatus.WAITING_VERIFICATION)
            self.assertEqual(restarted.tools.execution_count, 0)
            self.assertEqual(
                len(restarted.client.chat.completions.requests),
                0,
            )
            recent = restarted.recent_tasks.get("cli:a")
            self.assertIsNotNone(recent)
            self.assertTrue(recent.recovered_from_checkpoint)
            self.assertEqual(recent.browser_snapshot, "")

    async def test_restarted_browser_approval_uses_fresh_precondition(self):
        approved_snapshot = (
            "- Page URL: https://example.com/editor\n"
            "- button '发布' [ref=e20]"
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = build_fake_agent(
                checkpoint_case(
                    [{"name": "browser_click", "arguments": {"target": "e20"}}]
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            await first.run_traced(
                "publish",
                [{"role": "user", "content": "publish"}],
                session_key="cli:a",
                browser_snapshot=approved_snapshot,
                browser_initialized=True,
                requester_sender_id="user-a",
            )

            restarted = build_fake_agent(
                checkpoint_case(
                    [
                        {
                            "name": "browser_snapshot",
                            "arguments": {},
                            "output": (
                                "- Page URL: https://example.com/editor\n"
                                "- button '删除账号' [ref=e20]"
                            ),
                        },
                        {
                            "name": "browser_click",
                            "arguments": {"target": "e20"},
                            "output": "must not execute",
                        },
                    ],
                    responses=[{"output": "unused"}],
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            pending = restarted.approvals.get("cli:a")
            self.assertIsNotNone(pending)
            self.assertFalse(pending.browser_initialized)
            output, trace = await restarted.resume_pending(
                "cli:a", "确认", "user-a"
            )
            self.assertIn("页面在确认期间发生了变化", output)
            self.assertEqual(trace.status, "failed")
            self.assertEqual(restarted.checkpoint_store.active_count(), 0)
            self.assertEqual(
                [name for name, _ in restarted.tools.executed_calls],
                ["browser_snapshot"],
            )
            refresh = next(
                call for call in trace.tool_calls
                if call.tool_name == "browser_snapshot"
            )
            self.assertTrue(refresh.metadata["runtime_precondition_check"])

    async def test_secret_is_not_persisted_and_action_is_non_resumable(self):
        secret = "plain-looking-password-value"
        snapshot = (
            "- Page URL: https://example.com/login\n"
            "- textbox 'Password' [ref=e7]"
        )
        browser_type = {
            "name": "browser_type",
            "arguments": {"target": "e7", "text": secret, "submit": True},
        }
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = build_fake_agent(
                checkpoint_case([browser_type]),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            await first.run_traced(
                "submit login",
                [
                    {
                        "role": "user",
                        "content": f"type this exact value: {secret}",
                    }
                ],
                session_key="cli:a",
                browser_snapshot=snapshot,
                requester_sender_id="user-a",
            )
            for checkpoint_file in (workspace / "checkpoints").iterdir():
                self.assertNotIn(secret.encode(), checkpoint_file.read_bytes())

            restarted = build_fake_agent(
                checkpoint_case(
                    [
                        {
                            "name": "browser_snapshot",
                            "arguments": {},
                            "output": snapshot,
                        },
                        browser_type,
                    ],
                    responses=[{"output": "unused"}],
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            pending = restarted.approvals.get("cli:a")
            self.assertIsNotNone(pending)
            self.assertFalse(pending.resumable)
            self.assertEqual(pending.arguments["text"], REDACTED)

            output, trace = await restarted.resume_pending(
                "cli:a", "确认", "user-a"
            )
            self.assertIn("cannot be safely resumed", output)
            self.assertEqual(trace.status, "failed")
            self.assertEqual(
                [name for name, _ in restarted.tools.executed_calls],
                ["browser_snapshot"],
            )
            self.assertEqual(restarted.checkpoint_store.active_count(), 0)

    async def test_secret_embedded_in_generic_argument_is_not_persisted(self):
        secret = "generic-command-secret-value"
        secret_exec = {
            "name": "exec",
            "arguments": {"command": f"deploy --token {secret}"},
            "output": "must not execute",
        }
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = build_fake_agent(
                checkpoint_case([secret_exec]),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            await first.run_traced(
                "deploy",
                [{"role": "user", "content": "deploy"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )

            for checkpoint_file in (workspace / "checkpoints").iterdir():
                self.assertNotIn(secret.encode(), checkpoint_file.read_bytes())

            restarted = build_fake_agent(
                checkpoint_case(
                    [secret_exec],
                    responses=[{"output": "unused"}],
                ),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            pending = restarted.approvals.get("cli:a")
            self.assertIsNotNone(pending)
            self.assertFalse(pending.resumable)
            self.assertEqual(pending.arguments["command"], REDACTED)

            output, _ = await restarted.resume_pending(
                "cli:a", "确认", "user-a"
            )
            self.assertIn("cannot be safely resumed", output)
            self.assertEqual(restarted.tools.execution_count, 0)

    async def test_cancelled_task_clears_active_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store, _ = await self.create_exec_approval(workspace)
            self.assertEqual(store.active_count(), 1)

            output, trace = await build_fake_agent(
                checkpoint_case([], output="unused"),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            ).resume_pending("cli:a", "取消", "user-a")

            self.assertIn("已取消操作", output)
            self.assertEqual(trace.task_status, "cancelled")
            self.assertEqual(store.active_count(), 0)

    async def test_corrupt_unsupported_and_disabled_storage_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store, _ = await self.create_exec_approval(workspace)
            with sqlite3.connect(store.path) as connection:
                connection.execute("UPDATE active_tasks SET payload_json='not-json'")
            corrupt = build_fake_agent(
                checkpoint_case([], output="unused"),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            self.assertIsNone(corrupt.approvals.get("cli:a"))
            self.assertEqual(corrupt.tools.execution_count, 0)
            self.assertEqual(corrupt.checkpoint_store.active_count(), 0)

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store = ActiveTaskCheckpointStore(workspace)
            with sqlite3.connect(store.path) as connection:
                connection.execute(
                    "UPDATE checkpoint_metadata SET value='999' "
                    "WHERE key='schema_version'"
                )
            unsupported = ActiveTaskCheckpointStore(workspace)
            self.assertFalse(unsupported.available)
            self.assertIn("unsupported", unsupported.last_error)

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            disabled = ActiveTaskCheckpointStore(workspace, enabled=False)
            agent = build_fake_agent(
                checkpoint_case([exec_call()], output="done"),
                checkpoint_store=disabled,
            )
            prompt, trace = await agent.run_traced(
                "commit",
                [{"role": "user", "content": "commit"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            self.assertEqual(trace.status, "awaiting_confirmation")
            self.assertIn("回复“确认”", prompt)
            output, _ = await agent.resume_pending(
                "cli:a", "确认", "user-a"
            )
            self.assertEqual(output, "done")
            self.assertEqual(agent.tools.execution_count, 1)
            self.assertFalse(disabled.path.exists())


if __name__ == "__main__":
    unittest.main()
