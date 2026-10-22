"""One outstanding capability per actual approval await; never cache grants."""
import asyncio
import json
import secrets
import time
from .security import redact
from ..tools.command_approval import CommandApprovalRequest, MAX_DISPLAY
from ..tools.undo_approval import UndoApprovalRequest
from ..mcp_client.approval import ApprovalRequest, ApprovalDecision


class WebApproval:
    def __init__(self, emit, *, timeout=90, secret_values=lambda: ()):
        self.secret_values = secret_values
        self.emit = emit; self.timeout = timeout; self.pending = None
        self.audit = []

    async def __call__(self, request):
        if self.pending is not None: return ApprovalDecision.DENY
        if isinstance(request, CommandApprovalRequest):
            display = request.display_json; kind = 'command'
        elif isinstance(request, ApprovalRequest):
            display = json.dumps({'server': request.server, 'tool': request.tool,
                                  'arguments': json.loads(request.arguments_json)}, ensure_ascii=True); kind = 'mcp'
        elif isinstance(request, UndoApprovalRequest):
            # Web v1 intentionally does not retain cross-turn Undo capsules.
            return ApprovalDecision.DENY
        else: return ApprovalDecision.DENY
        if redact(display, self.secret_values()) != display or len(display) > MAX_DISPLAY: return ApprovalDecision.DENY
        display = json.dumps(json.loads(display), ensure_ascii=True, indent=2)
        if len(display) > MAX_DISPLAY: return ApprovalDecision.DENY
        nonce = secrets.token_hex(32); future = asyncio.get_running_loop().create_future()
        pending = {'id': nonce, 'kind': kind, 'display': display, 'expires_at': time.time() + self.timeout,
                   'deadline': time.monotonic() + self.timeout, 'future': future}
        self.pending = pending
        self.emit({'type': 'approval_requested', 'kind': kind})
        decision = ApprovalDecision.DENY
        try:
            decision = await asyncio.wait_for(future, timeout=self.timeout)
            return decision
        except TimeoutError: return ApprovalDecision.DENY
        finally:
            self.pending = None
            approved = decision is ApprovalDecision.APPROVE
            self.audit.append({'kind': kind, 'approved': approved, 'time': time.time()})
            self.audit[:] = self.audit[-64:]
            self.emit({'type': 'approval_resolved', 'approved': approved, 'kind': kind})

    def resolve(self, nonce, allow):
        pending = self.pending
        if (pending is None or not isinstance(nonce, str) or not secrets.compare_digest(nonce, pending['id'])
                or type(allow) is not bool or pending['future'].done() or time.monotonic() >= pending['deadline']):
            return False
        pending['future'].set_result(ApprovalDecision.APPROVE if allow else ApprovalDecision.DENY)
        return True

    def public_pending(self):
        p = self.pending
        return {k: p[k] for k in ('id', 'kind', 'display', 'expires_at')} if p and not p['future'].done() else None
