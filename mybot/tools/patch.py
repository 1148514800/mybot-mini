"""Structured, bounded text edits. POSIX single-file publication, best-effort recovery.

No shell, Git, test runner, persistent journal or cross-file crash atomicity.
Pinned dir_fds reduce races; final pathname checks and rename are NOT a filesystem
compare-and-swap and do not defend against every malicious concurrent writer.
"""
from __future__ import annotations

import ctypes
import difflib
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import time
import stat
import sys
from dataclasses import dataclass, field

from jsonschema import Draft202012Validator

from .base import ToolResult
from .repository import RepositoryTool, MAX_FILE_BYTES

MAX_PATCH_BYTES = 256 * 1024
MAX_DIFF_CHARS = 24000
_RETRY = frozenset({'stale_file_hash', 'anchor_not_found', 'ambiguous_context'})
# Pure input failures only while validating a preview. Do not extend write recovery.
_PREVIEW_CORRECTABLE = frozenset({'invalid_arguments', 'overlapping_edits', 'no_effective_changes'})
_STRING = {'type': 'string', 'maxLength': MAX_PATCH_BYTES}
_PATH = {'type': 'string', 'minLength': 1, 'maxLength': 4096}
_EDIT = {'type': 'object', 'properties': {
    'old_text': {**_STRING, 'minLength': 1}, 'new_text': _STRING},
    'required': ['old_text', 'new_text'], 'additionalProperties': False}
_UPDATE = {'type': 'object', 'properties': {
    'op': {'const': 'update'}, 'path': _PATH,
    'expected_sha256': {'description': 'Copy exactly the 64 hexadecimal characters from read_file_range metadata.file_sha256; no prefix, placeholder or excerpt hash.', 'type': 'string', 'pattern': '^[a-fA-F0-9]{64}$', 'minLength': 64, 'maxLength': 64},
    'edits': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'items': _EDIT}},
    'required': ['op', 'path', 'expected_sha256', 'edits'], 'additionalProperties': False}
