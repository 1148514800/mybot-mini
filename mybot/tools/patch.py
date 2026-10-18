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
import stat
import sys
from dataclasses import dataclass, field

from .base import ToolResult
from .repository import RepositoryTool, MAX_FILE_BYTES

MAX_PATCH_BYTES = 256 * 1024
MAX_DIFF_CHARS = 24000
_RETRY = frozenset({'stale_file_hash', 'anchor_not_found', 'ambiguous_context'})
_STRING = {'type': 'string', 'maxLength': MAX_PATCH_BYTES}
_PATH = {'type': 'string', 'minLength': 1, 'maxLength': 4096}
_EDIT = {'type': 'object', 'properties': {
    'old_text': {**_STRING, 'minLength': 1}, 'new_text': _STRING},
    'required': ['old_text', 'new_text'], 'additionalProperties': False}
_UPDATE = {'type': 'object', 'properties': {
    'op': {'const': 'update'}, 'path': _PATH,
    'expected_sha256': {'type': 'string', 'pattern': '^[a-fA-F0-9]{64}$', 'minLength': 64, 'maxLength': 64},
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


class ApplyPatchTool(RepositoryTool):
    name = 'apply_patch'
    description = ('Precisely update UTF-8 files using full-file SHA256 and unique non-overlapping old_text, '
                   'or add new files in existing directories. Default dry_run=true previews only. '
                   'Write requires patch_mode=write and explicit dry_run=false. No tests or commands run. '
                   'Reread and rebuild on stale_file_hash/anchor conflicts. Hidden/private paths denied.')
    private_arguments = True
    parameters = {'type': 'object', 'properties': {
        'dry_run': {'type': 'boolean', 'default': True},
        'changes': {'type': 'array', 'minItems': 1, 'maxItems': 8,
                    'items': {'oneOf': [_UPDATE, _ADD]}}},
        'required': ['changes'], 'additionalProperties': False}

    def __init__(self, workspace: Path, *, patch_mode: str):
        super().__init__(workspace)
        if patch_mode not in ('preview', 'write'): raise ValueError('invalid_patch_mode')
        self.patch_mode = patch_mode

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
        items = []; attempted = []; result = None
        dry_run = args.get('dry_run', True)
        try:
            bounded_arguments(args); self.validate(args)
            if sys.platform not in ('darwin', 'linux') or not hasattr(os, 'O_NOFOLLOW'):
                raise ValueError('unsupported_filesystem')
            if not dry_run and self.patch_mode != 'write': raise ValueError('patch_write_disabled')
            self._preflight(args, items)
            changed = [x for x in items if x.op == 'add' or x.before != x.after]
            diff, truncated = self._diff(changed)
            if not dry_run:
                for item in changed: self._stage(item)
                # Revalidate ALL versions before publishing the first file.
                for item in items: self._recheck(item)
                for item in changed:
                    self._recheck(item)
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
        except Exception as exc:
            reason = self.failure(exc).error
            status = self._recover(attempted) if attempted else 'preflight_failed'
            result = ToolResult(False, error=reason, metadata={
                'status': status, 'rollback_status': status, 'applied': False,
                'dry_run': dry_run if type(dry_run) is bool else True,
                'execution_evidence': False,
                'safe_to_retry': not attempted and reason in _RETRY})
        finally:
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
                                       safe_to_retry=False, execution_evidence=False)
        return result
