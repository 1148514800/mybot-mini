"""Explicitly approved native commands with independent lifecycle and Seatbelt gate."""
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from jsonschema import Draft202012Validator
from .base import ToolResult
from .repository import RepositoryTool
from .arguments import parse_object
from .command_config import validate_command
from .command_approval import inspectable_command, authorize_command
from .command_process import resolve_launch, run_process
from . import macos_sandbox
from ..mcp_client.approval import CREDENTIAL

MAX_ARGUMENT_BYTES = 16384


def parse_arguments(raw):
    return parse_object(raw, max_bytes=MAX_ARGUMENT_BYTES, max_depth=4)


def safe_output(data, replacements):
    try: text = data.decode('utf-8'); replaced = False
    except UnicodeDecodeError: text = data.decode('utf-8', errors='replace'); replaced = True
    for path, label in sorted(replacements, key=lambda pair: -len(pair[0])):
        text = text.replace(path, label)
    text = re.sub(r'/(?:Users|Volumes|home|private/(?:var/folders|tmp)|tmp)/[^\s"\']+', '<external-path>', text)
    text = CREDENTIAL.sub('<redacted>', text)
    text = ''.join(ch if ch in '\n\t' or unicodedata.category(ch) not in ('Cc', 'Cf') else ascii(ch)[1:-1] for ch in text)
    return text, replaced