_ADD = {'type': 'object', 'properties': {
    'op': {'const': 'add'}, 'path': _PATH, 'content': _STRING},
    'required': ['op', 'path', 'content'], 'additionalProperties': False}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bounded_arguments(args):
    # Bound traversal and strings BEFORE schema validation/serialization/encoding.
    pending = [(args, 0)]
    budget = MAX_PATCH_BYTES
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 12 or nodes > 2048:
            raise ValueError('patch_too_large')
        if isinstance(value, str):
            if len(value) > budget:
                raise ValueError('patch_too_large')
            try: budget -= len(value.encode('utf-8'))
            except UnicodeEncodeError: raise ValueError('invalid_utf8') from None
        elif isinstance(value, dict):
            if len(value) > 128: raise ValueError('patch_too_large')
            pending.extend((x, depth + 1) for pair in value.items() for x in pair)
        elif isinstance(value, list):
            if len(value) > 128: raise ValueError('patch_too_large')
            pending.extend((x, depth + 1) for x in value)
        elif value is not None and type(value) not in (bool, int, float):
            raise ValueError('invalid_arguments')
        if budget < 0: raise ValueError('patch_too_large')
    # Canonical compact UTF-8 JSON body is the specified byte budget (including escapes).
    if len(json.dumps(args, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')) > MAX_PATCH_BYTES:
        raise ValueError('patch_too_large')


def parse_arguments(raw):
    from .arguments import parse_object
    return parse_object(raw, max_bytes=MAX_PATCH_BYTES, size_error='patch_too_large')


def argument_feedback(args):
    """Bounded schema labels only; never serialize ValidationError/message/instance."""
    issues = []
    allowed = {'changes', 'dry_run', 'op', 'path', 'expected_sha256', 'edits',
               'old_text', 'new_text', 'content'}
    def record(error, prefix=()):
        if error.context:
            # Select only the declared operation's branch; no errors about the other op.
            op = error.instance.get('op') if isinstance(error.instance, dict) else None
            branch = 0 if op == 'update' else (1 if op == 'add' else None)
            if branch is not None:
                for child in error.context:
                    if child.schema_path[0] == branch: record(child, (*prefix, *error.path))
                return
        path = [str(v) if type(v) is int else (v if v in allowed else '<field>')
                for v in (*prefix, *error.path)]
        category = error.validator if error.validator in {
            'type', 'required', 'additionalProperties', 'pattern', 'minLength',
            'maxLength', 'minItems', 'maxItems', 'oneOf', 'const'} else 'schema'
        if len(issues) < 4: issues.append({'field': '.'.join(path) or '$', 'category': category})
    for error in Draft202012Validator(ApplyPatchTool.parameters).iter_errors(args):
        record(error)
        if len(issues) >= 4: break
    return {'version': 'patch-input-v1', 'issues': issues,
            'action': ('correct_input_and_preview; preserve_changes_for_write'
                       if args.get('dry_run', True) is True else 'stop_write_no_replay')}


def text_bytes(text):
    data = text.encode('utf-8')
    if b'\0' in data: raise ValueError('binary_file')
    if len(data) > MAX_FILE_BYTES: raise ValueError('file_too_large')
    return data


def check_metadata(fd, info):
    """Refuse metadata we cannot preserve; no copying ACLs or opaque xattrs."""
    if info.st_uid != os.geteuid() or info.st_gid != os.getegid():
        raise ValueError('unsupported_ownership')
    if getattr(info, 'st_flags', 0) or info.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        raise ValueError('unsupported_metadata')
    if sys.platform == 'darwin':
        libc = ctypes.CDLL(None, use_errno=True)
        libc.flistxattr.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        libc.flistxattr.restype = ctypes.c_ssize_t
        length = libc.flistxattr(fd, None, 0, 0)
        if length < 0 or length > 4096: raise ValueError('unsupported_metadata')
        names = ctypes.create_string_buffer(length)
        if libc.flistxattr(fd, names, length, 0) != length: raise ValueError('unsupported_metadata')
        if set(names.raw.split(b'\0')) - {b'', b'com.apple.provenance'}:
            raise ValueError('unsupported_metadata')
        # System-managed provenance cannot always be set by userspace. Require
        # byte equality on replacement/backup rather than silently dropping it.
        provenance = None
        if length:
            libc.fgetxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p,
                                      ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
            libc.fgetxattr.restype = ctypes.c_ssize_t
            buffer = ctypes.create_string_buffer(4096)
            count = libc.fgetxattr(fd, b'com.apple.provenance', buffer, 4096, 0, 0)
            if count < 0: raise ValueError('unsupported_metadata')
            provenance = buffer.raw[:count]
        libc.acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
        libc.acl_get_fd_np.restype = ctypes.c_void_p
        libc.acl_get_entry.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        libc.acl_free.argtypes = [ctypes.c_void_p]
        acl = libc.acl_get_fd_np(fd, 0x100)  # Darwin ACL_TYPE_EXTENDED
        if not acl and ctypes.get_errno() != 2: raise ValueError('unsupported_metadata')
        try:
            entry = ctypes.c_void_p()
            ctypes.set_errno(0)
            if acl and libc.acl_get_entry(acl, 0, ctypes.byref(entry)) != -1:
                raise ValueError('unsupported_metadata')
            # Darwin returns -1/EINVAL for an empty ACL (no first entry).
            if acl and ctypes.get_errno() != 22: raise ValueError('unsupported_metadata')
        finally:
            if acl: libc.acl_free(acl)
        return provenance
    elif sys.platform == 'linux' and hasattr(os, 'listxattr'):
        if os.listxattr(fd): raise ValueError('unsupported_metadata')
    else:
        raise ValueError('unsupported_filesystem')


@dataclass
class Prepared:
    path: str
    op: str
    parent: int
    name: str
    before: bytes
    after: bytes
    original: os.stat_result | None
    attributes: bytes | None = None
    stage: str | None = None
    backup: str | None = None
    staged_info: os.stat_result | None = None
    temp_inodes: dict = field(default_factory=dict)


def identity(info):
    return info.st_dev, info.st_ino


def version(info):
    return identity(info), info.st_mode, info.st_uid, info.st_gid, info.st_nlink, info.st_mtime_ns, info.st_ctime_ns


RECEIPT_ERRORS = frozenset({'malformed_receipt', 'unknown_receipt', 'expired_receipt',
    'consumed_receipt', 'wrong_attempt', 'stale_file_hash', 'metadata_changed',
    'patch_write_disabled', 'write_failed', 'cleanup_uncertain'})


@dataclass(frozen=True, repr=False)
class PreviewReceipt:
    digest: str
    scope: str
    workspace: tuple
    changes: bytes  # immutable, bounded JSON; never persisted
    fingerprints: tuple
    summary: str
    created: float
    expires: float


class ApplyPatchTool(RepositoryTool):
    name = 'apply_patch'
    description = ('Precisely update UTF-8 files using full-file SHA256 and unique non-overlapping old_text, '
                   'or add new files in existing directories. Default dry_run=true previews only. '
                   'Write requires patch_mode=write and explicit dry_run=false. No tests or commands run. '
                   'Each update requires op, path, expected_sha256 and edits (each edit: old_text and new_text); '
                   'each add requires op, path and content. No extra fields at any level. '
                   'expected_sha256 must be exactly 64 hex characters copied from read_file_range metadata.file_sha256. '
                   'Preview first; after success reuse identical changes, changing only dry_run to false. '
                   'A successful preview does not grant write permission. '
                   'Reread and rebuild on stale_file_hash/anchor conflicts; never replay blindly. Hidden/private paths denied.')
    private_arguments = True
    parameters = {'type': 'object', 'properties': {
        'dry_run': {'type': 'boolean', 'default': True,
                    'description': 'true previews only (default); false requests a write, still requiring patch_mode=write.'},
        'changes': {'type': 'array', 'minItems': 1, 'maxItems': 8,
                    'description': 'Use the declared update/add structure only. After a successful preview, if target files '
                        'and intended edits are unchanged, reuse the same changes and set only dry_run=false. '
                        'If changes are revised, preview again.',
                    'items': {'oneOf': [_UPDATE, _ADD]}}},
        'required': ['changes'], 'additionalProperties': False}

    def __init__(self, workspace: Path, *, patch_mode: str, preview_receipt=False, receipt_ttl=300):
        super().__init__(workspace)
        if patch_mode not in ('preview', 'write'): raise ValueError('invalid_patch_mode')
        self.patch_mode = patch_mode
        self.observer = None  # Host-only, opt-in; never a Tool argument.
        if type(preview_receipt) is not bool: raise ValueError('invalid_receipt_mode')
        if type(receipt_ttl) not in (int, float) or not 0 < receipt_ttl <= 300:
            raise ValueError('invalid_receipt_ttl')
        self.preview_receipt = preview_receipt
        self.receipt_ttl = receipt_ttl
        self.receipt_commit_guard = None  # Host controller deadline fence, never a model argument.
        self._receipt = None
        self._receipt_scope = None
        self._receipt_tombstone = None  # one digest + diagnostic, never changes/token
        if preview_receipt:
            self.parameters = {'type': 'object', 'properties': {
                'dry_run': {'type': 'boolean', 'default': True},
                'changes': {**self.parameters['properties']['changes'],
                    'description': 'Preview only: bounded update/add changes. Commit with preview_receipt instead.'},
                'preview_receipt': {'type': 'string', 'pattern': '^[a-f0-9]{64}$',
                                    'minLength': 64, 'maxLength': 64}},
                'additionalProperties': False,
                'oneOf': [
                    {'required': ['changes'], 'properties': {'dry_run': {'const': True}},
                     'not': {'required': ['preview_receipt']}},
                    {'required': ['dry_run', 'preview_receipt'],
                     'properties': {'dry_run': {'const': False}}, 'not': {'required': ['changes']}}]}
            self.description = ('Preview with changes and dry_run=true. Use the returned opaque preview_receipt '
                'to explicitly commit with only dry_run=false and preview_receipt. Never resend changes for commit. '
                'Receipt expires, is single-use and scoped to this turn. Write permission and all safety checks still apply. '
                'After commit run approved current-revision tests. Never replay a failed commit.')

    def _revoke_receipt(self, reason='unknown_receipt'):
        if self._receipt is not None:
            self._receipt_tombstone = (self._receipt.digest, reason)
        self._receipt = None

    def begin_receipt_scope(self):
        self.end_receipt_scope()
        self._receipt_scope = secrets.token_hex(32)

    def end_receipt_scope(self):
        self._revoke_receipt('wrong_attempt')
        self._receipt_scope = None

    def _workspace_stamp(self):
        return str(self.workspace), identity(os.stat(self.workspace, follow_symlinks=False))

    @staticmethod
    def _fingerprints(items):
        return tuple((x.path, identity(os.fstat(x.parent)), sha(x.before) if x.original else None,
                      version(x.original) if x.original else None, x.attributes, sha(x.after)) for x in items)

    def _consume_receipt(self, token):
        receipt = self._receipt
        self._revoke_receipt('consumed_receipt')  # every explicit attempt consumes before any safety/write checks
        if not isinstance(token, str) or re.fullmatch('[a-f0-9]{64}', token) is None:
            raise ValueError('malformed_receipt')
        digest = sha(token.encode('ascii'))
        if receipt is None or not secrets.compare_digest(receipt.digest, digest):
            if self._receipt_tombstone and secrets.compare_digest(self._receipt_tombstone[0], digest):
                raise ValueError(self._receipt_tombstone[1])
            raise ValueError('unknown_receipt')
        if not self._receipt_scope or receipt.scope != self._receipt_scope:
            raise ValueError('wrong_attempt')
        if receipt.workspace != self._workspace_stamp(): raise ValueError('wrong_attempt')
        if time.monotonic() >= receipt.expires: raise ValueError('expired_receipt')
        return receipt

    def _guard_receipt_commit(self, receipt):
        if receipt.scope != self._receipt_scope or receipt.workspace != self._workspace_stamp():
            raise ValueError('wrong_attempt')
        if time.monotonic() >= receipt.expires: raise ValueError('expired_receipt')
        if self.receipt_commit_guard is not None: self.receipt_commit_guard()

    def _check_receipt_files(self, receipt, items, diff):
        now = self._fingerprints(items)
        for old, new in zip(receipt.fingerprints, now):
            if old[2] != new[2]: raise ValueError('stale_file_hash')
            if old != new: raise ValueError('metadata_changed')
        if len(now) != len(receipt.fingerprints) or sha(diff.encode()) != receipt.summary:
            raise ValueError('metadata_changed')

    def redact_receipt_history(self, messages):
        # The live request needs the capability; Session/disk must never recover it or its changes.
        import copy
        clean = copy.deepcopy(messages)
        ids = {c.get('id') for m in clean for c in m.get('tool_calls') or []
               if c.get('function', {}).get('name') == self.name}
        for message in clean:
            if message.get('role') == 'tool' and message.get('tool_call_id') in ids:
                message['content'] = '[Patch result omitted after receipt scope]'
            for call in message.get('tool_calls') or []:
                if call.get('function', {}).get('name') == self.name:
                    call['function']['arguments'] = '{}'
            if message.get('role') == 'assistant' and isinstance(message.get('content'), str):
                message['content'] = re.sub(r'(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])', '<opaque-id>', message['content'])
        def scrub(value):
            if isinstance(value, str):
                return re.sub(r'(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])',
                    lambda match: '<opaque-id:' + sha(match[0].encode())[:16] + '>', value)
            if isinstance(value, list): return [scrub(item) for item in value]
            if isinstance(value, dict): return {key: scrub(item) for key, item in value.items()}
            return value
        return scrub(clean)

    def _open_parent(self, path):
        # Reuse the Phase19 resolver AND forbid every lexical symlink component.
        raw = Path(path)
        if '..' in raw.parts: raise ValueError('path_outside_workspace')
        target = self.resolve(path)
        if raw.is_absolute(): raw = raw.relative_to(self.workspace)
        if not raw.parts or raw == Path('.'): raise ValueError('invalid_path')
        fd = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in raw.parts[:-1]:
                try: child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError: raise ValueError('parent_missing') from None
                os.close(fd); fd = child
            # Reject links even when the shared resolver accepts an internal alias.
            probe = self.workspace
            for part in raw.parts:
                probe /= part
                if probe.is_symlink(): raise ValueError('symlink_denied')
            if target != self.workspace / raw: raise ValueError('invalid_path')
            return fd, raw.name, raw.as_posix()
        except BaseException:
            os.close(fd)
            raise

    def _read(self, parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode): raise ValueError('not_regular_file')
            if info.st_nlink != 1: raise ValueError('hardlink_denied')
            if info.st_size > MAX_FILE_BYTES: raise ValueError('file_too_large')
            attributes = check_metadata(fd, info)
            chunks = []; count = 0
            while count <= MAX_FILE_BYTES:
                chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - count))
                if not chunk: break
                chunks.append(chunk); count += len(chunk)
            data = b''.join(chunks)
            if len(data) > MAX_FILE_BYTES: raise ValueError('file_too_large')
            if b'\0' in data: raise ValueError('binary_file')
            try: data.decode('utf-8')
            except UnicodeDecodeError: raise ValueError('invalid_utf8') from None
            if version(info) != version(os.fstat(fd)): raise ValueError('stale_file_hash')
            return data, info, attributes
        finally: os.close(fd)

    def _recheck(self, item, *, published=False):
        fd, name, _ = self._open_parent(item.path)
        try:
            if identity(os.fstat(fd)) != identity(os.fstat(item.parent)):
                raise ValueError('path_changed')
        finally: os.close(fd)
        if item.op == 'add' and not published:
            try: os.stat(name, dir_fd=item.parent, follow_symlinks=False)
            except FileNotFoundError: return
            raise ValueError('target_exists')
        data, info, attributes = self._read(item.parent, name)
        if attributes != item.attributes: raise ValueError('unsupported_metadata')
        expected_info = item.staged_info if published else item.original
        if data != (item.after if published else item.before) or (identity(info) != identity(expected_info)):
            raise ValueError('stale_file_hash')
        if not published and version(info) != version(item.original): raise ValueError('stale_file_hash')
        if stat.S_IMODE(info.st_mode) != (stat.S_IMODE(item.original.st_mode) if item.original else 0o600):
            raise ValueError('unsupported_metadata')

    def _preflight(self, args, items):
        paths = set(); inodes = set()
        for change in args['changes']:
            fd, name, path = self._open_parent(change['path'])
            # Transfer fd ownership immediately, including failures below.
            item = Prepared(path, change['op'], fd, name, b'', b'', None)
            items.append(item)
            if path in paths: raise ValueError('duplicate_path')
            paths.add(path)
            if item.op == 'add':
                self._recheck(item)
                item.after = text_bytes(change['content'])
            else:
                data, info, attributes = self._read(fd, name)
                item.before, item.original, item.attributes = data, info, attributes
                if identity(info) in inodes: raise ValueError('duplicate_path')
                inodes.add(identity(info))
                if sha(data) != change['expected_sha256'].lower(): raise ValueError('stale_file_hash')
                edits = []
                for edit in change['edits']:
                    old = text_bytes(edit['old_text']); new = text_bytes(edit['new_text'])
                    start = data.find(old)
                    if start < 0: raise ValueError('anchor_not_found')
                    if data.find(old, start + 1) >= 0: raise ValueError('ambiguous_context')
                    edits.append((start, start + len(old), new))
                edits.sort()
                if any(a[1] > b[0] for a, b in zip(edits, edits[1:])): raise ValueError('overlapping_edits')
                size = len(data) + sum(len(new) - (end - start) for start, end, new in edits)
                if size > MAX_FILE_BYTES: raise ValueError('file_too_large')
                chunks = []; last = 0
                for start, end, new in edits:
                    chunks.extend((data[last:start], new)); last = end
                item.after = b''.join([*chunks, data[last:]])
        if not any(x.op == 'add' or x.before != x.after for x in items):
            raise ValueError('no_effective_changes')
        # Unchanged update entries are verified but not published.

    def _temp(self, item, body, mode):
        name = '.mybot-patch-' + secrets.token_hex(16)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=item.parent)
        try:
            item.temp_inodes[name] = identity(os.fstat(fd))
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(body); stream.flush()
            os.fchmod(fd, mode)
            check_metadata(fd, os.fstat(fd))
            os.fsync(fd)
        finally: os.close(fd)
        actual, info, attributes = self._read(item.parent, name)
        if actual != body: raise ValueError('stage_verification_failed')
        if item.original and attributes != item.attributes: raise ValueError('unsupported_metadata')
        if not item.original: item.attributes = attributes
        return name, info

    def _stage(self, item):
        mode = stat.S_IMODE(item.original.st_mode) if item.original else 0o600
        item.stage, item.staged_info = self._temp(item, item.after, mode)
        if item.op == 'update': item.backup, _ = self._temp(item, item.before, mode)

    def _publish(self, item):
        if item.op == 'add':
            # POSIX same-directory hardlink publication is atomic no-clobber;
            # unavailable/unsupported filesystems fail closed. Not a Windows API.
            os.link(item.stage, item.name, src_dir_fd=item.parent,
                    dst_dir_fd=item.parent, follow_symlinks=False)
            os.unlink(item.stage, dir_fd=item.parent)
        else:
            os.replace(item.stage, item.name, src_dir_fd=item.parent, dst_dir_fd=item.parent)
        item.stage = None

    def _recover(self, attempted):
        conflict = False; uncertain = False
        for item in reversed(attempted):
            try:
                # A failed publication may have left the original unchanged.
                try:
                    self._recheck(item)
                    continue
                except (OSError, ValueError): pass
                self._recheck(item, published=True)
                if item.op == 'add':
                    os.unlink(item.name, dir_fd=item.parent)
                    self._recheck(item)
                else:
                    backup, backup_info, attrs = self._read(item.parent, item.backup)
                    if (backup != item.before or attrs != item.attributes
                            or identity(backup_info) != item.temp_inodes[item.backup]
                            or stat.S_IMODE(backup_info.st_mode) != stat.S_IMODE(item.original.st_mode)):
                        raise ValueError('rollback_backup_changed')
                    os.replace(item.backup, item.name, src_dir_fd=item.parent, dst_dir_fd=item.parent)
                    item.backup = None
                    data, info, attributes = self._read(item.parent, item.name)
                    if attributes != item.attributes or data != item.before or stat.S_IMODE(info.st_mode) != stat.S_IMODE(item.original.st_mode):
                        raise OSError('recovery_verification_failed')
            except ValueError: conflict = True
            except Exception: uncertain = True
        return 'partial_failure_possible' if uncertain else ('rollback_conflict' if conflict else 'commit_failed_rolled_back')

    @staticmethod
    def _diff(items):
        parts = []; size = 0
        for item in items:
            # difflib sees raw newline characters; no newline normalization.
            lines = difflib.unified_diff(item.before.decode('utf-8').splitlines(keepends=True),
                item.after.decode('utf-8').splitlines(keepends=True),
                fromfile='/dev/null' if item.op == 'add' else 'a/' + item.path, tofile='b/' + item.path)
            for line in lines:
                if not line.endswith('\n'): line += '\n\\ No newline at end of file\n'
                room = MAX_DIFF_CHARS - size
                parts.append(line[:room]); size += min(len(line), room)
                if len(line) > room: return ''.join(parts), True
        return ''.join(parts), False

    async def execute(self, **args):
        # Synchronous local commit: no await/cancellation point within publication.
        items = []; attempted = []; result = None; phase = 'validation'
        dry_run = args.get('dry_run', True)
        receipt = None
        receipt_meta = {'patch_protocol': 'receipt' if self.preview_receipt else 'legacy',
            'receipt_created': False, 'receipt_commit_attempted': self.preview_receipt and dry_run is False,
            'receipt_commit_success': False, 'receipt_error_category': None,
            'preview_to_commit_consistent': None, 'file_revision_verified': False}
        if self.preview_receipt and self._receipt_scope:
            receipt_meta['receipt_scope_sha256'] = sha(self._receipt_scope.encode())
        try:
            if self.preview_receipt:
                if dry_run is False:
                    receipt = self._consume_receipt(args.get('preview_receipt'))
                else:
                    self._revoke_receipt()
                if not self._receipt_scope: raise ValueError('wrong_attempt')
            bounded_arguments(args); self.validate(args)
            if receipt is not None:
                args = {'dry_run': False, 'changes': json.loads(receipt.changes)}
            if sys.platform not in ('darwin', 'linux') or not hasattr(os, 'O_NOFOLLOW'):
                raise ValueError('unsupported_filesystem')
            if not dry_run and self.patch_mode != 'write': raise ValueError('patch_write_disabled')
            phase = 'preflight'
            self._preflight(args, items)
            phase = 'preview'
            changed = [x for x in items if x.op == 'add' or x.before != x.after]
            diff, truncated = self._diff(changed)
            if receipt is not None:
                self._check_receipt_files(receipt, items, diff)
                receipt_meta.update(preview_to_commit_consistent=True, file_revision_verified=True)
            if not dry_run:
                phase = 'write_preparation'
                if receipt is not None: self._guard_receipt_commit(receipt)
                if self.observer is not None: self.observer.before_publish(changed)
                for item in changed: self._stage(item)
                # Revalidate ALL versions before publishing the first file.
                for item in items: self._recheck(item)
                if receipt is not None: self._guard_receipt_commit(receipt)
                for item in changed:
                    self._recheck(item)
                    phase = 'publication'
                    attempted.append(item)
                    self._publish(item)
                    self._recheck(item, published=True)
                for item in changed: self._recheck(item, published=True)
            result = ToolResult(True, diff, metadata={
                'dry_run': dry_run, 'validation_ok': True, 'applied': not dry_run,
                'changed_files': [x.path for x in changed],
                'updated_files': [x.path for x in changed if x.op == 'update'],
                'added_files': [x.path for x in changed if x.op == 'add'],
                'before_sha256': {x.path: sha(x.before) if x.original else None for x in changed},
                'after_sha256': {x.path: sha(x.after) for x in changed},
                'preview_diff': diff if dry_run else None, 'diff_truncated': truncated,
                'rollback_status': 'not_needed', 'execution_evidence': not dry_run})
            if self.preview_receipt and dry_run:
                for item in items: self._recheck(item)
                token = secrets.token_hex(32)
                created = time.monotonic()
                self._receipt = PreviewReceipt(sha(token.encode()), self._receipt_scope,
                    self._workspace_stamp(), json.dumps(args['changes'], separators=(',', ':')).encode(),
                    self._fingerprints(items), sha(diff.encode()), created, created + self.receipt_ttl)
                receipt_meta['receipt_created'] = True
                result.metadata.update(preview_receipt=token, can_commit=self.patch_mode == 'write',
                    commit_arguments={'dry_run': False, 'preview_receipt': token})
        except Exception as exc:
            reason = self.failure(exc).error
            status = self._recover(attempted) if attempted else 'preflight_failed'
            result = ToolResult(False, error=reason, metadata={
                'status': status, 'rollback_status': status, 'failure_phase': phase, 'applied': False,
                'dry_run': dry_run if type(dry_run) is bool else True,
                'execution_evidence': False,
                'safe_to_retry': not attempted and (reason in _RETRY or
                    (dry_run is True and phase in ('validation', 'preflight') and reason in _PREVIEW_CORRECTABLE))})
        finally:
            if result is not None and result.error == 'invalid_arguments' and phase == 'validation':
                result.metadata['input_feedback'] = argument_feedback(args)
            cleanup_failed = False
            for item in items:
                for name, expected_inode in item.temp_inodes.items():
                    try:
                        info = os.stat(name, dir_fd=item.parent, follow_symlinks=False)
                        if identity(info) != expected_inode:
                            cleanup_failed = True
                            continue
                        os.unlink(name, dir_fd=item.parent)
                    except FileNotFoundError: pass
                    except OSError: cleanup_failed = True
                os.close(item.parent)
            if cleanup_failed and result is not None:
                result.success = False; result.error = 'temporary_cleanup_failed'
                result.metadata.update(status='partial_failure_possible', rollback_status='partial_failure_possible',
                                       failure_phase='cleanup', safe_to_retry=False, execution_evidence=False)
        if self.observer is not None and not dry_run:
            try:
                if result is not None and result.success and result.metadata.get('applied') is True:
                    self.observer.after_success(changed)
                else:
                    self.observer.on_failure(result)
            except Exception:
                result = ToolResult(False, error='journal_commit_failed', metadata={
                    'status': 'partial_failure_possible' if attempted else 'preflight_failed',
                    'failure_phase': 'journal', 'applied': False, 'execution_evidence': False, 'safe_to_retry': False})
                try: self.observer.on_failure(result)
                except Exception: pass
        if self.preview_receipt:
            if not result.success:
                self._revoke_receipt()
                category = result.error if result.error in RECEIPT_ERRORS else (
                    'metadata_changed' if result.error in ('unsupported_metadata', 'unsupported_ownership', 'path_changed') else 'write_failed')
                if result.metadata.get('status') in ('partial_failure_possible', 'rollback_conflict'):
                    category = 'cleanup_uncertain'
                receipt_meta['receipt_error_category'] = category
                if dry_run is False: result.metadata['safe_to_retry'] = False
                # Any failed write cannot claim file revision verification.
                receipt_meta['file_revision_verified'] = False
            receipt_meta['receipt_commit_success'] = bool(dry_run is False and result.success
                                                         and result.metadata.get('applied') is True)
        result.metadata.update(receipt_meta)
        result.metadata.update(patch_diagnostics(result, dry_run))
        return result


