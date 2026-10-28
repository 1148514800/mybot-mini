"""Bounded independent Sessions, one workspace lease, real Agent/MCP owner task."""
import asyncio
import hashlib
import json
from collections import deque
from dataclasses import dataclass, field, replace
import secrets
import time

from ..runtime_accounting import OUTPUT_NOTICES
from ..agent.streaming import StreamCleanupError
from ..agent import AgentLoop, ContextBuilder
from ..agent.session import Session
from ..config import GatewayConfig
from ..provider_failover import build_gateway_client, ProviderFailoverClient
from ..tools.registry import build_configured_tool_registry
from ..mcp_client.manager import MCPClientManager
from ..workspace import init_workspace
from .approval import WebApproval
from .security import redact
from ..workspace_lease import WorkspaceLease, WorkspaceBusy
from ..storage.history import open_store, SessionHistory, recover
from ..storage.event_schema import StoreError


@dataclass
class Conversation:
    id: str
    session: Session
    title: str = '新对话'
    status: str = 'idle'
    messages: list = field(default_factory=list)
    events: deque = field(default_factory=lambda: deque(maxlen=128))
    sequence: int = 0
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    approval: WebApproval | None = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    requests: int = 0
    tokens: int = 0
    usage_known: bool = True
    resources: dict = field(default_factory=dict)
    report: dict | None = None
    contract: dict | None = None
    failed_request: bool = False
    secret_values: tuple = ()
    history: object = None
    recovery_notice: str = ""
    pin_budget: dict = field(default_factory=dict)
    store_sequence: int = 0
    observed_turn_id: str | None = None
    context_boundary: int = 0

    stream_preview: dict = field(default_factory=dict)
    steer_inbox: object = None

    def emit(self, event):
        # No raw receipts, arguments, SDK errors, approval capabilities or private config.
        event = dict(event)
        if 'call_id' in event: event['call_id'] = hashlib.sha256(str(event['call_id']).encode()).hexdigest()[:24]
        for key in ('model', 'provider', 'tool'):
            if isinstance(event.get(key), str): event[key] = event[key][:128]
        clean = redact(event, self.secret_values)
        if len(json.dumps(clean, ensure_ascii=False).encode()) > 32768:
            clean = {k: clean[k] for k in ('type', 'tool', 'call_id', 'success', 'status') if k in clean}
            clean['display_truncated'] = True
        if str(clean.get('type','')).startswith('model_stream') or clean.get('type')=='model_text_delta':
            if clean.get('turn_id')!=self.observed_turn_id:return
            self.stream_preview={k:v for k,v in clean.items() if k in ('turn_id','stream_id','text','preview_revision','status','error_code')} | {'status':clean.get('status','generating')}
        self.sequence += 1
        self.events.append({'sequence': self.sequence, 'time': time.time(), **clean})
        if event['type'] == 'pin_budget':self.pin_budget=clean
        if event['type'] == 'task_contract': self.contract = clean.get('contract')
        if event['type'] == 'resource_update': self.resources = clean.get('resources', {})
        if event['type'] == 'model_request_started': self.requests += 1
        if event['type'] == 'model_request_failed': self.failed_request = True; self.usage_known = False
        if event['type'] == 'model_request_finished':
            count = event.get('tokens')
            if type(count) is int and count >= 0: self.tokens += count
            else: self.usage_known = False
        if event['type'] == 'approval_requested': self.status = 'waiting_approval'
        if event['type'] == 'approval_resolved' and self.status == 'waiting_approval': self.status = 'running'
        self.changed.set()

    def state(self):
        from ..agent.steer import SteerInbox
        return {'stream_preview':dict(self.stream_preview),'steers':list(self.steer_inbox.records.values()) if self.steer_inbox else SteerInbox.audit(self.history) if self.history else [],'active_turn_id':self.history.turn_id if self.history else None, 'id': self.id, 'title': self.title, 'status': self.status, 'messages': self.messages,
                'events': list(self.events), 'sequence': self.sequence, 'requests': self.requests,
                'tokens': self.resources.get('provider_reported_total_tokens') if self.resources else (self.tokens if self.usage_known else None), 'report': self.report, 'resources': self.resources, 'contract': self.contract,
                'approval': self.approval.public_pending() if self.approval else None,
                'decisions':self.history.decisions() if self.history else None,
                'pin_budget':self.pin_budget, 'pins': self.history.pins.list() if self.history else [], 'recovery_notice': self.recovery_notice}


