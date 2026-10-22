from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from openai import APITimeoutError, AsyncOpenAI
from ..provider_failover import FallbackBudgetExceeded

from ..config import GatewayConfig
from ..tools import ToolRegistry, ToolResult
from ..storage.session_store import SessionStore
from .context import ContextBuilder
from .session import Session
from .planning import Plan, PlanningTool
from .context_manager import ContextManager, ContextBudgetError
from ..skills.registry import SkillRegistry
from ..tools.skill import SkillTool
from ..mcp_client.discovery import MCPToolCatalog, DiscoveryTool
from ..mcp_client.router import AdaptiveToolRouter


class AgentLoop:
    """Run a simple tool-calling loop for one CLI conversation."""

    def __init__(self, client: AsyncOpenAI, config: GatewayConfig, tools: ToolRegistry,
                 context: ContextBuilder, session: Session | None = None, *, undo_approval_provider=None):
        self.client = client
        self.config = config
        self.tools = tools
        self.context = context
        self.skills = SkillRegistry(config.skills_path) if config.skills_enabled else None
        self.context.skill_index = self.skills.index() if self.skills is not None else []
        if self.skills is not None:
            for name in ("load_skill", "read_skill_reference"):
                self.tools.register(SkillTool(self.skills, name))
        self.context_manager = ContextManager(config)
        self.session = session if session is not None else Session(config.session_max_turns)
        self.store = SessionStore(config.session_path, config.workspace) if config.session_persist else None
        if self.store is not None:
            self.session.restore(self.store.load())
        self.coding_controller = None
        self.last_coding_report = None
        self._git_capsule = None
        self._active_journal = None
        self._undo_provider = undo_approval_provider
        self._undo_notice = False
        self.plan = Plan()
        for name in ("create_plan", "update_plan"):
            self.tools.register(PlanningTool(self.plan, name))
        self.discovery = MCPToolCatalog(tools, config.mcp_discovery) if config.mcp_discovery['enabled'] else None
        self.router = (AdaptiveToolRouter(self.discovery) if self.discovery is not None
                       and config.mcp_discovery.get('routing_mode','manual') == 'adaptive' else None)
        self.routing_decision = None
        self.routing_diagnostics = None
        self._request_visible_names = frozenset()
        if self.discovery is not None:
            if any(self.tools.has_tool(name) for name in self.discovery.tool_names):
                raise ValueError('MCP discovery tool name collision')
            for name in sorted(self.discovery.tool_names):
                self.tools.register(DiscoveryTool(self.discovery,name))

    async def run(self) -> None:
        while True:
            try:
                user_input = (await asyncio.to_thread(input, "You: ")).strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                return
            try:
                reply = await self.handle_message(user_input)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                print(f"\nBot: 运行时错误: {type(exc).__name__}: {exc}\n")
                continue
            print(f"\nBot: {reply}\n")

    async def handle_message(self, user_input: str) -> str:
        if self.config.coding_git_workflow['enabled']:
            command = user_input.strip()
            if command in ('/changes', '/undo'):
                return await self._git_cli(command)
            if self._git_capsule is not None: self._git_capsule.close()
            self._git_capsule = None
            if command == '/clear': self._undo_notice = False
        if self.discovery is not None:self.discovery.reset()
        self._request_visible_names = frozenset()
        self.routing_decision = None
        self.routing_diagnostics = None
        self.plan.reset(user_input)
        self.context_clipped = False
        self.context_history_omitted = False
        from .coding_controller import CodingTaskController, AutonomySettings
        from ..tools.run_command import RunCommandTool
        self.last_coding_report = None
        self.coding_controller = (CodingTaskController(AutonomySettings(**self.config.coding_autonomy), self.tools)
            if self.config.coding_autonomy['enabled'] and user_input.strip() != '/clear' else None)
        command = self.tools.get_tool('run_command')
        old_guard = command.execution_guard if type(command) is RunCommandTool else None
        if self.coding_controller is not None and type(command) is RunCommandTool:
            controller_guard = self.coding_controller.command_guard
            def task_guard(launch, timeout):
                if old_guard is not None: timeout = min(timeout, old_guard(launch, timeout))
                return controller_guard(launch, timeout)
            command.execution_guard = task_guard
        try:
            reply = await self._handle_message(user_input)
            if self.context_clipped:
                reply = "[CONTEXT] 本轮部分工具结果仅提供节选，未验证全文阅读或分析。以下模型回复不能视为完整任务结论：\n" + reply
            if self.context_history_omitted:
                reply = "[CONTEXT] 部分历史已省略，预算不足以提供其摘要。\n" + reply
            return reply
        except BaseException as exc:
            if self._active_journal is not None:
                self._active_journal.close()
                self._git_capsule = None
            if self.coding_controller is not None:
                self.coding_controller.stop('cancelled' if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)) else 'execution_uncertain', 'task_interrupted')
                self.last_coding_report = self.coding_controller.snapshot()
            report = self.plan.close("上下文预算不足" if isinstance(exc, ContextBudgetError) else "任务异常或中断")
            if report:
                print(report)
            raise
        finally:
            if type(command) is RunCommandTool: command.execution_guard = old_guard
            self.coding_controller = None
            if self._active_journal is not None:
                self._active_journal.patch_tool.observer = None
                self._active_journal = None
            if self.discovery is not None:self.discovery.reset()
            self._request_visible_names = frozenset()
            self.routing_decision = None

    def _route_initial_tools(self, user_input, messages, turns):
        decision = self.router.route(user_input,messages=messages,turns=turns,plan=self.plan,context_manager=self.context_manager)
        self.discovery.apply_preselection(decision.selected_tool_names)
        self.routing_decision = decision
        self.routing_diagnostics = decision.diagnostics()

    async def _handle_message(self, user_input: str) -> str:
        if user_input.strip() == "/clear":
            if self.store is not None:
                self.store.clear()
            self.session.clear()
            self.plan.reset()
            return "当前会话已清空。"
        messages = self.context.build_messages(user_input, self.session.history())
        if self.config.coding_git_workflow['enabled']:
            from .git_workflow import GitBaseline, GitWorkflowSettings
            from .change_journal import ChangeJournal
            from ..tools.patch import ApplyPatchTool
            from ..tools.run_command import RunCommandTool
            patch_tool = self.tools.get_tool('apply_patch')
            try:
                if type(patch_tool) is not ApplyPatchTool or self.tools.has_tool('write_file'):
                    raise ValueError('patch_only_registry_required')
                if patch_tool.workspace != self.config.workspace or patch_tool.patch_mode != 'write' or patch_tool.observer is not None:
                    raise ValueError('native_patch_required')
                if self.config.coding_git_workflow['undo_enabled']:
                    self._validate_undo_registry()
                baseline = await GitBaseline.capture(self.config.workspace)
                self._active_journal = ChangeJournal(baseline, patch_tool,
                    GitWorkflowSettings(**self.config.coding_git_workflow),
                    external_side_effects_possible=self.config.mcp_enabled or self.config.coding_command['mode'] == 'host_confirm')
                patch_tool.observer = self._active_journal
                if self._undo_notice:
                    messages[0]['content'] += '\nPrevious task verification is invalid after Undo or external changes; old Session text is not current evidence.'
            except (OSError, ValueError):
                self.coding_controller.stop('blocked', 'git_baseline_or_registry_unavailable')
                return self._finish_turn(messages, len(messages) - 1, '')
        turns = self.session.export_turns()
        turn_start = len(messages) - 1
        if self.router is not None:self._route_initial_tools(user_input,messages,turns)
        limit = max(1, min(self.config.max_react_steps, 30))
        debug = self.config.debug
        controller = self.coding_controller
        base_system = messages[0]["content"]
        for step in range(1, limit + 1):
            if controller is not None:
                messages[0]['content'] = base_system + controller.instruction()
            visible = self.discovery.visible_names() if self.discovery is not None else None
            definitions = self.tools.get_definitions(visible) or None
            # Freeze what THIS response may execute; activation cannot change it mid-batch.
            self._request_visible_names = frozenset(item['function']['name'] for item in definitions or [])
            llm_messages, stats = self.context_manager.prepare(messages, definitions, turns, self.plan)
            self.context_clipped = self.context_clipped or stats["current_clipped"]
            self.context_history_omitted = self.context_history_omitted or stats.get("history_omitted", False)
            if debug and self.config.context_enabled:
                print(f"[CONTEXT] chars={stats['before']}->{stats['after']} max={self.config.context_max_chars}")
            if controller is not None and not controller.before_request(definitions):
                return await self._complete_turn(messages, turn_start, '', controller.stop_reason)
            start = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.config.model,
                        messages=llm_messages,
                        tools=definitions,
                        temperature=0.1,
                        max_tokens=self.config.max_completion_tokens,
                    ),
                    timeout=(min(self.config.request_timeout_seconds, max(.001, controller.remaining_seconds))
                             if controller is not None else max(1.0, self.config.request_timeout_seconds)),
                )
            except FallbackBudgetExceeded:
                return await self._complete_turn(messages, turn_start, '', controller.stop_reason)
            except (TimeoutError, APITimeoutError):
                if controller is not None:
                    controller.check_time()
                    controller.stop('blocked', 'model_request_timeout')
                    return await self._complete_turn(messages, turn_start, '', controller.stop_reason)
                report = self.plan.close("模型请求超时")
                return f"模型请求超时（{self.config.request_timeout_seconds:g} 秒）。" + (f"\n{report}" if report else "")

            message = response.choices[0].message
            if debug:
                print(
                    f"[LLM {step}] time={time.perf_counter() - start:.2f}s "
                    f"tokens={response.usage.total_tokens if response.usage else '?'} "
                    f"tool_calls={len(message.tool_calls or [])}"
                )
            if not message.tool_calls:
                reply = (message.content or "").strip() or "模型没有返回文本。"
                if controller is not None and controller.needs_continuation():
                    continue
                return await self._complete_turn(messages, turn_start, reply)

            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {"id": call.id, "type": "function", "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    }}
                    for call in message.tool_calls
                ],
            })
            batch_allowed = controller.before_batch(message.tool_calls) if controller is not None else True
            permission_denied = False
            command_stopped = False
            for call in message.tool_calls:
                if debug:
                    if getattr(self.tools.get_tool(call.function.name), 'private_arguments', False):
                        args = '<Coding arguments omitted>'
                    else:
                        try:
                            args = json.loads(call.function.arguments or "{}")
                        except json.JSONDecodeError:
                            args = "<invalid JSON>"
                        if isinstance(args, dict) and "content" in args:
                            args["content"] = f"<{len(str(args['content']))} chars>"
                        if call.function.name.startswith("mcp__") or (self.discovery is not None and call.function.name in self.discovery.tool_names):
                            args = "<MCP arguments omitted>"
                    print(f"[CALL] {call.function.name}: {args}")
                was_stopped = permission_denied or command_stopped
                if controller is not None and (not batch_allowed or controller.state != 'running'):
                    messages.append({'role': 'tool', 'tool_call_id': call.id, 'content':
                        ToolResult(False, error='autonomy_stopped', metadata={'reason': controller.stop_reason, 'executed': False}).to_text()})
                    continue
                if controller is not None and not controller.before_tool(call.function.name, call.function.arguments):
                    messages.append({'role': 'tool', 'tool_call_id': call.id, 'content':
                        ToolResult(False, error='autonomy_stopped', metadata={'reason': controller.stop_reason, 'executed': False}).to_text()})
                    continue
                result = (ToolResult(success=False,error="approval_cancelled: earlier call denied")
                          if permission_denied or command_stopped else await self._execute(call.function.name, call.function.arguments))
                if controller is not None and not was_stopped:
                    controller.observe(call.function.name, call.function.arguments, result)
                from ..tools.run_command import RunCommandTool
                native_command = (call.function.name == 'run_command' and type(self.tools.get_tool(call.function.name)) is RunCommandTool)
                command_stopped = command_stopped or (native_command and not was_stopped and not result.success and result.metadata.get('completed') is not True)
                permission_denied = permission_denied or result.metadata.get("permission_denied",False)
                if debug:
                    print(
                        f"[RESULT] success={result.success} "
                        f"chars={len(result.output)} error={result.error}"
                    )
                messages.append({
                    "role": "tool", "tool_call_id": call.id, "content": result.to_text(),
                })

            if controller is not None and controller.state != 'running':
                return await self._complete_turn(messages, turn_start, '', controller.stop_reason)
            if command_stopped:
                return await self._complete_turn(messages, turn_start,
                    '原生命令未完成或未获批准，本轮任务已停止；后续工具未执行。已执行命令可能已有副作用。', '原生命令停止')
            if permission_denied:
                return await self._complete_turn(messages, turn_start,
                    "MCP 操作未获批准，本轮任务已停止；后续工具未执行。已执行的操作不会自动回滚。", "工具审批拒绝")

        return await self._complete_turn(messages, turn_start, f"已达到单次任务的 {limit} 步上限。", "达到 ReAct 上限")

    async def _complete_turn(self, messages, turn_start, reply, reason=''):
        if self._active_journal is not None:
            await self._active_journal.refresh()
        return self._finish_turn(messages, turn_start, reply, reason)

    def _validate_undo_registry(self):
        from ..tools.file import ReadFileTool
        from ..tools.list_files import ListFilesTool
        from ..tools.search_code import SearchCodeTool
        from ..tools.read_file_range import ReadFileRangeTool
        from ..tools.git_tools import GitStatusTool, GitDiffTool
        from ..tools.patch import ApplyPatchTool
        from ..tools.run_command import RunCommandTool
        allowed = {ReadFileTool, ListFilesTool, SearchCodeTool, ReadFileRangeTool, GitStatusTool, GitDiffTool,
                   ApplyPatchTool, RunCommandTool, PlanningTool, SkillTool, DiscoveryTool}
        if any(type(t) not in allowed for t in self.tools.iter_tools()): raise ValueError('unsupported_undo_registry')
        native = self.tools.get_tool('run_command')
        if type(native) is not RunCommandTool or native.settings.mode != 'macos_readonly':
            raise ValueError('readonly_command_required')

    async def _git_cli(self, command):
        journal = self._git_capsule
        if journal is None: return 'undo_unavailable: no recent task capsule'
        if command == '/changes':
            await journal.refresh()
            state = journal.summary()
            if (not state['git_metadata_unchanged'] or any(not f.get('current_matches', True) for f in state['files'])):
                self._invalidate_coding_review('stale_review')
            return journal.review()
        from ..tools.undo import UndoService
        result = await UndoService(journal, self._undo_provider).undo()
        if result.get('verification_invalidated'):
            self._invalidate_coding_review(result['undo_status'],
                changed=result.get('files_may_have_changed', False), uncertain=result['undo_status'] == 'undo_partial_failure_possible')
        return json.dumps(result, ensure_ascii=True) + ('\n此前修复的测试记录不再适用于当前内容；未自动复测。' if result.get('verification_invalidated') else '')

    def _invalidate_coding_review(self, reason, *, changed=False, uncertain=False):
        self._undo_notice = True
        if self.last_coding_report is not None:
            self.last_coding_report = {**self.last_coding_report,
                'state': 'execution_uncertain' if uncertain else 'edited_unverified',
                'verification': 'invalid', 'tests_passed_after_last_patch': 0,
                'current_revision': self.last_coding_report['current_revision'] + int(changed),
                'stop_reason': reason, 'undo_status': reason, 'verification_invalidated': True}

    def _finish_turn(self, messages: list[dict[str, Any]], turn_start: int, reply: str,
                     reason: str = "") -> str:
        controller = self.coding_controller
        if controller is not None:
            reply = controller.finish(reason)
            self.last_coding_report = controller.snapshot()
        report = self.plan.close(reason)
        if report and controller is None:
            reply = f"{reply}\n{report}" if reason else report
        if self._active_journal is not None:
            self._git_capsule = self._active_journal
            reply += '\n[TASK CHANGE SUMMARY]\n' + self._active_journal.summary_text(4000)
        messages.append({"role": "assistant", "content": reply})
        if self.store is not None:
            turns = self.session.export_turns() + [messages[turn_start:]]
            self.store.save(turns[-self.session.max_turns:])
        self.session.add_turn(messages[turn_start:])
        return reply

    async def _execute(self, name: str, raw_arguments: Any) -> ToolResult:
        if self.tools.is_metadata(name):
            return await self._execute_tool(name, raw_arguments)
        error = self.plan.execution_error()
        if error:
            return ToolResult(success=False, error=error)
        if self.discovery is not None and self.discovery.is_mcp(name) and name not in self._request_visible_names:
            result = ToolResult(success=False,error='mcp_tool_not_visible_in_request; search and activate it, then wait for the next model request')
        else:
            result = await self._execute_tool(name, raw_arguments)
        from ..tools.patch import ApplyPatchTool
        from ..tools.run_command import RunCommandTool
        self.plan.observe(name, result, native_command=(name == 'run_command' and type(self.tools.get_tool(name)) is RunCommandTool), native_patch=(
            name == 'apply_patch' and type(self.tools.get_tool(name)) is ApplyPatchTool))
        return result

    async def _execute_tool(self, name: str, raw_arguments: Any) -> ToolResult:
        from ..tools.run_command import RunCommandTool, parse_arguments as parse_command_arguments
        if name == 'run_command' and type(self.tools.get_tool(name)) is RunCommandTool:
            try: arguments = parse_command_arguments(raw_arguments)
            except ValueError as exc:
                return RunCommandTool.failure_result(str(exc))
            return await self.tools.execute(name, arguments)
        from ..tools.patch import ApplyPatchTool, parse_arguments
        if name == 'apply_patch' and type(self.tools.get_tool(name)) is ApplyPatchTool:
            try:
                arguments = parse_arguments(raw_arguments)
            except ValueError as exc:
                return ToolResult(False, error=str(exc), metadata={
                    'status': 'preflight_failed', 'failure_phase': 'argument_parsing', 'applied': False,
                    'execution_evidence': False, 'safe_to_retry': False,
                    'input_feedback': {'version': 'patch-input-v1', 'issues': [{'field': '$', 'category': 'invalid_json_object'}],
                        'action': 'supply_bounded_unique_key_json_object; intent_unknown_no_retry'}})
            return await self.tools.execute(name, arguments)
        try:
            arguments = json.loads(raw_arguments or "{}") if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError as exc:
            return ToolResult(success=False, error=f"invalid JSON arguments: {exc}")
        if not isinstance(arguments, dict):
            return ToolResult(success=False, error="arguments must be a JSON object")
        if not self.tools.has_tool(name):
            return ToolResult(success=False, error=f"unknown tool '{name}'")
        schema = self.tools.get_parameters(name)
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in arguments:
                return ToolResult(success=False, error=f"missing required field '{required}'")
        for key, value in arguments.items():
            rule = properties.get(key, {})
            expected = rule.get("type")
            if expected == "string" and not isinstance(value, str):
                return ToolResult(success=False, error=f"field '{key}' must be a string")
        return await self.tools.execute(name, arguments)
