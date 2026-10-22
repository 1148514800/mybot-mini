"""Bounded independent Sessions, one workspace lease, real Agent/MCP owner task."""
import asyncio
import hashlib
import json
from collections import deque
from dataclasses import dataclass, field, replace
import secrets
import time

from ..agent import AgentLoop, ContextBuilder
from ..agent.session import Session
from ..config import GatewayConfig
from ..provider_failover import build_gateway_client, ProviderFailoverClient
from ..tools import build_default_tool_registry
from ..mcp_client.manager import MCPClientManager
from ..workspace import init_workspace
from .approval import WebApproval
from .security import redact


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
    report: dict | None = None
    failed_request: bool = False
    secret_values: tuple = ()

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
        self.sequence += 1
        self.events.append({'sequence': self.sequence, 'time': time.time(), **clean})
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
        return {'id': self.id, 'title': self.title, 'status': self.status, 'messages': self.messages,
                'events': list(self.events), 'sequence': self.sequence, 'requests': self.requests,
                'tokens': self.tokens if self.usage_known else None, 'report': self.report,
                'approval': self.approval.public_pending() if self.approval else None}


class ChatRuntime:
    def __init__(self, config=None, *, client_factory=build_gateway_client, approval_timeout=90, task_timeout=600):
        self.config = config or GatewayConfig()
        self.client_factory = client_factory
        self.approval_timeout = approval_timeout
        self.task_timeout = task_timeout
        self.conversations = {}; self.owner = None; self.closed = False; self.cleanup_uncertain = False

    def new(self):
        if len(self.conversations) >= 20: raise ValueError('conversation_limit')
        c = Conversation(secrets.token_hex(16), Session(self.config.session_max_turns))
        c.secret_values = (self.config.api_key,)
        self.conversations[c.id] = c
        return c

    async def start(self, c, text):
        if self.closed or self.cleanup_uncertain or self.owner is not None: return False
        if text.strip() in ('/undo', '/changes', '/clear'): raise ValueError('use_web_controls')
        self.owner = c.id  # No await between checking and reserving the process-wide lease.
        c.status = 'running'; c.started.clear(); c.failed_request = False; c.report = None
        c.events.clear(); c.requests = c.tokens = 0; c.usage_known = True
        c.messages.append({'role': 'user', 'content': redact(text, c.secret_values), 'time': time.time()})
        c.messages[:] = c.messages[-64:]
        if c.title == '新对话': c.title = redact(text.strip()[:32], c.secret_values)
        c.approval = WebApproval(c.emit, timeout=self.approval_timeout, secret_values=lambda: c.secret_values)
        c.task = asyncio.create_task(self._run(c, text))
        await c.started.wait()
        return True

    async def _run(self, c, text):
        client = None; agent = None; manager = None
        c.started.set()
        c.emit({'type': 'message_started'})
        try:
            async with asyncio.timeout(self.task_timeout):
                # Web histories are memory-only and never load/share the CLI disk Session.
                config = replace(self.config, session_persist=False, debug=False)
                if config.coding_enabled:
                    if not config.workspace.is_dir(): raise ValueError('workspace_missing')
                else: init_workspace(config.workspace)
                tools = build_default_tool_registry(config.workspace, coding_enabled=config.coding_enabled,
                    patch_mode=config.coding_patch_mode, preview_receipt=config.coding_preview_receipt,
                    command=config.coding_command, command_approval_provider=c.approval)
                # MCP enter/call/exit MUST stay in this SAME task, per existing manager fences.
                manager = MCPClientManager(config, tools, approval_provider=c.approval)
                await manager.__aenter__()
                client = self.client_factory(config)
                if isinstance(client, ProviderFailoverClient):
                    c.secret_values = tuple(dict.fromkeys((config.api_key, client._backup_config.api_key)))
                    c.messages = redact(c.messages, c.secret_values)
                    c.title = redact(c.title, c.secret_values)
                agent = AgentLoop(client, config, tools, ContextBuilder(config.workspace), session=c.session,
                    undo_approval_provider=c.approval, event_callback=c.emit)
                if isinstance(client, ProviderFailoverClient):
                    client.before_fallback = lambda definitions: agent.coding_controller is None or agent.coding_controller.before_request(definitions)
                reply = await agent.handle_message(text)
                report = agent.last_coding_report
                if report:
                    allowed = ('state', 'current_revision', 'committed_patches', 'test_runs', 'test_passes',
                               'test_failures', 'tests_passed_after_last_patch', 'verification', 'model_requests')
                    c.report = {k: report[k] for k in allowed if k in report}
                    state = report['state']
                    if state == 'execution_uncertain': self.cleanup_uncertain = True
                    state_label = {'verified':'当前修改已验证','edited_unverified':'已修改，尚未验证','completed_without_changes':'本轮完成，未提交修改','blocked':'已阻止执行','execution_uncertain':'执行结果不确定','cancelled':'已停止','budget_exhausted':'预算耗尽，已停止'}.get(state, '任务结束')
                    c.status = 'failed' if state in ('blocked', 'execution_uncertain') else ('stopped' if state in ('cancelled', 'budget_exhausted') else 'completed')
                    reply = (f"任务状态：{state_label}。已提交 {report['committed_patches']} 次修改，当前版本 {report['current_revision']}。\n\n"
                        f"当前修改之后的有效通过测试数：{report['tests_passed_after_last_patch']}。"
                        + ('指定测试范围已验证；这不代表整个项目或 Strict Success。' if state == 'verified' else '尚不能宣称当前修改已验证。'))
                else: c.status = 'failed' if c.failed_request else 'completed'
                reply = redact(reply, c.secret_values)
                c.messages.append({'role': 'assistant', 'content': reply, 'time': time.time()})
                c.messages[:] = c.messages[-64:]
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
            if agent is not None and agent._git_capsule is not None: agent._git_capsule.close()
            if manager is not None:
                try: await manager.__aexit__(None, None, None)
                except BaseException: cleanup_ok = False
            if client is not None:
                try: await client.close()
                except BaseException: cleanup_ok = False
            c.status = outcome
            if not cleanup_ok:
                c.status = 'cleanup_uncertain'; self.cleanup_uncertain = True
            c.emit({'type': {'cancelled': 'message_cancelled', 'failed': 'message_failed',
                            'stopped': 'message_cancelled', 'cleanup_uncertain': 'message_failed'}.get(c.status, 'message_completed'),
                    'status': c.status, 'report': c.report})
            # Lease remains held until MCP __aexit__, Agent finally and client close settle.
            if cleanup_ok: self.owner = None

    async def stop(self, c):
        task = c.task
        if task is not None and not task.done():
            if not task.cancelling(): task.cancel()
            await asyncio.shield(task)

    async def clear(self, c):
        if self.owner is not None: return False
        c.session.clear(); c.messages.clear(); c.events.clear(); c.report = None; c.title = '新对话'; c.status = 'idle'
        c.requests = c.tokens = 0; c.usage_known = True
        c.emit({'type': 'conversation_cleared'})
        return True

    async def close(self):
        self.closed = True
        for c in self.conversations.values(): await self.stop(c)
