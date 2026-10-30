"""Turn boundaries, persistence and cleanup. State remains on the owning AgentLoop."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from ..runtime_accounting import OUTPUT_NOTICES
from .context_manager import ContextBudgetError
from .planning import PlanningTool
from ..tools.skill import SkillTool
from ..mcp_client.discovery import DiscoveryTool


async def handle_message(self, user_input: str) -> str:
    from ..storage.event_schema import StoreError
    control=self._history_control(user_input)
    if control is not None:return control
    if user_input.strip() in ('/clear','/undo','/changes'):
        reply=await self._run_message(user_input)
        if user_input.strip()=='/clear':self.history.clear_context()
        return reply
    own=self.history.turn_id is None
    if own:self.history.start(user_input)
    self.context_manager.pinned_context=self.history.pins.list(active_only=True)
    old_observer=self.tools.execution_observer;self.tools.execution_observer=self.history
    try:
        reply=await self._run_message(user_input)
        if own:
            outcome=self.last_runtime_report.get('outcome','completed')
            status=outcome if outcome in ('failed','cancelled','output_truncated','output_filtered','empty_response','unknown_finish','content_filtered','provider_error','response_unconfirmed','empty_reply','stopped','execution_uncertain') else 'completed'
            if self.last_coding_report and self.last_coding_report['state']=='execution_uncertain':status='execution_uncertain'
            elif outcome=='blocked':status='failed'
            elif outcome in ('budget_exhausted','timeout'):status='stopped'
            self.history.finish(reply,status)
        if self.resources.context.get('pins_omitted'):
            reply='[PIN] 部分固定事项未进入本次请求，历史信息可能遗漏。\n'+reply
        return reply
    except BaseException as exc:
        if isinstance(exc,ContextBudgetError) and self.context_manager.pinned_context:
            self._notify('pin_budget',included=[],omitted=[p['pin_id'] for p in self.context_manager.pinned_context],reason='protected_request_budget')
            if self._event_callback is None:print('[PIN] 当前尝试未发送；固定事项未能进入请求预算。')
        if own:
            try:self.history.interrupt('storage_failed' if isinstance(exc,StoreError) else 'cancelled' if isinstance(exc,asyncio.CancelledError) else 'runtime_failed',cancelled=isinstance(exc,asyncio.CancelledError),failed=not isinstance(exc,asyncio.CancelledError))
            except StoreError:pass  # Durable started evidence stays incomplete; never replay.
        raise
    finally:
        self.tools.execution_observer=old_observer


def _history_control(self,text):
    from ..storage.event_schema import StoreError
    from ..storage.history import SessionHistory
    parts=text.strip().split()
    if not parts:return None
    command=parts[0]
    if command not in ('/decisions','/pins','/pin','/unpin','/repin','/sessions','/session','/history','/delete-session','/review-session'):return None
    try:
        if command=='/decisions':
            from .decision_provenance import render_view
            return render_view(self.history.decisions(boundary=int(parts[1]) if len(parts)>1 else None))
        if command=='/pins':return json.dumps(self.history.pins.list(),ensure_ascii=False)
        if command=='/history':return json.dumps(self.history.messages(before=int(parts[1]) if len(parts)>1 else None),ensure_ascii=False)
        if command=='/sessions':return json.dumps([{k:s[k] for k in ('id','title')} for s in self.history.store.sessions()],ensure_ascii=False)
        if command=='/session':
            sid=None if parts[1]=='new' else parts[1]
            h=SessionHistory(self.history.store,sid)
            if sid:h.status()
            self.history=h;self.session.restore(h.model_turns(self.session.max_turns))
            return 'Session '+h.sid+' '+h.status()['status']
        if len(parts)<2 or parts[1]!='confirm':raise StoreError('explicit_confirm_command_required')
        if command=='/pin' and len(parts)==6:
            ident=self.history.pins.add(parts[2],int(parts[3]),int(parts[4]),parts[5],confirmed=True)
            return 'Pinned '+ident
        if command=='/repin' and len(parts)==8:
            ident=self.history.pins.add(parts[4],int(parts[5]),int(parts[6]),parts[7],confirmed=True,replace_id=parts[2],expected_revision=int(parts[3]))
            return 'Replaced '+ident
        if command=='/unpin' and len(parts)==4:
            self.history.pins.revoke(parts[2],int(parts[3]),confirmed=True);return 'Pin revoked'
        if command=='/delete-session' and len(parts)==3:
            self.history.store.delete(parts[2])
            if parts[2]==self.history.sid:self.history=SessionHistory(self.history.store);self.session.clear()
            return '会话记录已从应用数据库删除；不保证底层介质、备份无残留。'
        if command=='/review-session' and len(parts)==3 and parts[2]=='WORKSPACE_AND_PROCESSES_CHECKED':
            self.history.review(confirmed=True);return '人工检查已记录；旧任务仍中断，未恢复授权或verified。'
        raise StoreError('history_command_arguments')
    except (ValueError,IndexError,StoreError):
        return '会话操作拒绝：请检查来源、版本和显式confirm参数；未请求模型。'


def close_history(self):
    if self._owns_history:self.history.store.close()


async def _run_message(self, user_input: str) -> str:
    from ..runtime_accounting import RuntimeAccounting
    from .context_compactor import ContextCompactor
    self.resources = RuntimeAccounting()
    from ..runtime_accounting import find_gateway
    gateway = find_gateway(self.client)
    if gateway is not None: gateway.reset_task()
    self.partial_reply = ""
    self.compactor = ContextCompactor(self.config)
    self.last_runtime_report = self.resources.snapshot()
    if self.config.coding_git_workflow['enabled']:
        command = user_input.strip()
        if command in ('/changes', '/undo'):
            try:
                reply = await self._git_cli(command)
                self.resources.outcome = 'completed'
                return reply
            except BaseException as exc:
                self.resources.outcome = 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed'
                raise
            finally:
                self.last_runtime_report = self.resources.snapshot()
                self._notify('resource_update', resources=self.last_runtime_report)
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
    from .task_contract import TaskContract
    self.last_task_contract = None
    self.task_contract = (TaskContract(user_input, self.coding_controller)
        if self.coding_controller is not None and self.config.coding_task_contract else None)
    command = self.tools.get_tool('run_command')
    old_guard = command.execution_guard if type(command) is RunCommandTool else None
    if self.coding_controller is not None and type(command) is RunCommandTool:
        controller_guard = self.coding_controller.command_guard
        def task_guard(launch, timeout):
            if old_guard is not None: timeout = min(timeout, old_guard(launch, timeout))
            return controller_guard(launch, timeout)
        command.execution_guard = task_guard
    from ..tools.patch import ApplyPatchTool
    receipt_tool = self.tools.get_tool('apply_patch')
    old_receipt_guard = None
    if type(receipt_tool) is ApplyPatchTool and receipt_tool.preview_receipt:
        receipt_tool.begin_receipt_scope()
        old_receipt_guard = receipt_tool.receipt_commit_guard
        def receipt_guard():
            if old_receipt_guard is not None: old_receipt_guard()
            if self.coding_controller is not None and not self.coding_controller.check_time():
                raise ValueError('receipt_controller_stopped')
        receipt_tool.receipt_commit_guard = receipt_guard
    try:
        reply = await self._handle_message(user_input)
        if self.context_clipped:
            reply = "[CONTEXT] 本轮部分工具结果仅提供节选，未验证全文阅读或分析。以下模型回复不能视为完整任务结论：\n" + reply
        if self.context_history_omitted:
            reply = "[CONTEXT] 部分历史已省略，预算不足以提供其摘要。\n" + reply
        self.resources.outcome = (self.resources.output['status'] if self.resources.output.get('status') in OUTPUT_NOTICES else
            self.last_coding_report['state'] if self.last_coding_report else
            'completed' if self.resources.outcome == 'running' else self.resources.outcome)
        return reply
    except BaseException as exc:
        if isinstance(exc, ContextBudgetError): self.resources.request_budget_exhausted = True
        self.resources.outcome = 'context_budget_exhausted' if isinstance(exc, ContextBudgetError) else 'cancelled' if isinstance(exc, asyncio.CancelledError) else 'failed'
        if self._active_journal is not None:
            self._active_journal.close()
            self._git_capsule = None
        if self.coding_controller is not None:
            self.coding_controller.stop('cancelled' if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)) else 'execution_uncertain', 'task_interrupted')
            self.last_coding_report = self.coding_controller.snapshot()
        report = self.plan.close("上下文预算不足" if isinstance(exc, ContextBudgetError) else "任务异常或中断")
        if report and self._event_callback is None:
            print(report)
        raise
    finally:
        if type(receipt_tool) is ApplyPatchTool and receipt_tool.preview_receipt:
            receipt_tool.end_receipt_scope()
            receipt_tool.receipt_commit_guard = old_receipt_guard
        if type(command) is RunCommandTool: command.execution_guard = old_guard
        if self.task_contract is not None:
            self.last_task_contract = self.task_contract.public_snapshot()
            self._notify('task_contract', contract=self.last_task_contract)
        self.coding_controller = None
        if self._active_journal is not None:
            self._active_journal.patch_tool.observer = None
            self._active_journal = None
        if self.discovery is not None:self.discovery.reset()
        self._request_visible_names = frozenset()
        self.routing_decision = None
        self.last_runtime_report = self.resources.snapshot()
        self._notify('resource_update', resources=self.last_runtime_report)


async def _complete_turn(self, messages, turn_start, reply, reason=''):
    if self._active_journal is not None:
        await self._active_journal.refresh()
    return self._finish_turn(messages, turn_start, reply, reason)


def _validate_undo_registry(self):
    from ..tools.file import ReadFileTool
    from ..tools.list_files import ListFilesTool
    from ..tools.repo_map import RepoMapTool
    from ..tools.search_code import SearchCodeTool
    from ..tools.read_file_range import ReadFileRangeTool
    from ..tools.git_tools import GitStatusTool, GitDiffTool
    from ..tools.patch import ApplyPatchTool
    from ..tools.run_command import RunCommandTool
    from .task_contract import ContractTool
    allowed = {RepoMapTool, ContractTool, ReadFileTool, ListFilesTool, SearchCodeTool, ReadFileRangeTool, GitStatusTool, GitDiffTool,
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
    if self.task_contract is not None:
        self.task_contract.invalidate()
        self.last_task_contract = self.task_contract.public_snapshot()
    if self.last_coding_report is not None:
        self.last_coding_report = {**self.last_coding_report,
            'state': 'execution_uncertain' if uncertain else 'edited_unverified',
            'verification': 'invalid', 'tests_passed_after_last_patch': 0,
            'current_revision': self.last_coding_report['current_revision'] + int(changed),
            'stop_reason': reason, 'undo_status': reason, 'verification_invalidated': True}


def _finish_turn(self, messages: list[dict[str, Any]], turn_start: int, reply: str,
                 reason: str = "") -> str:
    controller = self.coding_controller
    partial = reply
    delivery_status = self.resources.output.get('status')
    if controller is not None:
        reply = controller.finish(reason)
        if self.resources.output.get('failure_reason'):
            reply += '\n' + self.resources.output['failure_reason']
        elif delivery_status in OUTPUT_NOTICES and partial:
            reply += '\n[模型部分回复]\n' + partial
        self.last_coding_report = controller.snapshot()
        if self.task_contract is not None: reply += '\n' + self.task_contract.summary()
    report = self.plan.close(reason)
    if controller is None and (reason or any(s.status != 'completed' for s in self.plan.steps)):
        self.resources.outcome = 'stopped' if reason else 'failed'
    if report and controller is None:
        reply = f"{reply}\n{report}" if reason or delivery_status in OUTPUT_NOTICES else report
    if self._active_journal is not None:
        self._git_capsule = self._active_journal
        reply += '\n[TASK CHANGE SUMMARY]\n' + self._active_journal.summary_text(4000)
    if delivery_status in OUTPUT_NOTICES:
        reply = '[OUTPUT] ' + OUTPUT_NOTICES[delivery_status] + '\n' + reply
    from ..runtime_accounting import find_gateway
    gateway = find_gateway(self.client)
    if gateway is not None:
        for secret in gateway.secret_values:
            if len(secret) >= 6: reply = reply.replace(secret, "[已隐藏]")
    messages.append({"role": "assistant", "content": reply})
    from ..tools.patch import ApplyPatchTool
    patch_tool = self.tools.get_tool('apply_patch')
    saved_turn = messages[turn_start:]
    if type(patch_tool) is ApplyPatchTool and patch_tool.preview_receipt:
        saved_turn = patch_tool.redact_receipt_history(saved_turn)
    self.session.add_turn(self.history.identify_turn(saved_turn))
    return reply
