"""Full bounded legacy replacement approval, no cached or model-supplied grants."""
import asyncio
from dataclasses import dataclass
import json
import sys
from ..mcp_client.approval import ApprovalDecision, CREDENTIAL, SENSITIVE


@dataclass(frozen=True)
class FileApprovalRequest:
    display_json: str


def inspectable_write(path, content, expected_sha256):
    display = json.dumps({'tool': 'write_file', 'path': path, 'content': content,
                          'existing_file': expected_sha256 is not None, 'os_sandbox': False,
                          'approval': 'one full replacement only; no automatic parent creation'}, ensure_ascii=True)
    if len(display) > 10000 or CREDENTIAL.search(display) or SENSITIVE.search(display): return None
    return FileApprovalRequest(display)


async def cli_file_approval(request):
    if not sys.stdin.isatty() or not sys.stdout.isatty(): return ApprovalDecision.DENY
    print('[LEGACY FILE APPROVAL] ' + request.display_json)
    print('完整覆盖写入，无 OS 沙盒。仅批准本次？输入 yes: ', end='', flush=True)
    return ApprovalDecision.APPROVE if (await asyncio.to_thread(input)).strip() == 'yes' else ApprovalDecision.DENY
