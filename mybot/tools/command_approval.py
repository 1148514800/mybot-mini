"""Separate native command approvals; no MCP server identity or authorization cache."""
import asyncio
import json
import sys
from dataclasses import dataclass
from ..mcp_client.approval import ApprovalDecision, CREDENTIAL, SENSITIVE

MAX_DISPLAY = 12000


@dataclass(frozen=True, slots=True)
class CommandApprovalRequest:
    mode: str
    cwd: str
    argv: tuple[str, ...]  # Complete EFFECTIVE command, including pinned runtime/options.
    timeout_seconds: int
    os_sandbox: bool
    display_json: str


def inspectable_command(mode, cwd, argv, timeout):
    # Escaping controls/bidi is safe only when the entire JSON remains visible.
    if any(CREDENTIAL.search(a) or SENSITIVE.search(a) for a in argv): return None
    payload = {'tool': 'run_command', 'execution_mode': mode, 'cwd': cwd, 'argv': argv,
               'timeout_seconds': timeout, 'os_sandbox': mode == 'macos_readonly',
               'approval': 'one call only; includes synthetic isolation self-test in sandbox mode',
               'limits': '8 MiB/file; 32 MiB temporary data/512 entries monitored; bounded output'}
    display = json.dumps(payload, ensure_ascii=True, allow_nan=False)
    if len(display) > MAX_DISPLAY: return None
    return CommandApprovalRequest(mode, cwd, tuple(argv), timeout, mode == 'macos_readonly', display)


async def cli_command_approval(request, *, output=None):
    # A host may retain its terminal while capturing unrelated Agent output.
    # Never fall back to __stdout__ or /dev/tty when the selected channel is not a TTY.
    output = sys.stdout if output is None else output
    if not sys.stdin.isatty() or not output.isatty(): return ApprovalDecision.DENY
    print('[NATIVE COMMAND APPROVAL] ' + request.display_json, file=output)
    if request.mode == 'host_confirm':
        print('警告：以当前系统用户权限执行，无 OS 沙盒；可读写外部文件、启动其他程序或访问网络。', file=output)
    else:
        print('macOS Seatbelt：Workspace 只读，仅本次临时目录可写，网络禁止；自检失败则拒绝。', file=output)
    print('仅批准此命令一次？输入 yes 批准，其他输入拒绝: ', end='', file=output, flush=True)
    answer = await asyncio.to_thread(input)
    return ApprovalDecision.APPROVE if answer.strip() == 'yes' else ApprovalDecision.DENY


async def authorize_command(provider, request):
    if request is None: return False, 'approval_uninspectable'
    if provider is None: return False, 'approval_unavailable'
    try: decision = await provider(request)
    except Exception: return False, 'approval_error'
    return (True, 'approved') if decision is ApprovalDecision.APPROVE else (False, 'approval_denied')
