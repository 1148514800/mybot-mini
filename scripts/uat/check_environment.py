"""Read-only OFFLINE fixture readiness. Never calls a model or publishes a patch."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from mybot.tools.patch import ApplyPatchTool, check_metadata
from .fixtures import ALLOWED, PROJECTS, assess, fingerprint


def git(root, *args):
    return subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args],
                          capture_output=True, check=True).stdout.decode().strip()


async def check_environment(case, root):
    requested_root = Path(root).absolute()
    root = requested_root.resolve()
    before = fingerprint(root)
    report = dict(mode='OFFLINE/SYNTHETIC', fixture_version=2, actual_root=str(root),
                  uid=os.getuid(), euid=os.geteuid(), gid=os.getgid(), egid=os.getegid(),
                  files=[], directories=[], issues=[])
    if requested_root.is_symlink(): report['issues'].append('symlink_root')
    parent_info = root.parent.stat()
    report['root_parent'] = dict(uid=parent_info.st_uid, gid=parent_info.st_gid,
        mode=oct(stat.S_IMODE(parent_info.st_mode)))
    paths = list(PROJECTS.get(case, {}))
    for name in paths:
        path = root / name
        entry = dict(path=name)
        try:
            info = path.lstat()
            entry.update(uid=info.st_uid, gid=info.st_gid, mode=oct(stat.S_IMODE(info.st_mode)),
                         regular=stat.S_ISREG(info.st_mode), symlink=path.is_symlink(),
                         version=[info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns])
            if not stat.S_ISREG(info.st_mode): raise ValueError('not_regular_file')
            # Walk parents without following symlinks, including fixture root.
            parent = path.parent
            while True:
                pi = parent.lstat()
                if stat.S_ISLNK(pi.st_mode): raise ValueError('symlink_parent')
                if not stat.S_ISDIR(pi.st_mode): raise ValueError('not_directory')
                report['directories'].append(dict(path=str(parent.relative_to(root)) or '.',
                    uid=pi.st_uid, gid=pi.st_gid, mode=oct(stat.S_IMODE(pi.st_mode))))
                if parent == root: break
                parent = parent.parent
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                entry['xattr_present'] = bool(subprocess.run(['xattr', str(path)], capture_output=True, check=True).stdout) if sys.platform == 'darwin' else bool(os.listxattr(path, follow_symlinks=False))
                check_metadata(fd, os.fstat(fd))  # Actual ACL/xattr/UID/GID policy.
                entry['metadata_supported'] = True
                entry['acl_supported'] = True
            finally: os.close(fd)
            entry['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            entry['metadata_supported'] = False
            report['issues'].append(str(exc) if isinstance(exc, ValueError) else 'metadata_io_error')
        report['files'].append(entry)
    try:
        report['git_head'] = git(root, 'rev-parse', 'HEAD')
        report['git_index_sha256'] = hashlib.sha256(git(root, 'ls-files', '--stage').encode()).hexdigest()
        report['git_status'] = git(root, 'status', '--porcelain')
        if report['git_status']: report['issues'].append('dirty_fixture')
    except subprocess.SubprocessError: report['issues'].append('git_unavailable')
    # Native dry_run exercises path opening, metadata, hash, anchors and recheck.
    previews = []
    tool = ApplyPatchTool(root, patch_mode='preview')
    for name in ALLOWED.get(case, []):
        path = root/name
        if not path.is_file() or path.is_symlink(): continue
        text = path.read_text()
        result = await tool.execute(dry_run=True, changes=[dict(op='update', path=name,
            expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            edits=[dict(old_text=text, new_text=text+'\n# OFFLINE preflight preview only\n')])])
        previews.append(dict(path=name, passed=result.success, code=result.metadata.get('safe_error_code')))
        if not result.success: report['issues'].append(result.metadata.get('safe_error_code') or 'preview_failed')
    report['native_previews'] = previews
    try:
        public = await assess(case, root, hidden=False) if case in PROJECTS else None
        hidden = await assess(case, root) if case in ('U04', 'U05') else None
        report.update(public_tests=public, independent_tests=hidden,
                      seatbelt_available=bool(public and public['sandbox_applied']))
        if public and (not public['sandbox_applied'] or public['status'] != 'completed'):
            report['issues'].append('sandbox_or_unittest_unavailable')
        if case in ('U04', 'U05'):
            # Exit 1 alone is insufficient: check expected unittest failures and
            # initial source fingerprint so import errors cannot masquerade as bugs.
            expected = all((root/k).read_text() == v for k,v in PROJECTS[case].items())
            report['expected_initial_bug'] = bool(expected and public['returncode'] == 1
                and 'FAIL:' in public['stderr'] and not hidden['passed'])
            if not report['expected_initial_bug']: report['issues'].append('initial_bug_not_confirmed')
    except Exception:
        report['issues'].append('sandbox_or_unittest_unavailable')
    report['unchanged'] = before == fingerprint(root)
    if not report['unchanged']: report['issues'].append('fixture_changed_during_preflight')
    report['status'] = 'PASS' if not report['issues'] else 'BLOCKED'
    return report


async def require_environment(case, root):
    report = await check_environment(case, root)
    if report['status'] != 'PASS': raise RuntimeError('fixture_environment_blocked')
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('case', choices=['U03','U04','U05']);parser.add_argument('root')
    args=parser.parse_args();report=asyncio.run(check_environment(args.case,args.root))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['status']=='PASS' else 1)
if __name__=='__main__':main()