class ChatRuntime:
    def __init__(self, config=None, *, client_factory=build_gateway_client, approval_timeout=90, task_timeout=600, initialize_workspace=True):
        self.config = config or GatewayConfig()
        self.initialize_workspace = initialize_workspace
        self.client_factory = client_factory
        self.approval_timeout = approval_timeout
        self.task_timeout = task_timeout
        self.conversations = {}; self.owner = None; self.closed = False; self.cleanup_uncertain = False
        # The channel namespace never imports CLI JSON/private conversations.
        self.event_store=open_store(self.config,'web')
        recover(self.event_store)
        if self.config.storage_backend=='event_sqlite':
            for row in reversed(self.event_store.sessions(20)):
                c=Conversation(row['id'],Session(self.config.session_max_turns),title=row['title'])
                c.history=SessionHistory(self.event_store,c.id);status=c.history.status()
                c.status=status['status'];c.recovery_notice=status.get('notice','')
                c.messages=c.history.messages();c.session.restore(c.history.model_turns(c.session.max_turns))
                c.secret_values=(self.config.api_key,);self.conversations[c.id]=c
        self.cleanup_uncertain=self.event_store.workspace_uncertain()

    def sync(self):
        if self.config.storage_backend!='event_sqlite' or self.owner is not None or self.closed:return
        recover(self.event_store)
        rows=self.event_store.sessions(20);ids={r['id'] for r in rows}
        for sid in list(self.conversations):
            if sid not in ids:
                c=self.conversations.pop(sid);c.messages.clear();c.events.clear();c.session.clear();c.changed.set()
        for row in reversed(rows):
            c=self.conversations.get(row['id'])
            if c is None:
                c=Conversation(row['id'],Session(self.config.session_max_turns));c.history=SessionHistory(self.event_store,c.id)
                c.secret_values=(self.config.api_key,);self.conversations[c.id]=c
            if row['seq']==c.store_sequence:continue
            status=c.history.status()
            if c.observed_turn_id!=status['turn_id']:
                c.report=None;c.contract=None;c.resources={};c.approval=None;c.events.clear();c.stream_preview={};c.steer_inbox=None
                c.session.restore(c.history.model_turns(c.session.max_turns))
            elif row['context_after']!=c.context_boundary:
                c.session.restore(c.history.model_turns(c.session.max_turns))
            c.context_boundary=row['context_after']
            c.observed_turn_id=status['turn_id'];c.store_sequence=row['seq']
            c.title=row['title'];c.messages=c.history.messages();c.status=status['status'];c.recovery_notice=status.get('notice','')
        if self.event_store.workspace_uncertain():self.cleanup_uncertain=True

    def new(self):
        if len(self.conversations) >= 20: raise ValueError('conversation_limit')
        history=SessionHistory(self.event_store)
        c = Conversation(history.sid, Session(self.config.session_max_turns));c.history=history
        c.secret_values = (self.config.api_key,)
        self.conversations[c.id] = c
        return c

    async def start(self, c, text):
        if self.closed or self.cleanup_uncertain or self.event_store.workspace_uncertain() or self.owner is not None: return False
        if c.history.status()['status'] in ('running','pending','execution_uncertain'):return False
        if text.strip() in ('/undo', '/changes', '/clear'): raise ValueError('use_web_controls')
        try:
            c.history.start(text)  # Commit acceptance before UI/model publication.
            accepted_messages=c.history.messages()
        except StoreError:
            c.status='failed';self.cleanup_uncertain=True
            try:c.history.interrupt('storage_failed',failed=True)
            except StoreError:pass
            raise
        self.owner = c.id  # No await between checking and reserving the process-wide lease.
        c.status = 'running'; c.started.clear(); c.failed_request = False; c.report = None
        c.events.clear(); c.contract = None; c.pin_budget={}; c.requests = c.tokens = 0; c.usage_known = True; c.resources = {}
        from ..agent.steer import SteerInbox
        c.steer_inbox=SteerInbox(c.history,c.emit) if self.config.web_steer else None;c.stream_preview={}
        c.messages=accepted_messages;c.recovery_notice='';c.observed_turn_id=c.history.turn_id
        c.messages[:] = c.messages[-64:]
        c.title=c.history.title()
        c.approval = WebApproval(c.emit, timeout=self.approval_timeout, secret_values=lambda: c.secret_values)
        c.task = asyncio.create_task(self._run(c, text))
        await c.started.wait()
        return True

    async def _run(self, c, text):
        client = None; agent = None; manager = None; reply = None; lease = WorkspaceLease(self.config.workspace)
        c.started.set()
        c.emit({'type': 'message_started'})
        try:
            async with asyncio.timeout(self.task_timeout):
                lease.acquire()
                # Web histories are memory-only and never load/share the CLI disk Session.
                config = replace(self.config, session_persist=False, session_backend='event_sqlite' if self.config.storage_backend=='event_sqlite' else 'memory', debug=False)
                if config.coding_enabled or not self.initialize_workspace:
                    if not config.workspace.is_dir(): raise ValueError('workspace_missing')
                else: init_workspace(config.workspace)
                tools = build_configured_tool_registry(config, file_approval_provider=c.approval,
                    command_approval_provider=c.approval)
                # MCP enter/call/exit MUST stay in this SAME task, per existing manager fences.
                manager = MCPClientManager(config, tools, approval_provider=c.approval)
                await manager.__aenter__()
                client = self.client_factory(config)
                if isinstance(client, ProviderFailoverClient):
                    c.secret_values = tuple(dict.fromkeys((config.api_key, *client.secret_values)))
                    c.messages = redact(c.messages, c.secret_values)
                    c.title = redact(c.title, c.secret_values)
                agent = AgentLoop(client, config, tools, ContextBuilder(config.workspace), session=c.session,
                    undo_approval_provider=c.approval, event_callback=c.emit,history=c.history,steer_inbox=c.steer_inbox,stream_secrets=c.secret_values)
                reply = await agent.handle_message(text)
                report = agent.last_coding_report
                if report:
                    allowed = ('state', 'current_revision', 'committed_patches', 'test_runs', 'test_passes',
                               'test_failures', 'tests_passed_after_last_patch', 'verification', 'model_requests')
                    c.report = {k: report[k] for k in allowed if k in report}
                    state = report['state']
                    if state == 'execution_uncertain': self.cleanup_uncertain = True
                    state_label = {'verified':'当前修改已验证','edited_unverified':'已修改，尚未验证','completed_without_changes':'本轮完成，未提交修改','blocked':'已阻止执行','execution_uncertain':'执行结果不确定','cancelled':'已停止','budget_exhausted':'预算耗尽，已停止'}.get(state, '任务结束')
                    c.status = 'execution_uncertain' if state=='execution_uncertain' else 'failed' if state=='blocked' else ('stopped' if state in ('cancelled', 'budget_exhausted') else 'completed')
                    reply = (f"任务状态：{state_label}。已提交 {report['committed_patches']} 次修改，当前版本 {report['current_revision']}。\n\n"
                        f"当前修改之后的有效通过测试数：{report['tests_passed_after_last_patch']}。"
                        + ('指定测试范围已验证；这不代表整个项目或 Strict Success。' if state == 'verified' else '尚不能宣称当前修改已验证。'))
                else:
                    outcome = agent.last_runtime_report['outcome']
                    c.status = 'failed' if c.failed_request or outcome == 'failed' else 'stopped' if outcome in ('timeout','stopped') else 'completed'
                delivery = agent.last_runtime_report.get('output', {})
                if delivery.get('failure_reason'):
                    reply += '\n' + str(delivery['failure_reason'])[:4096]
                if delivery.get('status') in OUTPUT_NOTICES:
                    if c.status not in ('failed','stopped','execution_uncertain'): c.status = delivery['status']
                    # Coding report is independent; retain the model's partial text
                    # as well as the actual host revision report.
                    if report:
                        reply = '[OUTPUT] ' + OUTPUT_NOTICES[delivery['status']] + '\n' + reply
                        if agent.partial_reply: reply += '\n[模型部分回复]\n' + agent.partial_reply
                if agent.task_contract is not None: reply += '\n' + agent.task_contract.summary()
                reply = redact(reply, c.secret_values)

        except StoreError:
            c.status='execution_uncertain';self.cleanup_uncertain=True
            c.recovery_notice='持久化写入失败；不宣称已保存，不自动重放。请检查数据库和工作区后重启。'
        except StreamCleanupError:
            c.status='execution_uncertain';self.cleanup_uncertain=True
        except WorkspaceBusy:
            c.status = 'failed'
            c.emit({'type':'workspace_busy', 'reason':'another_process_or_unsafe_lock'})
        except asyncio.CancelledError:
            c.status = 'cancelled'; c.usage_known = False
        except TimeoutError:
            c.status = 'stopped'; c.usage_known = False
        except Exception:
            c.status = 'failed'; c.usage_known = False  # Never serialize SDK errors/keys/source/host paths.
        finally:
            cleanup_ok = True
            if c.report is None and agent is not None and agent.last_coding_report is not None:
                snapshot = agent.last_coding_report
                c.report = {k: snapshot[k] for k in ('state', 'current_revision', 'committed_patches', 'test_runs', 'test_passes', 'test_failures', 'tests_passed_after_last_patch', 'verification', 'model_requests') if k in snapshot}
                if snapshot['state'] == 'execution_uncertain': self.cleanup_uncertain = True
            outcome = c.status
            c.status = 'stopping' if outcome in ('cancelled', 'stopped') else 'settling'
            c.emit({'type': 'task_status_changed', 'status': c.status})
            if agent is not None and agent._git_capsule is not None:
                try: agent._git_capsule.close()
                except BaseException: cleanup_ok = False
            if manager is not None:
                try:
                    async with asyncio.timeout(3): await manager.__aexit__(None, None, None)
                except BaseException: cleanup_ok = False
            if client is not None:
                try:
                    async with asyncio.timeout(3): await client.close()
                except BaseException: cleanup_ok = False
            if c.steer_inbox and c.steer_inbox.pending:
                budget=bool(agent and agent.resources.request_budget_exhausted)
                stopped=outcome in ('cancelled','stopped','execution_uncertain') and not budget
                try:c.steer_inbox.resolve('discarded_on_stop' if stopped else 'not_applied','stop' if stopped else 'budget' if budget else 'no_next_step')
                except StoreError:cleanup_ok=False;self.cleanup_uncertain=True
            # Persist the terminal boundary only after owned resources settle.
            # A cleanup failure must remain unsafe after a service restart.
            try:
                if reply is not None and cleanup_ok and outcome!='execution_uncertain':
                    c.history.finish(reply,outcome if outcome in ('completed','failed','cancelled','stopped',*OUTPUT_NOTICES) else 'failed')
                    c.messages=c.history.messages()[-64:]
                elif c.history.turn_id is not None:
                    c.history.interrupt('cancelled' if outcome=='cancelled' else 'runtime_failed',
                        cancelled=outcome=='cancelled',failed=outcome=='failed',force_uncertain=not cleanup_ok or outcome=='execution_uncertain')
                    if c.history.status()['status']=='execution_uncertain':
                        outcome='execution_uncertain';self.cleanup_uncertain=True
            except StoreError:
                cleanup_ok=False;self.cleanup_uncertain=True
                c.recovery_notice='持久化写入失败；不宣称已保存，不自动重放。请检查数据库和工作区后重启。'
            c.status = outcome
            if not cleanup_ok:
                c.status = 'cleanup_uncertain'; self.cleanup_uncertain = True
            c.emit({'type': {'cancelled': 'message_cancelled', 'failed': 'message_failed',
                            'stopped': 'message_cancelled', 'cleanup_uncertain': 'message_failed', 'execution_uncertain': 'message_failed',
                            **{k:'message_incomplete' for k in OUTPUT_NOTICES}}.get(c.status, 'message_completed'),
                    'status': c.status, 'report': c.report})
            # Lease remains held until MCP __aexit__, Agent finally and client close settle.
            lease.release(confirmed=cleanup_ok and not self.cleanup_uncertain)
            if cleanup_ok: self.owner = None

    def steer(self,c,value):
        if not self.config.web_steer or self.closed or self.cleanup_uncertain or self.owner!=c.id or c.status!='running' or c.task is None or c.task.done() or c.steer_inbox is None:
            raise StoreError('steer_rejected_busy_approval_or_inactive')
        if set(value)!={'expected_turn_id','client_request_id','text'}:raise StoreError('steer_fields')
        return c.steer_inbox.submit(**value)

    async def stop(self, c):
        task = c.task
        if task is not None and not task.done():
            if not task.cancelling(): task.cancel()
            await asyncio.shield(task)

    async def clear(self, c):
        if self.owner is not None: return False
        c.history.clear_context()
        c.session.clear();
        if self.config.storage_backend!='event_sqlite':c.messages.clear()
        c.events.clear(); c.report = None; c.contract = None; c.title = c.history.title() if self.config.storage_backend=='event_sqlite' else '新对话'; c.status = 'idle'
        c.requests = c.tokens = 0; c.usage_known = True; c.resources = {}
        c.emit({'type': 'conversation_cleared'})
        return True

    async def delete(self,c,*,confirmed=False):
        if confirmed is not True:raise StoreError('delete_confirmation_required')
        if self.owner is not None:return False
        self.event_store.delete(c.id);self.conversations.pop(c.id,None);c.messages.clear();c.events.clear();c.session.clear();c.changed.set()
        return True

    def pin(self,c,value):
        if self.owner is not None:raise StoreError('pin_while_busy')
        return c.history.pins.add(value['message_id'],value['start'],value['end'],value['category'],
            confirmed=value.get('confirmed') is True,replace_id=value.get('replace_id'),expected_revision=value.get('expected_revision'))

    def review(self,c,*,confirmed=False):
        if self.owner is not None:raise StoreError('workspace_busy')
        c.history.review(confirmed=confirmed)
        c.status=c.history.status()['status'];c.recovery_notice=c.history.status()['notice']
        self.cleanup_uncertain=self.event_store.workspace_uncertain()

    async def close(self):
        self.closed = True
        for c in self.conversations.values(): c.changed.set()
        for c in self.conversations.values():
            try:
                # Shutdown owns cleanup; an admission/HALT hook is not permission
                # to prevent closing an already owned task. Never clear that hook.
                await asyncio.wait_for(ChatRuntime.stop(self, c), 10)
            except BaseException:
                self.cleanup_uncertain = True
                raise StreamCleanupError('runtime_close_unconfirmed') from None
        self.event_store.close()