SAFE_PATCH_ERRORS = frozenset({
    'invalid_arguments', 'malformed_json', 'stale_file_hash', 'unsupported_ownership',
    'unsupported_metadata', 'path_changed', 'receipt_expired', 'receipt_invalid',
    'write_failed', 'execution_uncertain', 'unknown', 'anchor_not_found',
    'ambiguous_context', 'no_effective_changes', 'invalid_path', 'path_outside_workspace',
    'symlink_denied', 'not_regular_file', 'expired_receipt', 'invalid_receipt',
    'consumed_receipt', 'wrong_attempt', 'metadata_changed', 'unknown_receipt',
    'malformed_receipt', 'patch_write_disabled', 'hardlink_denied', 'target_exists'})


def patch_diagnostics(result, dry_run=None):
    """Only constant codes; never exception prose, paths, patch or capabilities."""
    phase = result.metadata.get('failure_phase')
    if phase not in ('argument_parsing', 'validation', 'preflight', 'preview',
                     'write_preparation', 'publication', 'cleanup', 'journal'):
        phase = 'unknown'
    code = result.error if result.error in SAFE_PATCH_ERRORS else 'unknown'
    uncertain = result.metadata.get('status') in ('partial_failure_possible', 'rollback_conflict')
    if uncertain: code = 'execution_uncertain'
    intent = 'preview' if dry_run is True else 'write' if dry_run is False else 'unknown'
    if phase == 'argument_parsing': intent = 'unknown'
    return dict(error_category=code if not result.success else None,
        safe_error_code=code if not result.success else None, failure_phase=phase,
        operation_intent=intent,
        file_metadata_supported=False if code in ('unsupported_ownership', 'unsupported_metadata') else None,
        guidance_code=(None if result.success else 'check_workspace_metadata' if code in ('unsupported_ownership', 'unsupported_metadata')
                       and (intent == 'preview' or phase in ('validation', 'preflight'))
                       else 'inspect_state_no_replay' if intent == 'write' or uncertain
                       else 'review_patch_input' if not result.success else None),
        safe_to_retry=bool(result.metadata.get('safe_to_retry')))
