"""Independent bounded command lifecycle. Not the Phase19 Git/rg read-only runner."""
import asyncio
import json
import math
import os
from pathlib import Path
import signal
import stat
import sys
import time
from dataclasses import dataclass

FILE_LIMIT = 8 * 1024 * 1024
TEMP_LIMIT = 32 * 1024 * 1024
TEMP_ENTRIES = 512
CLEANUP_SECONDS = 1.5


def fingerprint(path):
    s = Path(path).stat()
    if not stat.S_ISREG(s.st_mode) or not s.st_mode & 0o111 or s.st_mode & 0o022:
        raise ValueError('untrusted_executable')
    if s.st_uid not in (0, os.geteuid()): raise ValueError('untrusted_executable')
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


@dataclass(frozen=True)
class Launch:
    argv: tuple
    roots: tuple
    versions: tuple


def trusted_python(workspace):
    base = Path(getattr(sys, '_base_executable', sys.executable)).resolve(strict=True)
    if base.is_relative_to(workspace): raise ValueError('untrusted_executable')
    fingerprint(base)
    runtime = Path(sys.base_prefix).resolve()
    if not base.is_relative_to(runtime) or runtime in (Path('/'), Path.home().resolve()):
        raise ValueError('untrusted_runtime')
    candidate = workspace / '.venv/bin/python'
    versions = [(str(base), fingerprint(base))]
    if candidate.exists() or candidate.is_symlink():
        for part in (workspace / '.venv', workspace / '.venv/bin'):
            if part.is_symlink() or not part.is_dir(): raise ValueError('untrusted_virtualenv')
        cfg = workspace / '.venv/pyvenv.cfg'
        if cfg.is_symlink() or not cfg.is_file() or cfg.stat().st_size > 4096:
            raise ValueError('untrusted_virtualenv')
        if not candidate.is_symlink() or candidate.resolve(strict=True) != base:
            raise ValueError('untrusted_virtualenv')
        values = {k.strip(): v.strip() for k, v in (line.split('=', 1) for line in cfg.read_text().splitlines() if '=' in line)}
        if values.get('include-system-site-packages', '').lower() != 'false': raise ValueError('untrusted_virtualenv')
        home = values.get('home', '')
        if Path(home).resolve() != base.parent: raise ValueError('untrusted_virtualenv')
        import hashlib
        versions.append((str(cfg), hashlib.sha256(cfg.read_bytes()).hexdigest()))
        selected = candidate
        roots = (str(runtime), str(workspace / '.venv'))
    else:
        selected = Path(sys.executable).absolute()
        if selected.resolve(strict=True) != base: raise ValueError('untrusted_virtualenv')
        roots = (str(runtime), str(Path(sys.prefix).resolve()))
    return selected, roots, tuple(versions)


def trusted_uv(workspace):
    # No repository/PATH search. Known host installation roots only, then validate target.
    roots = [Path('/opt/homebrew'), Path('/usr/local'), Path.home() / '.local/bin']
    for p in [Path('/opt/homebrew/bin/uv'), Path('/usr/local/bin/uv'), Path.home() / '.local/bin/uv']:
        if not p.exists(): continue
        target = p.resolve(strict=True)
        if target.is_relative_to(workspace) or not any(target.is_relative_to(r) for r in roots):
            raise ValueError('untrusted_executable')
        fingerprint(target)
        return target
    raise FileNotFoundError('executable_missing')


def resolve_launch(argv, workspace):
    python, roots, versions = trusted_python(workspace)
    name = argv[0]
    if name in ('python', 'python3'):
        effective = (str(python), *argv[1:])
    elif name in ('pytest', 'ruff'):
        effective = (str(python), '-m', name, *argv[1:])
    elif name == 'uv':
        if tuple(argv[:4]) != ('uv', 'run', '--no-sync', 'python'):
            raise ValueError('unsupported_command')
        uv = trusted_uv(workspace)
        effective = (str(uv), 'run', '--no-config', '--offline', '--no-sync', '--python', str(python), 'python', *argv[4:])
        roots = (*roots, str(uv))
        versions = (*versions, (str(uv), fingerprint(uv)))
    else: raise ValueError('unsupported_command')
    return Launch(tuple(effective), tuple(sorted(set(roots))), versions)


def environment(temp, launch):
    return {'PATH': '/usr/bin:/bin', 'LANG': 'en_US.UTF-8', 'LC_ALL': 'en_US.UTF-8',
            'HOME': str(temp), 'TMPDIR': str(temp), 'TMP': str(temp), 'TEMP': str(temp),
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
            'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'XDG_CACHE_HOME': str(temp / 'cache'),
            'UV_CACHE_DIR': str(temp / 'uv-cache'), 'UV_OFFLINE': '1',
            'UV_PYTHON_DOWNLOADS': 'never', 'UV_NO_PROGRESS': '1',
            'UV_PROJECT_ENVIRONMENT': str(Path(launch.argv[launch.argv.index('--python') + 1] if '--python' in launch.argv else launch.argv[0]).parent.parent)}


# Trusted -I/-S bootstrap avoids importing project code before limits and closes
# both internal descriptors before exec. The target cannot forge the exec handshake.
BOOTSTRAP = '''import os,sys,json,resource
fd=int(sys.argv[1]); cwd_fd=int(sys.argv[2]); timeout=int(sys.argv[3]); argv=json.loads(sys.argv[4])
try:
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 resource.setrlimit(resource.RLIMIT_FSIZE,(8388608,8388608))
 resource.setrlimit(resource.RLIMIT_NOFILE,(128,128))
 resource.setrlimit(resource.RLIMIT_CPU,(timeout+1,timeout+1))
 os.fchdir(cwd_fd);os.close(cwd_fd);os.set_inheritable(fd,False)
 os.write(fd,b'ready')
 os.execv(argv[0],argv)
except BaseException:
 os.write(fd,b'failed');os._exit(126)
'''


