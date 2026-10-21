"""Phase25 real-TTY approvals with cancellable FD reads and per-attempt challenges."""
import asyncio
import os
import sys
import uuid
from ..mcp_client.approval import ApprovalDecision


class AttemptApproval:
    def __init__(self, attempt, *, output=None, challenge=True):
        self.attempt = attempt
        self.output = sys.stdout if output is None else output
        self.busy = False
        self.challenge = challenge

    async def __call__(self, request):
        self.attempt.check()
        if request.mode != 'macos_readonly' or self.busy or not sys.stdin.isatty() or not self.output.isatty():
            return ApprovalDecision.DENY
        try:
            fd = sys.stdin.fileno()
            if not os.isatty(fd) or not os.isatty(self.output.fileno()):
                return ApprovalDecision.DENY
        except (OSError, ValueError, AttributeError):
            return ApprovalDecision.DENY
        # A bare/delayed yes and any previous challenge cannot authorize this call.
        challenge = uuid.uuid4().hex if self.challenge else None
        expected = 'yes ' + challenge if challenge else 'yes'
        print('[NATIVE COMMAND APPROVAL] ' + request.display_json, file=self.output)
        print('macOS Seatbelt：Workspace只读、网络禁止；每次仅批准当前命令。', file=self.output)
        print('仅批准此命令一次？输入 ' + expected + '，其他输入拒绝: ',
              end='', file=self.output, flush=True)
        loop = asyncio.get_running_loop()
        answer = loop.create_future()
        self.busy = True
        data = bytearray()
        def ready():
            if answer.done():
                return
            try:
                chunk = os.read(fd, 1024)
                data.extend(chunk)
                if not chunk or b'\n' in data or len(data) >= 1024:
                    answer.set_result(bytes(data))
            except OSError:
                answer.set_result(b'')
        try:
            loop.add_reader(fd, ready)
            value = await answer
            self.attempt.check()
            approved = value.strip() == expected.encode()
            self.attempt.command_approved = approved
            return ApprovalDecision.APPROVE if approved else ApprovalDecision.DENY
        except asyncio.CancelledError:
            self.attempt.revoke('approval_cancelled')
            raise
        finally:
            loop.remove_reader(fd)
            self.busy = False
