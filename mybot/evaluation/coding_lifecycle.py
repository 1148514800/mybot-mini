"""Host-only attempt fence and bounded cancellation settlement; no recovery authority."""
import asyncio
import hashlib
import uuid
from pathlib import Path
import shutil
import tempfile


class Attempt:
    def __init__(self, identity=None):
        self.identity = dict(identity or {})
        self.identity.setdefault('attempt_id', uuid.uuid4().hex)
        self.active = True
        self.reason = None
        self.cleanup_confirmed = True
        self.tool = None
        self.command_approved = False
        self.approval_cancelled = False
        self.tool_uncertain = False
        self.cancelled_calls = []
        self.calls = []

    def check(self):
        if not self.active:
            raise asyncio.CancelledError('attempt_expired')

    def revoke(self, reason):
        self.active = False
        if self.reason is None:
            self.reason = reason

    async def settle(self, task, timeout=5):
        """Repeated caller cancellation cannot cancel cleanup or erase its deadline."""
        deadline = asyncio.get_running_loop().time() + timeout
        while not task.done():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.cleanup_confirmed = False
                # Consume a late exception; the revoked fence still rejects new work.
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                return
            try:
                await asyncio.wait({task}, timeout=remaining)
            except asyncio.CancelledError:
                self.revoke('task_cancelled')
        # Retrieve exceptions without treating cancellation as successful completion.
        if not task.cancelled():
            task.exception()

    async def run(self, coroutine, timeout):
        self.check()
        task = asyncio.create_task(coroutine)
        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
            if done:
                self.check()
                return task.result()
            self.revoke('task_timeout')
            task.cancel()
            await self.settle(task)
            raise TimeoutError
        except asyncio.CancelledError:
            self.revoke('task_cancelled')
            task.cancel()
            await self.settle(task)
            raise

    def register_calls(self, calls, allowed_names=()):
        self.check()
        self.allowed_names = frozenset(allowed_names)
        for call in calls or []:
            self.calls.append(dict(id_sha256=hashlib.sha256(call.id.encode()).hexdigest(),
                name=call.function.name if call.function.name in self.allowed_names else '<unknown>', status='pending'))

    def begin_tool(self, name):
        self.check()
        safe_name = name if name in getattr(self, 'allowed_names', ()) else '<unknown>'
        return next((c for c in self.calls if c['status']=='pending' and c['name']==safe_name), None)

    def metadata(self):
        receipts = [dict(c, status='not_executed_after_stop' if c['status']=='pending' else c['status']) for c in self.calls]
        return dict(**self.identity, terminal_reason=self.reason,
            cleanup_confirmed=self.cleanup_confirmed,
            execution_uncertain=not self.cleanup_confirmed or self.tool_uncertain,
            cancelled_tool_calls=list(self.cancelled_calls), tool_call_receipts=receipts,
            workspace_retained=not self.cleanup_confirmed or self.tool_uncertain, approval_cancelled=self.approval_cancelled)


class WorkspaceDirectory:
    """Never delete a workspace while a native operation lacks settlement evidence."""
    def __init__(self):
        self.path = Path(tempfile.mkdtemp(prefix='mybot-coding-benchmark-')).resolve()
        self.retain = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        # An escape before terminal evidence is itself uncertain; never erase it.
        self.retain |= exc[0] is not None
        if not self.retain:
            shutil.rmtree(self.path)