def temp_within_budget(root):
    count = 0; size = 0
    def scan(fd, depth):
        nonlocal count, size
        if depth > 16: return False
        with os.scandir(fd) as entries:
            for entry in entries:
                count += 1
                if count > TEMP_ENTRIES: return False
                info = entry.stat(follow_symlinks=False); size += info.st_size
                if size > TEMP_LIMIT: return False
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        if not scan(child, depth + 1): return False
                    finally: os.close(child)
        return True
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: return scan(fd, 0)
    finally: os.close(fd)


@dataclass
class CommandProcessResult:
    status: str
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    stdout_bytes: int
    stderr_bytes: int
    duration_ms: int
    spawned: bool
    process_terminated: bool
    sandbox_applied: bool


async def run_process(launch, *, cwd, cwd_fd, temp, timeout, output_limit, profile=None):
    started = time.monotonic(); proc = None; killed = False; cleanup_uncertain = False; cleanup_task = None; work = None
    read_fd, write_fd = os.pipe(); os.set_blocking(read_fd, False)
    aborted = asyncio.Event()
    python = str(Path(getattr(sys, '_base_executable', sys.executable)).resolve())
    argv = [python, '-I', '-S', '-c', BOOTSTRAP, str(write_fd), str(cwd_fd), str(math.ceil(timeout)), json.dumps(launch.argv)]
    if profile is not None: argv = ['/usr/bin/sandbox-exec', '-p', profile, *argv]
    def kill():
        nonlocal killed, cleanup_uncertain
        if proc is None: return
        try: os.killpg(proc.pid, signal.SIGKILL); killed = True
        except ProcessLookupError: pass
        except PermissionError:
            if proc.returncode is None:
                try: proc.kill(); killed = True
                except ProcessLookupError: pass
                except OSError: cleanup_uncertain = True
        except OSError: cleanup_uncertain = True
    tasks = []; status = 'completed'; output = [bytearray(), bytearray()]; seen = [0, 0]
    async def drain(stream, index):
        nonlocal status
        while chunk := await stream.read(4096):
            seen[index] += len(chunk)
            room = max(0, output_limit - sum(map(len, output)))
            output[index].extend(chunk[:room])
            if len(chunk) > room:
                status = 'output_limit_exceeded'; kill(); aborted.set(); return
    async def monitor():
        nonlocal status
        while True:
            await asyncio.sleep(.05)
            try: valid = temp_within_budget(temp)
            except OSError: valid = False
            if not valid: status = 'temporary_limit_exceeded'; kill(); aborted.set(); return
    async def cleanup():
        nonlocal cleanup_uncertain
        kill()
        if proc is not None:
            try: await asyncio.wait_for(proc.wait(), CLEANUP_SECONDS)
            except TimeoutError:
                if proc.returncode is None: cleanup_uncertain = True
            # asyncio has no public pipe-close API. Close our own transports to
            # bound cleanup when a detached descendant still holds a pipe open.
            for n in (0, 1, 2):
                transport = proc._transport.get_pipe_transport(n)
                if transport is not None: transport.close()
            try: proc._transport.close()
            except OSError: cleanup_uncertain = True
        for task in tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    async def protected_cleanup():
        nonlocal cleanup_task
        if cleanup_task is None: cleanup_task = asyncio.create_task(cleanup())
        interrupted = False
        while not cleanup_task.done():
            try: await asyncio.shield(cleanup_task)
            except asyncio.CancelledError: interrupted = True
        await cleanup_task
        if interrupted: raise asyncio.CancelledError
    try:
        spawning = asyncio.create_task(asyncio.create_subprocess_exec(*argv, cwd=str(cwd),
            env=environment(temp, launch), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True, pass_fds=(write_fd, cwd_fd), limit=8192))
        try: proc = await asyncio.shield(spawning)
        except BaseException:
            try: proc = await spawning
            except Exception: pass
            raise
        finally: os.close(write_fd); write_fd = None
        tasks = [asyncio.create_task(drain(proc.stdout, 0)), asyncio.create_task(drain(proc.stderr, 1)), asyncio.create_task(monitor())]
        work = asyncio.gather(proc.wait(), *tasks[:2])
        stop = asyncio.create_task(aborted.wait()); tasks.append(stop)
        try:
            done, _ = await asyncio.wait((work, stop), timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done: status = 'timed_out'
        finally:
            await protected_cleanup()
            if not work.done(): work.cancel()
            await asyncio.gather(work, return_exceptions=True)
        handshake = os.read(read_fd, 64)
        spawned = handshake == b'ready'
        sandbox = profile is not None and handshake.startswith(b'ready')
        if status == 'completed':
            if not spawned: status = 'sandbox_unavailable' if profile is not None else 'spawn_failed'
            elif proc.returncode is None: status = 'process_state_unknown'
            elif proc.returncode < 0: status = 'process_signaled'
        if cleanup_uncertain: status = 'process_state_unknown'
        return CommandProcessResult(status, proc.returncode, bytes(output[0]), bytes(output[1]),
            *seen, round((time.monotonic() - started) * 1000), spawned, killed, sandbox)
    except BaseException:
        await protected_cleanup()
        if work is not None:
            if not work.done(): work.cancel()
            await asyncio.gather(work, return_exceptions=True)
        raise
    finally:
        os.close(read_fd)
        if write_fd is not None: os.close(write_fd)
