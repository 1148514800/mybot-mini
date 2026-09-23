from __future__ import annotations

import unittest

from mybot.agent.browser_reliability import BrowserTaskBudget, BrowserTaskState
from mybot.agent.tool_execution import (
    ToolExecutionContext,
    ToolExecutionPipeline,
    ToolExecutionRequest,
    ToolExecutionStatus,
)
from mybot.tools import BrowserResult, Tool, ToolRegistry, ToolResult
from mybot.tools.browser.session import BrowserLease
from mybot.tracing import AgentTracer


class CountingTool(Tool):
    def __init__(
        self,
        name: str,
        *,
        parameters: dict | None = None,
        result: ToolResult | None = None,
    ) -> None:
        self._name = name
        self._parameters = parameters or {
            "type": "object",
            "properties": {},
        }
        self.execution_count = 0
        self.executed_arguments: list[dict] = []
        self.result = result or ToolResult(success=True, output="ok")

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "count executions"

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs) -> ToolResult:
        self.execution_count += 1
        self.executed_arguments.append(dict(kwargs))
        return self.result


class ToolExecutionPipelineTests(unittest.IsolatedAsyncioTestCase):
    def build_pipeline(
        self,
        tool: CountingTool,
        *,
        extra_tools: tuple[CountingTool, ...] = (),
        debug_trace=None,
    ) -> tuple[ToolExecutionPipeline, AgentTracer]:
        registry = ToolRegistry()
        # Browser action tests model an already established trusted lease.
        registry.browser_ownership._lease = BrowserLease("cli:test")
        registry.register(tool)
        for extra_tool in extra_tools:
            registry.register(extra_tool)
        tracer = AgentTracer()
        return (
            ToolExecutionPipeline(
                registry,
                tracer,
                debug_trace=debug_trace,
            ),
            tracer,
        )

    @staticmethod
    def context(snapshot: str = "") -> ToolExecutionContext:
        return ToolExecutionContext(
            browser_snapshot=snapshot,
            browser_state=BrowserTaskState(latest_snapshot=snapshot),
            browser_budget=BrowserTaskBudget(),
        )

    @staticmethod
    def traced_request(
        tracer: AgentTracer,
        name: str,
        arguments,
        **overrides,
    ) -> ToolExecutionRequest:
        run = tracer.start_run("test", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)
        values = {
            "tool_name": name,
            "arguments": arguments,
            "session_key": "cli:test",
            "sender_id": "user-a",
            "task_id": run.metadata["task_id"],
            "model_tool_call_id": "call-1",
            "step_id": step.step_id,
        }
        values.update(overrides)
        return ToolExecutionRequest(**values)

    async def test_normal_success_executes_and_traces_once(self) -> None:
        tool = CountingTool(
            "read_file",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
        pipeline, tracer = self.build_pipeline(tool)
        request = self.traced_request(
            tracer,
            "read_file",
            {"path": "README.md"},
        )

        outcome = await pipeline.execute(request, self.context())

        self.assertEqual(outcome.status, ToolExecutionStatus.EXECUTED)
        self.assertTrue(outcome.tool_result.success)
        self.assertEqual(tool.execution_count, 1)
        self.assertEqual(len(tracer.get_current_run().tool_calls), 1)
        self.assertEqual(
            tracer.get_current_run().tool_calls[0].tool_name,
            "read_file",
        )

    async def test_unknown_and_invalid_arguments_do_not_execute(self) -> None:
        exec_tool = CountingTool(
            "exec",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        )
        pipeline, tracer = self.build_pipeline(exec_tool)

        unknown = await pipeline.execute(
            self.traced_request(tracer, "missing_tool", {}),
            self.context(),
        )
        self.assertEqual(unknown.status, ToolExecutionStatus.FAILED)
        self.assertIn("Unknown tool", unknown.tool_result.error)
        tracer.finish_step()
        tracer.finish_run()

        invalid = await pipeline.execute(
            self.traced_request(tracer, "exec", {"command": 123}),
            self.context(),
        )
        self.assertEqual(invalid.status, ToolExecutionStatus.FAILED)
        self.assertIn("must be string", invalid.tool_result.error)
        self.assertEqual(exec_tool.execution_count, 0)

    async def test_execution_guard_blocks_before_registry_call(self) -> None:
        exec_tool = CountingTool("exec")
        pipeline, tracer = self.build_pipeline(exec_tool)
        guard = ToolResult(
            success=False,
            error="Repeated identical tool call blocked.",
        )

        outcome = await pipeline.execute(
            self.traced_request(
                tracer,
                "exec",
                {"command": "git commit"},
                execution_guard=guard,
            ),
            self.context(),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertIs(outcome.tool_result, guard)
        self.assertEqual(exec_tool.execution_count, 0)

    async def test_wrong_browser_entry_tool_fails_before_registry_call(
        self,
    ) -> None:
        open_tool = CountingTool("browser_open")
        pipeline, tracer = self.build_pipeline(open_tool)

        outcome = await pipeline.execute(
            self.traced_request(tracer, "browser_attach", {}),
            self.context(),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertIn("browser_attach is blocked", outcome.tool_result.error)
        self.assertEqual(open_tool.execution_count, 0)

    async def test_browser_action_forces_runtime_session(self) -> None:
        snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=True,
                output="- Page URL: https://example.com",
                action="snapshot",
                session="managed_browser",
            ),
        )
        pipeline, tracer = self.build_pipeline(snapshot)

        await pipeline.execute(
            self.traced_request(
                tracer,
                "browser_snapshot",
                {"session": "local_browser"},
            ),
            self.context(),
        )

        self.assertEqual(
            snapshot.executed_arguments[0]["session"],
            "managed_browser",
        )

    async def test_skill_is_loaded_once_per_task(self) -> None:
        skill = CountingTool("read_file")
        pipeline, tracer = self.build_pipeline(skill)
        context = self.context()
        request = self.traced_request(
            tracer,
            "read_file",
            {"path": "skills/demo/SKILL.md"},
        )

        first = await pipeline.execute(request, context)
        second = await pipeline.execute(request, context)

        self.assertEqual(first.status, ToolExecutionStatus.EXECUTED)
        self.assertEqual(second.status, ToolExecutionStatus.EXECUTED)
        self.assertEqual(
            second.tool_result.metadata["execution_skipped"],
            "skill_already_loaded",
        )
        self.assertEqual(skill.execution_count, 1)

    async def test_stale_target_adds_recovery_snapshot(self) -> None:
        click = CountingTool(
            "browser_click",
            parameters={
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
            result=ToolResult(
                success=False,
                error="Ref e12 not found",
                metadata={
                    "error_type": "stale_target",
                    "recoverable": True,
                },
            ),
        )
        snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=True,
                output="- Page URL: https://example.com\nbutton Save [ref=e44]",
                action="snapshot",
                session="managed_browser",
            ),
        )
        pipeline, tracer = self.build_pipeline(
            click,
            extra_tools=(snapshot,),
        )
        context = self.context(
            "- Page URL: https://example.com\nbutton Save [ref=e12]"
        )
        context.browser_initialized = True

        outcome = await pipeline.execute(
            self.traced_request(tracer, "browser_click", {"target": "e12"}),
            context,
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.EXECUTED)
        self.assertEqual(click.execution_count, 1)
        self.assertEqual(snapshot.execution_count, 1)
        self.assertEqual(
            outcome.tool_result.metadata["recovery_action"],
            "browser_snapshot",
        )
        self.assertTrue(outcome.tool_result.metadata["recovery_succeeded"])

    async def test_pipeline_exception_becomes_tool_failure(self) -> None:
        class ExplodingTool(CountingTool):
            async def execute(self, **kwargs) -> ToolResult:
                raise RuntimeError("boom")

        exploding = ExplodingTool("exec")
        pipeline, tracer = self.build_pipeline(exploding)

        outcome = await pipeline.execute(
            self.traced_request(tracer, "exec", {}),
            self.context(),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.EXECUTED)
        self.assertFalse(outcome.tool_result.success)
        self.assertIn("boom", outcome.tool_result.error)


if __name__ == "__main__":
    unittest.main()