class RunCommandTool(RepositoryTool):
    name = 'run_command'
    description = ('Run a Python test/check command after separate one-call human approval. argv array, no shell string. '
        'Modes are host_confirm (NO OS isolation) or macos_readonly (verified Seatbelt, workspace read-only, network denied). '
        'Only python/python3, pytest/ruff via validated Python, or uv run --no-sync python ... . '
        'Nonzero completed exit is real failure feedback, not a passed test. Output/time/temp limits apply.')
    private_arguments = True
    parameters = {'type': 'object', 'properties': {
        'argv': {'type': 'array', 'minItems': 1, 'maxItems': 32,
                 'items': {'type': 'string', 'minLength': 1, 'maxLength': 2048}},
        'cwd': {'type': 'string', 'minLength': 1, 'maxLength': 4096},
        'timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 60}},
        'required': ['argv'], 'additionalProperties': False}

    def __init__(self, workspace, *, command, patch_mode, approval_provider=None):
        super().__init__(workspace)
        self.settings = validate_command(command, coding_enabled=True, patch_mode=patch_mode)
        if self.settings.mode == 'off': raise ValueError('command_disabled')
        self.approval_provider = approval_provider
        self.execution_guard = None  # Optional per-turn host constraint, never a model argument.

    def _cwd(self, value):
        raw = Path(value)
        if raw.is_absolute() or '..' in raw.parts: raise ValueError('invalid_cwd')
        target = self.resolve(value)
        probe = self.workspace
        for part in raw.parts:
            probe /= part
            if probe.is_symlink(): raise ValueError('invalid_cwd')
        if not target.is_dir(): raise ValueError('invalid_cwd')
        return target

    @staticmethod
    def failure_result(reason, *, mode=None, approved=False, permission=False):
        meta = dict(status=reason, approved=approved, execution_mode=mode, spawned=False,
            completed=False, process_terminated=False, sandbox_applied=False, exit_code=None,
            timed_out=False, output_truncated=False, stdout_bytes=0, stderr_bytes=0,
            duration_ms=0, execution_evidence=False, command_fatal=True)
        if permission: meta['permission_denied'] = True
        return ToolResult(False, error=reason, metadata=meta)

    async def execute(self, **args):
        approved = False; fd = None; result = None; settings = self.settings; mode = settings.mode
        try:
            args = parse_arguments(args)
            if not Draft202012Validator(self.parameters).is_valid(args): raise ValueError('invalid_arguments')
            argv = tuple(args['argv'])
            if any('\0' in arg for arg in argv) or sum(len(a.encode('utf-8')) for a in argv) > 8192:
                raise ValueError('invalid_arguments')
            timeout = args.get('timeout_seconds', settings.timeout_seconds)
            if timeout > settings.timeout_seconds: raise ValueError('timeout_exceeds_configuration')
            cwd = self._cwd(args.get('cwd', '.')); relative = cwd.relative_to(self.workspace).as_posix()
            fd = os.open(cwd, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            identity = lambda s: (s.st_dev, s.st_ino)
            cwd_identity = identity(os.fstat(fd))
            launch = resolve_launch(argv, self.workspace)
            request = inspectable_command(mode, relative, launch.argv, timeout)
            approved, reason = await authorize_command(self.approval_provider, request)
            if not approved: return self.failure_result(reason, mode=mode, permission=True)
            if self.execution_guard is not None: timeout = self.execution_guard(launch, timeout)
            # Revalidate the exact approved argv/cwd/runtime, never a mutable caller payload.
            if self._cwd(relative) != cwd or identity(cwd.stat()) != cwd_identity:
                raise ValueError('cwd_changed')
            if resolve_launch(argv, self.workspace) != launch: raise ValueError('runtime_changed')
            if mode == 'macos_readonly' and not await macos_sandbox.verify_sandbox(launch.roots):
                return self.failure_result('sandbox_unavailable', mode=mode, approved=True)
            with tempfile.TemporaryDirectory(prefix='mybot-command-', dir='/private/tmp' if os.uname().sysname == 'Darwin' else '/tmp') as folder:
                temp = Path(folder).resolve()
                sandbox = macos_sandbox.profile(self.workspace, temp, launch.roots) if mode == 'macos_readonly' else None
                # The self-test may yield: recheck once more immediately before spawn.
                if self._cwd(relative) != cwd or identity(cwd.stat()) != cwd_identity or resolve_launch(argv, self.workspace) != launch:
                    raise ValueError('execution_snapshot_changed')
                if self.execution_guard is not None: timeout = self.execution_guard(launch, timeout)
                result = await run_process(launch, cwd=cwd, cwd_fd=fd, temp=temp, timeout=timeout,
                    output_limit=settings.max_output_bytes, profile=sandbox)
                replacements = [(str(self.workspace), '<workspace>'), (str(temp), '<run-temp>'),
                    (str(Path.home()), '<home>'), *((p, '<runtime>') for p in launch.roots)]
                stdout, out_replaced = safe_output(result.stdout, replacements)
                stderr, err_replaced = safe_output(result.stderr, replacements)
            completed = result.status == 'completed'
            success = completed and result.exit_code == 0
            metadata = dict(status=result.status, approved=True, execution_mode=mode,
                spawned=result.spawned, completed=completed, process_terminated=result.process_terminated,
                sandbox_applied=result.sandbox_applied, exit_code=result.exit_code,
                command_nonzero=completed and result.exit_code != 0,
                timed_out=result.status == 'timed_out', output_truncated=result.status == 'output_limit_exceeded',
                stdout_bytes=result.stdout_bytes, stderr_bytes=result.stderr_bytes, duration_ms=result.duration_ms,
                encoding_replaced=out_replaced or err_replaced, execution_evidence=success, command_fatal=not completed)
            return ToolResult(success, json.dumps(dict(stdout=stdout, stderr=stderr), ensure_ascii=True),
                error=None if success else ('command_nonzero' if completed else result.status), metadata=metadata)
        except Exception as exc:
            if result is not None:
                failed = self.failure_result('process_state_unknown', mode=mode, approved=approved)
                failed.metadata.update(spawned=result.spawned, sandbox_applied=result.sandbox_applied,
                    exit_code=result.exit_code, process_terminated=result.process_terminated, duration_ms=result.duration_ms)
                return failed
            reason = str(exc) if isinstance(exc, ValueError) and str(exc).isidentifier() else ('executable_missing' if isinstance(exc, FileNotFoundError) else 'command_execution_failed')
            return self.failure_result(reason, mode=mode, approved=approved)
        finally:
            if fd is not None: os.close(fd)
