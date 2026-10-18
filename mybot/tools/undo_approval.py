"""Human-initiated single-capsule approval. No model tool and no cached grants."""
import asyncio
from dataclasses import dataclass
import json
import sys
from ..mcp_client.approval import ApprovalDecision, CREDENTIAL, SENSITIVE


@dataclass(frozen=True, slots=True)
class UndoApprovalRequest:
    files: tuple[tuple[str, str, str, str | None], ...]
    display_json: str


def undo_request(entries):
    files = tuple(sorted((e.relative_path, 'restore' if e.original_existed else 'remove_added', e.final_sha256, e.original_sha256) for e in entries))
    if not files or any(CREDENTIAL.search(p) or SENSITIVE.search(p) for p, _, _, _ in files): return None
    text = json.dumps({'action': 'undo_native_patches_once', 'files': files}, ensure_ascii=True)
    if len(text) > 12000: return None
    return UndoApprovalRequest(files, text)


async def cli_undo_approval(request):
    if not sys.stdin.isatty() or not sys.stdout.isatty(): return ApprovalDecision.DENY
    print('[UNDO APPROVAL] ' + request.display_json)
    answer = await asyncio.to_thread(input, '仅撤销这些原生Patch一次？输入 yes 批准，其他输入拒绝: ')
    return ApprovalDecision.APPROVE if answer.strip() == 'yes' else ApprovalDecision.DENY


async def authorize_undo(provider, request):
    if provider is None or request is None: return False
    try: return await provider(request) is ApprovalDecision.APPROVE
    except Exception: return False
