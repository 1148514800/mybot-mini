from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mybot.agent.task_state import AgentTaskStatus
from mybot.storage.checkpoint import ActiveTaskCheckpointStore
from tests.fakes import FakeCase, build_fake_agent


def checkpoint_case(
    tools: list[dict],
    *,
    output: str = "task complete",
    responses: list[dict] | None = None,
) -> FakeCase:
    metadata = {"fake_tools": tools, "fake_output": output}
    if responses is not None:
        metadata["fake_response_sequence"] = responses
    return FakeCase(
        id="checkpoint",
        name="checkpoint",
        input="continue task",
        metadata=metadata,
    )


class ActiveTaskCheckpointTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_task_state_that_is_not_recent_is_discarded(self):
        click = {
            "name": "browser_click",
            "arguments": {"target": "#submit"},
            "output": "clicked",
        }
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            store = ActiveTaskCheckpointStore(workspace)
            first = build_fake_agent(
                checkpoint_case([click], output="无法完成验证，任务尚未完成"),
                checkpoint_store=store,
            )
            await first.run_traced(
                "点击提交",
                [{"role": "user", "content": "点击提交"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            self.assertEqual(store.active_count(), 1)
            store.clear_recent("cli:a")

            restarted = build_fake_agent(
                checkpoint_case([], output="unused"),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )

            self.assertEqual(restarted.task_states, {})
            self.assertEqual(store.active_count(), 0)

    async def test_corrupt_unsupported_and_disabled_storage_fail_closed(self):
        click = {
            "name": "browser_click",
            "arguments": {"target": "#submit"},
            "output": "clicked",
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            workspace = Path(directory)
            store = ActiveTaskCheckpointStore(workspace)
            agent = build_fake_agent(
                checkpoint_case([click], output="无法完成验证，任务尚未完成"),
                checkpoint_store=store,
            )
            await agent.run_traced(
                "点击提交",
                [{"role": "user", "content": "点击提交"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            with sqlite3.connect(store.path) as connection:
                connection.execute("UPDATE active_tasks SET payload_json=\'not-json\'")
            corrupt = build_fake_agent(
                checkpoint_case([], output="unused"),
                checkpoint_store=ActiveTaskCheckpointStore(workspace),
            )
            self.assertEqual(corrupt.task_states, {})
            self.assertEqual(corrupt.tools.execution_count, 0)
            self.assertEqual(corrupt.checkpoint_store.active_count(), 0)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            workspace = Path(directory)
            store = ActiveTaskCheckpointStore(workspace)
            with sqlite3.connect(store.path) as connection:
                connection.execute(
                    "UPDATE checkpoint_metadata SET value=\'999\' "
                    "WHERE key=\'schema_version\'"
                )
            unsupported = ActiveTaskCheckpointStore(workspace)
            self.assertFalse(unsupported.available)
            self.assertIn("unsupported", unsupported.last_error)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            workspace = Path(directory)
            disabled = ActiveTaskCheckpointStore(workspace, enabled=False)
            agent = build_fake_agent(
                checkpoint_case(
                    [{"name": "read_file", "arguments": {"path": "notes.txt"}}],
                    output="done",
                ),
                checkpoint_store=disabled,
            )
            output, trace = await agent.run_traced(
                "读取文件",
                [{"role": "user", "content": "读取文件"}],
                session_key="cli:a",
                requester_sender_id="user-a",
            )
            self.assertEqual(trace.status, "success")
            self.assertEqual(output, "done")
            self.assertEqual(agent.tools.execution_count, 1)
            self.assertFalse(disabled.path.exists())


if __name__ == "__main__":
    unittest.main()
