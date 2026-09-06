from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from mybot.agent.browser_reliability import BrowserTaskBudget, BrowserTaskState
from mybot.agent.tool_execution import (
    ToolExecutionContext,
    ToolExecutionPipeline,
    ToolExecutionRequest,
    ToolExecutionStatus,
)
from mybot.guardrails import ApprovalManager, ToolPolicy
from mybot.tools import BrowserResult, Tool, ToolRegistry, ToolResult
from mybot.tools.browser.session import BrowserLease
from mybot.tracing import AgentTracer, REDACTED


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
        approvals: ApprovalManager | None = None,
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
                ToolPolicy(),
                approvals or ApprovalManager(),
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
            tracer.get_current_run().tool_calls[0].metadata["policy_decision"],
            "allow",
        )

    async def test_confirmation_creates_pending_without_execution(self) -> None:
        tool = CountingTool(
            "exec",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        )
        pipeline, tracer = self.build_pipeline(tool)
        request = self.traced_request(
            tracer,
            "exec",
            {"command": "git commit -m test"},
        )

        outcome = await pipeline.execute(request, self.context())

        self.assertEqual(outcome.status, ToolExecutionStatus.WAITING_APPROVAL)
        self.assertIsNotNone(outcome.pending_approval)
        self.assertEqual(tool.execution_count, 0)
        self.assertEqual(len(tracer.get_current_run().tool_calls), 1)

    async def test_approved_execution_uses_frozen_arguments_once(self) -> None:
        tool = CountingTool(
            "exec",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        )
        pipeline, tracer = self.build_pipeline(tool)
        original = {"command": "git commit -m exact"}
        request = self.traced_request(tracer, "exec", original)
        pending_outcome = await pipeline.execute(request, self.context())
        pending = pending_outcome.pending_approval
        self.assertEqual(tool.execution_count, 0)
        tracer.finish_step()
        tracer.finish_run()

        approved = pipeline.approvals.approve(
            "cli:test",
            pending.approval_id,
            "user-a",
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)
        resume_request = ToolExecutionRequest(
            tool_name="exec",
            arguments={"command": "git commit -m changed"},
            session_key="cli:test",
            sender_id="user-a",
            task_id="task-1",
            model_tool_call_id="call-1",
            step_id=step.step_id,
        )

        outcome = await pipeline.execute_approved(
            approved,
            resume_request,
            self.context(),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.EXECUTED)
        self.assertEqual(tool.execution_count, 1)
        self.assertEqual(tool.executed_arguments, [original])
        self.assertEqual(len(tracer.get_current_run().tool_calls), 1)

    async def test_invalid_sender_and_expired_approval_never_execute(self) -> None:
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        approvals = ApprovalManager(ttl_seconds=600, clock=lambda: now[0])
        tool = CountingTool("exec")
        pipeline, tracer = self.build_pipeline(tool, approvals=approvals)
        request = self.traced_request(
            tracer,
            "exec",
            {"command": "git push"},
        )
        pending = (await pipeline.execute(request, self.context())).pending_approval

        self.assertIsNone(
            approvals.approve("cli:test", pending.approval_id, "user-b")
        )
        self.assertEqual(tool.execution_count, 0)
        self.assertIs(approvals.get("cli:test"), pending)

        now[0] += timedelta(seconds=601)
        self.assertIs(approvals.expire("cli:test"), pending)
        self.assertEqual(pending.status, "expired")
        self.assertEqual(tool.execution_count, 0)

    async def test_consumed_approval_is_rechecked_for_ttl_before_execution(
        self,
    ) -> None:
        now = [datetime(2026, 9, 5, tzinfo=UTC)]
        approvals = ApprovalManager(ttl_seconds=600, clock=lambda: now[0])
        tool = CountingTool("exec")
        pipeline, tracer = self.build_pipeline(tool, approvals=approvals)
        request = self.traced_request(
            tracer,
            "exec",
            {"command": "git push"},
        )
        pending = (await pipeline.execute(request, self.context())).pending_approval
        approved = approvals.approve(
            "cli:test",
            pending.approval_id,
            "user-a",
        )
        tracer.finish_step()
        tracer.finish_run()
        now[0] += timedelta(seconds=601)
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="exec",
                arguments={"command": "ignored"},
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertIn("expired", outcome.tool_result.error)
        self.assertEqual(tool.execution_count, 0)

    async def test_blocked_unknown_and_invalid_arguments_do_not_execute(self) -> None:
        exec_tool = CountingTool(
            "exec",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        )
        pipeline, tracer = self.build_pipeline(exec_tool)
        blocked = await pipeline.execute(
            self.traced_request(
                tracer,
                "exec",
                {"command": "rm -rf /"},
            ),
            self.context(),
        )
        self.assertEqual(blocked.status, ToolExecutionStatus.BLOCKED)
        self.assertEqual(exec_tool.execution_count, 0)
        tracer.finish_step()
        tracer.finish_run()

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

    async def test_approved_browser_action_fails_if_snapshot_changed(self) -> None:
        tool = CountingTool(
            "browser_click",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "session": {"type": "string"},
                },
                "required": ["target"],
            },
        )
        pipeline, tracer = self.build_pipeline(tool)
        snapshot = (
            "- Page URL: https://example.com/editor\n"
            "- button '发布' [ref=e20]"
        )
        request = self.traced_request(
            tracer,
            "browser_click",
            {"target": "e20"},
        )
        pending = (
            await pipeline.execute(request, self.context(snapshot))
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test",
            pending.approval_id,
            "user-a",
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)
        resume_request = ToolExecutionRequest(
            tool_name=pending.tool_name,
            arguments=pending.arguments,
            session_key="cli:test",
            sender_id="user-a",
            task_id="task-1",
            step_id=step.step_id,
        )

        outcome = await pipeline.execute_approved(
            approved,
            resume_request,
            self.context("- Page URL: https://example.com/other"),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertEqual(tool.execution_count, 0)
        self.assertEqual(
            outcome.tool_result.metadata["approval_status"],
            "precondition_failed",
        )

    async def test_live_browser_click_precondition_passes_without_full_snapshot_match(
        self,
    ) -> None:
        click = CountingTool("browser_click")
        approved_snapshot = (
            "- Page URL: https://example.com/editor\n"
            "- paragraph 'dynamic count: 1'\n"
            "- button '发布' [ref=e20]"
        )
        fresh_snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=True,
                output=(
                    "- Page URL: https://example.com/editor\n"
                    "- paragraph 'dynamic count: 2'\n"
                    "- button '发布' [ref=e20]"
                ),
                action="snapshot",
                session="managed_browser",
                url="https://example.com/editor",
            ),
        )
        pipeline, tracer = self.build_pipeline(
            click,
            extra_tools=(fresh_snapshot,),
        )
        pending = (
            await pipeline.execute(
                self.traced_request(
                    tracer,
                    "browser_click",
                    {"target": "e20"},
                ),
                self.context(approved_snapshot),
            )
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test", pending.approval_id, "user-a"
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="browser_click",
                arguments={"target": "e20"},
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(approved_snapshot),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.EXECUTED)
        self.assertEqual(fresh_snapshot.execution_count, 1)
        self.assertEqual(click.execution_count, 1)
        self.assertEqual(
            outcome.tool_result.metadata["precondition_result"], "passed"
        )
        refresh_trace = next(
            call
            for call in tracer.get_current_run().tool_calls
            if call.metadata.get("runtime_precondition_check")
            and call.tool_name == "browser_snapshot"
        )
        self.assertTrue(refresh_trace.metadata["runtime_internal"])
        self.assertEqual(refresh_trace.metadata["precondition_result"], "passed")

    async def test_live_browser_click_fails_for_missing_or_changed_target(
        self,
    ) -> None:
        approved_snapshot = (
            "- Page URL: https://example.com/editor\n"
            "- button '发布' [ref=e20]"
        )
        for fresh_output, expected_reason in (
            ("- Page URL: https://example.com/editor", "target_missing"),
            (
                "- Page URL: https://example.com/editor\n"
                "- button '删除账号' [ref=e20]",
                "target_changed",
            ),
        ):
            with self.subTest(reason=expected_reason):
                click = CountingTool("browser_click")
                snapshot = CountingTool(
                    "browser_snapshot",
                    result=BrowserResult(
                        success=True,
                        output=fresh_output,
                        action="snapshot",
                        session="managed_browser",
                        url="https://example.com/editor",
                    ),
                )
                pipeline, tracer = self.build_pipeline(
                    click,
                    extra_tools=(snapshot,),
                )
                pending = (
                    await pipeline.execute(
                        self.traced_request(
                            tracer,
                            "browser_click",
                            {"target": "e20"},
                        ),
                        self.context(approved_snapshot),
                    )
                ).pending_approval
                tracer.finish_step()
                tracer.finish_run()
                approved = pipeline.approvals.approve(
                    "cli:test", pending.approval_id, "user-a"
                )
                tracer.start_run("confirm", metadata={"task_id": "task-1"})
                step = tracer.start_step(1)

                outcome = await pipeline.execute_approved(
                    approved,
                    ToolExecutionRequest(
                        tool_name="browser_click",
                        arguments=pending.arguments,
                        session_key="cli:test",
                        sender_id="user-a",
                        task_id="task-1",
                        step_id=step.step_id,
                    ),
                    self.context(approved_snapshot),
                )

                self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
                self.assertEqual(click.execution_count, 0)
                self.assertEqual(
                    outcome.tool_result.metadata["approval_status"],
                    "precondition_failed",
                )
                self.assertEqual(
                    outcome.tool_result.metadata["precondition_reason"],
                    expected_reason,
                )

    async def test_live_browser_click_fails_when_url_changes(self) -> None:
        click = CountingTool("browser_click")
        approved_snapshot = (
            "- Page URL: https://example.com/editor\n"
            "- button '发布' [ref=e20]"
        )
        snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=True,
                output=(
                    "- Page URL: https://example.com/account/delete\n"
                    "- button '发布' [ref=e20]"
                ),
                action="snapshot",
                session="managed_browser",
                url="https://example.com/account/delete",
            ),
        )
        pipeline, tracer = self.build_pipeline(click, extra_tools=(snapshot,))
        pending = (
            await pipeline.execute(
                self.traced_request(
                    tracer, "browser_click", {"target": "e20"}
                ),
                self.context(approved_snapshot),
            )
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test", pending.approval_id, "user-a"
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="browser_click",
                arguments=pending.arguments,
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(approved_snapshot),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertEqual(click.execution_count, 0)
        self.assertEqual(
            outcome.tool_result.metadata["precondition_reason"], "url_changed"
        )

    async def test_live_browser_click_fails_when_snapshot_refresh_fails(
        self,
    ) -> None:
        click = CountingTool("browser_click")
        approved_snapshot = (
            "- Page URL: https://example.com/editor\n"
            "- button '发布' [ref=e20]"
        )
        snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=False,
                error="browser closed",
                action="snapshot",
                session="managed_browser",
            ),
        )
        pipeline, tracer = self.build_pipeline(click, extra_tools=(snapshot,))
        pending = (
            await pipeline.execute(
                self.traced_request(
                    tracer, "browser_click", {"target": "e20"}
                ),
                self.context(approved_snapshot),
            )
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test", pending.approval_id, "user-a"
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="browser_click",
                arguments=pending.arguments,
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(approved_snapshot),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertEqual(click.execution_count, 0)
        self.assertEqual(
            outcome.tool_result.metadata["precondition_reason"],
            "snapshot_refresh_failed",
        )

    async def test_live_browser_type_changed_target_fails_without_text_leak(
        self,
    ) -> None:
        secret_text = "plain-looking-password-value"
        debug_messages: list[str] = []
        browser_type = CountingTool("browser_type")
        approved_snapshot = (
            "- Page URL: https://example.com/login\n"
            "- textbox 'Password' [ref=e7]"
        )
        snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=True,
                output=(
                    "- Page URL: https://example.com/login\n"
                    "- button 'Delete account' [ref=e7]"
                ),
                action="snapshot",
                session="managed_browser",
                url="https://example.com/login",
            ),
        )
        pipeline, tracer = self.build_pipeline(
            browser_type,
            extra_tools=(snapshot,),
            debug_trace=debug_messages.append,
        )
        pending = (
            await pipeline.execute(
                self.traced_request(
                    tracer,
                    "browser_type",
                    {"target": "e7", "text": secret_text, "submit": True},
                ),
                self.context(approved_snapshot),
            )
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test", pending.approval_id, "user-a"
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="browser_type",
                arguments=pending.arguments,
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(approved_snapshot),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertEqual(browser_type.execution_count, 0)
        self.assertEqual(
            outcome.tool_result.metadata["precondition_reason"],
            "target_changed",
        )
        rendered_trace = str(tracer.get_current_run().tool_calls)
        self.assertNotIn(secret_text, rendered_trace)
        self.assertIn(REDACTED, rendered_trace)
        self.assertNotIn(secret_text, "\n".join(debug_messages))
        self.assertNotIn(secret_text, outcome.tool_result.to_text())

    async def test_live_browser_press_fails_closed_without_focus_context(
        self,
    ) -> None:
        press = CountingTool("browser_press")
        snapshot_text = "- Page URL: https://example.com/editor"
        snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=True,
                output=snapshot_text,
                action="snapshot",
                session="managed_browser",
                url="https://example.com/editor",
            ),
        )
        pipeline, tracer = self.build_pipeline(press, extra_tools=(snapshot,))
        pending = (
            await pipeline.execute(
                self.traced_request(
                    tracer, "browser_press", {"key": "Enter"}
                ),
                self.context(snapshot_text),
            )
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test", pending.approval_id, "user-a"
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="browser_press",
                arguments=pending.arguments,
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(snapshot_text),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.FAILED)
        self.assertEqual(snapshot.execution_count, 1)
        self.assertEqual(press.execution_count, 0)
        self.assertEqual(
            outcome.tool_result.metadata["precondition_reason"],
            "unsupported_precondition",
        )

    async def test_live_browser_eval_requires_same_session_and_url(self) -> None:
        browser_eval = CountingTool("browser_eval")
        snapshot_text = "- Page URL: https://example.com/editor"
        snapshot = CountingTool(
            "browser_snapshot",
            result=BrowserResult(
                success=True,
                output=snapshot_text,
                action="snapshot",
                session="managed_browser",
                url="https://example.com/editor",
            ),
        )
        pipeline, tracer = self.build_pipeline(
            browser_eval,
            extra_tools=(snapshot,),
        )
        pending = (
            await pipeline.execute(
                self.traced_request(
                    tracer,
                    "browser_eval",
                    {"script": "() => location.href"},
                ),
                self.context(snapshot_text),
            )
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test", pending.approval_id, "user-a"
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="browser_eval",
                arguments=pending.arguments,
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(snapshot_text),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.EXECUTED)
        self.assertEqual(snapshot.execution_count, 1)
        self.assertEqual(browser_eval.execution_count, 1)
        self.assertEqual(
            outcome.tool_result.metadata["precondition_result"], "passed"
        )

    async def test_non_browser_approval_does_not_refresh_browser_snapshot(
        self,
    ) -> None:
        exec_tool = CountingTool("exec")
        snapshot = CountingTool("browser_snapshot")
        pipeline, tracer = self.build_pipeline(
            exec_tool,
            extra_tools=(snapshot,),
        )
        pending = (
            await pipeline.execute(
                self.traced_request(
                    tracer, "exec", {"command": "git commit -m exact"}
                ),
                self.context(),
            )
        ).pending_approval
        tracer.finish_step()
        tracer.finish_run()
        approved = pipeline.approvals.approve(
            "cli:test", pending.approval_id, "user-a"
        )
        tracer.start_run("confirm", metadata={"task_id": "task-1"})
        step = tracer.start_step(1)

        outcome = await pipeline.execute_approved(
            approved,
            ToolExecutionRequest(
                tool_name="exec",
                arguments={"command": "ignored"},
                session_key="cli:test",
                sender_id="user-a",
                task_id="task-1",
                step_id=step.step_id,
            ),
            self.context(),
        )

        self.assertEqual(outcome.status, ToolExecutionStatus.EXECUTED)
        self.assertEqual(exec_tool.execution_count, 1)
        self.assertEqual(snapshot.execution_count, 0)


if __name__ == "__main__":
    unittest.main()
