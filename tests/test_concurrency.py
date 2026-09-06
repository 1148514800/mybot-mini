from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from mybot.core.concurrency import SessionExecutionCoordinator
from mybot.tools import Tool, ToolRegistry, ToolResult
from mybot.tracing import AgentTracer


class _DelayedTool(Tool):
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    description = "test browser"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        await asyncio.sleep(0)
        return ToolResult(success=True, output="opened")


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_sessions_overlap_and_same_session_serializes(self):
        coordinator = SessionExecutionCoordinator(2)
        events: list[str] = []
        first_started = asyncio.Event()
        release_first = asyncio.Event()

        async def first():
            events.append("a1-start")
            first_started.set()
            await release_first.wait()
            events.append("a1-end")

        async def second():
            events.append("a2-start")
            events.append("a2-end")

        async def other():
            await first_started.wait()
            events.append("b-start")

        task_a1 = asyncio.create_task(coordinator.execute("a", first))
        await first_started.wait()
        task_a2 = asyncio.create_task(coordinator.execute("a", second))
        task_b = asyncio.create_task(coordinator.execute("b", other))
        await asyncio.sleep(0)
        self.assertIn("b-start", events)
        self.assertNotIn("a2-start", events)
        release_first.set()
        await asyncio.gather(task_a1, task_a2, task_b)
        self.assertLess(events.index("a1-end"), events.index("a2-start"))
        await coordinator.shutdown()

    async def test_tracer_context_isolation(self):
        tracer = AgentTracer(Path(tempfile.mkdtemp()))
        barrier = asyncio.Barrier(2)
        runs = {}

        async def run(key):
            run = tracer.start_run(key, metadata={"task_id": key})
            step = tracer.start_step(1)
            runs[key] = (run.run_id, step.step_id)
            await barrier.wait()
            self.assertEqual(tracer.get_current_run().run_id, run.run_id)
            self.assertEqual(tracer.get_current_step().step_id, step.step_id)
            tracer.finish_run(key)

        await asyncio.gather(run("a"), run("b"))
        self.assertNotEqual(runs["a"][0], runs["b"][0])

    async def test_browser_ownership_blocks_cross_session_and_releases_on_close(self):
        registry = ToolRegistry()
        registry.register(_DelayedTool("browser_open"))
        registry.register(_DelayedTool("browser_snapshot"))
        registry.register(_DelayedTool("browser_close"))
        opened = await registry.execute("browser_open", {}, session_key="a", task_id="t1")
        self.assertTrue(opened.success)
        blocked = await registry.execute("browser_snapshot", {}, session_key="b")
        self.assertFalse(blocked.success)
        self.assertEqual(blocked.metadata["error_type"], "browser_ownership_conflict")
        allowed = await registry.execute("browser_snapshot", {}, session_key="a")
        self.assertTrue(allowed.success)
        closed = await registry.execute("browser_close", {}, session_key="a")
        self.assertTrue(closed.success)
        reopened = await registry.execute("browser_open", {}, session_key="b")
        self.assertTrue(reopened.success)


if __name__ == "__main__":
    unittest.main()
