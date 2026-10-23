"""Cooperative CLI/Web process lock, outside user workspace; never delete lock files."""
from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path
import stat


class WorkspaceBusy(RuntimeError):
    pass


class WorkspaceLease:
    # Stable across TMPDIR settings. Kernel flock releases on process exit, not by
    # guessing PID liveness or deleting an unknown lock. Same-UID cooperation only.
    directory = Path('/tmp') / f'mybot-workspace-leases-{os.getuid()}'
    uncertain = []  # Keep descriptors until process exit if cleanup is unconfirmed.

    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.fd = None

    def acquire(self):
        if self.fd is not None: raise WorkspaceBusy('workspace_lease_already_held')
        folder = self.directory
        folder.mkdir(mode=0o700, exist_ok=True)
        parent = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = None
        try:
            info = os.fstat(parent)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise WorkspaceBusy('workspace_lock_directory_unsafe')
            name = hashlib.sha256(os.fsencode(self.workspace)).hexdigest()+'.lock'
            fd = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
                raise WorkspaceBusy('workspace_lock_file_unsafe')
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise WorkspaceBusy('workspace_busy_in_another_process') from None
            self.fd = fd; fd = None
            return self
        finally:
            if fd is not None: os.close(fd)
            os.close(parent)

    def release(self, *, confirmed=True):
        if self.fd is None: return
        if not confirmed:
            if self not in self.uncertain: self.uncertain.append(self)
            return
        fd,self.fd = self.fd,None
        os.close(fd)
