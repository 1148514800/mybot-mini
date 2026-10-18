"""Read-only checkout baseline and narrowly scoped private Git metadata fingerprints."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from ..tools.git_tools import GitStatusTool
from ..tools.patch import identity, version


@dataclass(frozen=True)
class GitWorkflowSettings:
    enabled: bool = False
    undo_enabled: bool = False
    max_files: int = 24
    max_journal_bytes: int = 8388608
    max_review_chars: int = 20000


def validate_git_workflow(value, *, coding_enabled, patch_mode, autonomy_enabled, command_mode, mcp_enabled):
    if not isinstance(value, dict) or set(value) - set(GitWorkflowSettings.__dataclass_fields__):
        raise ValueError('invalid coding.git_workflow fields')
    result = GitWorkflowSettings(**value)
    for key in ('enabled', 'undo_enabled'):
        if type(getattr(result, key)) is not bool: raise ValueError('invalid coding.git_workflow.' + key)
    for key, low, high in [('max_files', 1, 24), ('max_journal_bytes', 1, 16777216), ('max_review_chars', 256, 64000)]:
        n = getattr(result, key)
        if type(n) is not int or not low <= n <= high: raise ValueError('invalid coding.git_workflow.' + key)
    if result.undo_enabled and not result.enabled: raise ValueError('undo requires git_workflow.enabled')
    if result.enabled and not (coding_enabled is True and patch_mode == 'write' and autonomy_enabled is True):
        raise ValueError('git_workflow requires coding enabled, patch write and autonomy enabled')
    if result.undo_enabled and (command_mode != 'macos_readonly' or mcp_enabled is not False):
        raise ValueError('undo requires macos_readonly and mcp.enabled=false')
    return result


def read_scoped(directory, relative, *, limit=16777216, missing=False):
    """Fixed internal metadata paths only; never a model API. No symlink components."""
    parts = Path(relative).parts
    if not parts or any(p in ('.', '..') for p in parts) or Path(relative).is_absolute():
        raise ValueError('metadata_unavailable')
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ValueError('metadata_unavailable')
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk: break
            data.extend(chunk)
        if len(data) > limit or version(info) != version(os.fstat(fd)):
            raise ValueError('metadata_unavailable')
        return bytes(data), (version(info), hashlib.sha256(data).hexdigest())
    except FileNotFoundError:
        if missing: return None, ('absent',)
        raise
    finally:
        if fd is not None: os.close(fd)
        os.close(parent)


def validate_full_index(data):
    """Conservative SHA-1 v2/v3 full-index scope; reject shared/sparse formats."""
    fail = ValueError('unsupported_index_format')
    if len(data) < 32 or data[:4] != b'DIRC' or hashlib.sha1(data[:-20]).digest() != data[-20:]:
        raise fail
    index_version = int.from_bytes(data[4:8], 'big')
    count = int.from_bytes(data[8:12], 'big')
    if index_version not in (2, 3) or count > 100000: raise fail
    end = len(data) - 20
    offset = 12
    for _ in range(count):
        start = offset
        if offset + 62 > end: raise fail
        mode = int.from_bytes(data[offset + 24:offset + 28], 'big')
        flags = int.from_bytes(data[offset + 60:offset + 62], 'big')
        # Extended flags include sparse/skip-worktree and intent-to-add. Fail closed.
        if flags & 0x4000 or mode & 0o170000 in (0o040000, 0o160000): raise fail
        offset += 62
        nul = data.find(b'\0', offset, end)
        if nul < 0: raise fail
        length = nul - offset
        if not length or (flags & 0xfff) != min(length, 0xfff): raise fail
        offset = start + ((nul + 1 - start + 7) // 8) * 8
        if offset > end or any(data[nul:offset]): raise fail
    while offset < end:
        if offset + 8 > end: raise fail
        signature = data[offset:offset + 4]
        length = int.from_bytes(data[offset + 4:offset + 8], 'big')
        # Git specifies non-uppercase extensions as mandatory (e.g. link/sdir).
        if not 65 <= signature[0] <= 90: raise fail
        offset += 8 + length
        if offset > end: raise fail


@dataclass(repr=False)
class GitMetadataScope:
    root: Path
    admin: Path
    common: Path
    marker: object
    admin_identity: object
    common_identity: object
    worktree_links: object = None

    @classmethod
    async def create(cls, tool, root):
        async def query(args):
            r = await tool.git(args, root, stdout_limit=8192)
            if r.code or r.truncated or r.timed_out: raise ValueError('metadata_unavailable')
            return r.stdout.decode('utf-8').rstrip('\n')
        admin = Path(await query(['rev-parse', '--absolute-git-dir'])).resolve()
        common_raw = Path(await query(['rev-parse', '--git-common-dir']))
        common = (common_raw if common_raw.is_absolute() else root / common_raw).resolve()
        marker_path = root / '.git'
        if marker_path.is_symlink(): raise ValueError('metadata_unavailable')
        if marker_path.is_dir():
            if admin != marker_path or common != admin: raise ValueError('metadata_unavailable')
            marker = ('directory', identity(marker_path.stat()))
        else:
            data, marker = read_scoped(root, '.git', limit=4096)
            if not data.startswith(b'gitdir: ') or len(data.splitlines()) != 1: raise ValueError('metadata_unavailable')
            target = Path(os.fsdecode(data[8:].strip()))
            if (target if target.is_absolute() else root / target).resolve() != admin:
                raise ValueError('metadata_unavailable')
            if admin.parent.name != 'worktrees' or admin.parent.parent != common:
                raise ValueError('metadata_unavailable')
            back, _ = read_scoped(admin, 'gitdir', limit=4096)
            if Path(os.fsdecode(back.strip())).resolve() != marker_path: raise ValueError('metadata_unavailable')
            com, _ = read_scoped(admin, 'commondir', limit=4096)
            if (admin / os.fsdecode(com.strip())).resolve() != common: raise ValueError('metadata_unavailable')
        result = cls(root, admin, common, marker, identity(admin.stat()), identity(common.stat()))
        if marker[0] != 'directory':
            result.worktree_links = tuple(read_scoped(admin, name, limit=4096)[1] for name in ('gitdir', 'commondir'))
        result.fingerprint()
        return result

    def fingerprint(self):
        if self.admin.is_symlink() or self.common.is_symlink(): raise ValueError('metadata_unavailable')
        if identity(self.admin.stat()) != self.admin_identity or identity(self.common.stat()) != self.common_identity:
            raise ValueError('metadata_unavailable')
        marker_path = self.root / '.git'
        if marker_path.is_symlink(): raise ValueError('metadata_unavailable')
        if self.marker[0] == 'directory':
            if not marker_path.is_dir() or identity(marker_path.stat()) != self.marker[1]:
                raise ValueError('metadata_unavailable')
        elif read_scoped(self.root, '.git', limit=4096)[1] != self.marker:
            raise ValueError('metadata_unavailable')
        if self.worktree_links is not None and tuple(read_scoped(self.admin, name, limit=4096)[1]
                for name in ('gitdir', 'commondir')) != self.worktree_links:
            raise ValueError('metadata_unavailable')
        head, head_fp = read_scoped(self.admin, 'HEAD', limit=4096)
        if head.startswith(b'ref: '):
            ref = head[5:].strip().decode('ascii')
            if not re.fullmatch(r'refs/heads/[A-Za-z0-9_./-]+', ref) or any(p in ('.', '..') for p in Path(ref).parts):
                raise ValueError('metadata_unavailable')
            ref_fp = read_scoped(self.common, ref, limit=4096, missing=True)[1]
        elif re.fullmatch(rb'[a-fA-F0-9]{40}(?:[a-fA-F0-9]{24})?\n?', head): ref_fp = None
        else: raise ValueError('metadata_unavailable')
        index_data, index = read_scoped(self.admin, 'index')
        validate_full_index(index_data)
        packed = read_scoped(self.common, 'packed-refs', missing=True)[1]
        return index, head_fp, ref_fp, packed


@dataclass(repr=False)
class GitBaseline:
    tool: object
    root: Path
    head: str | None = None
    files: list = field(default_factory=list)
    complete: bool = False
    truncated: bool = False
    reason: str = ''
    scope: GitMetadataScope | None = None
    fingerprint: object = None

    @classmethod
    async def capture(cls, workspace):
        tool = GitStatusTool(workspace)
        root = await tool.git_root('.')
        if root != Path(workspace).resolve(): raise ValueError('checkout_root_required')
        result = cls(tool, root)
        first = None
        try:
            result.scope = await GitMetadataScope.create(tool, root)
            first = result.scope.fingerprint()
        except (OSError, ValueError, UnicodeError):
            result.scope = None
        try:
            status = await tool.execute()
            if status.success:
                body = json.loads(status.output)
                result.files, result.truncated = body['files'], body['truncated']
            else: raise ValueError(status.error if status.error and status.error.isidentifier() else 'baseline_unavailable')
            head = await tool.git(['rev-parse', '--verify', 'HEAD'], root, stdout_limit=256)
            if head.code or head.truncated or head.timed_out: raise ValueError('head_unavailable')
            result.head = head.stdout.decode().strip()
            if not re.fullmatch(r'[a-fA-F0-9]{40}(?:[a-fA-F0-9]{24})?', result.head): raise ValueError('head_unavailable')
            result.fingerprint = result.scope.fingerprint() if result.scope is not None else None
            result.complete = (first is not None and first == result.fingerprint and not result.truncated and not any(
                f['status'] == 'unmerged' or 'U' in f['index_status'] + f['worktree_status']
                or f['index_status'] + f['worktree_status'] in ('AA', 'DD') for f in result.files))
            if not result.complete: result.reason = 'baseline_incomplete'
        except (OSError, ValueError, UnicodeError):
            result.reason = 'baseline_incomplete'
        return result

    def unchanged(self):
        try: return self.complete and self.scope is not None and self.scope.fingerprint() == self.fingerprint
        except (OSError, ValueError, UnicodeError): return False

    def summary(self):
        return {'head': self.head, 'complete': self.complete, 'truncated': self.truncated,
            'index_fingerprint': 'available' if self.fingerprint is not None else 'unavailable',
            'staged': [f['path'] for f in self.files if f['staged']],
            'unstaged': [f['path'] for f in self.files if f['unstaged']],
            'untracked': [f['path'] for f in self.files if f['untracked']],
            'conflicts': [f['path'] for f in self.files if 'U' in f['index_status'] + f['worktree_status'] or f['index_status'] + f['worktree_status'] in ('AA','DD')], 'reason': self.reason}
