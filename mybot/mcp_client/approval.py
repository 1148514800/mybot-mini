"""Local, one-call approvals. Never infer authority from model/server text."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from enum import Enum


class ApprovalDecision(Enum):
    APPROVE = 'approved'
    DENY = 'denied'


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    server: str
    tool: str
    arguments_json: str


SENSITIVE = re.compile(r'password|passwd|secret|token|api.?key|authorization|credential', re.I)
CREDENTIAL = re.compile(r'(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|Bearer\s+\S+)', re.I)
MAX_DISPLAY = 4000


def inspectable_request(server, tool, arguments):
    """Escape terminal controls; hidden/oversized arguments cannot be approved."""
    hidden = False
    def redact(value):
        nonlocal hidden
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if SENSITIVE.search(key):
                    hidden = True
                    result[key] = '<redacted>'
                else:
                    result[key] = redact(item)
            return result
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, str) and CREDENTIAL.search(value):
            hidden = True
            return '<redacted>'
        return value
    text = json.dumps(redact(arguments), ensure_ascii=True, sort_keys=True, allow_nan=False)
    if hidden or len(text) > MAX_DISPLAY:
        return None
    return ApprovalRequest(server, tool, text)


async def cli_approval(request: ApprovalRequest) -> ApprovalDecision:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return ApprovalDecision.DENY
    # JSON ensure_ascii escapes ANSI, control characters, newlines and bidi text.
    print(f'[APPROVAL] Server: {request.server}  Tool: mcp__{request.server}__{request.tool}\nPolicy: confirm\nArguments: {request.arguments_json}')
    answer = await asyncio.to_thread(input, '仅本次执行？输入 yes 批准，其他输入拒绝: ')
    return ApprovalDecision.APPROVE if answer.strip() == 'yes' else ApprovalDecision.DENY


async def authorize(provider, server, tool, arguments):
    request = inspectable_request(server, tool, arguments)
    if request is None:
        return False, 'approval_uninspectable'
    if provider is None:
        return False, 'approval_unavailable'
    try:
        decision = await provider(request)
    except Exception:
        return False, 'approval_error'
    return (True, 'approved') if decision is ApprovalDecision.APPROVE else (False, 'approval_denied')
