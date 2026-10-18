"""Deprecated Seatbelt interface, deny-first profile plus mandatory real isolation probe.

SBPL is not a supported third-party API. Never silently fall back to host execution.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from .command_process import Launch, run_process

SYSTEM_ROOTS = ('/System/Library', '/System/Cryptexes/OS/usr/lib', '/usr/lib',
                '/usr/share/locale', '/Library/Apple/System/Library', '/bin', '/usr/bin')


def available():
    return sys.platform == 'darwin' and Path('/usr/bin/sandbox-exec').is_file()


def profile(workspace, temp, runtime_roots):
    if not available(): raise ValueError('sandbox_unavailable')
    workspace = Path(workspace).resolve(); temp = Path(temp).resolve(); home = Path.home().resolve()
    if home.is_relative_to(workspace) or workspace in (Path('/'), home):
        raise ValueError('unsafe_workspace_root')
    if temp.is_relative_to(workspace) or workspace.is_relative_to(temp):
        raise ValueError('sandbox_path_overlap')
    # User-private HOME locations cannot themselves be selected as command workspaces.
    for name in ('.ssh', '.aws', '.azure', '.gnupg', '.kube', 'Library/Keychains'):
        if workspace.is_relative_to(home / name): raise ValueError('unsafe_workspace_root')
    roots = {Path(p).resolve() for p in (*SYSTEM_ROOTS, *runtime_roots)} | {workspace, temp}
    if any(home.is_relative_to(p) or p == Path('/') for p in roots): raise ValueError('untrusted_runtime')
    ancestors = {p for root in roots for p in root.parents}
    quote = lambda p: json.dumps(str(p), ensure_ascii=False)
    read = ' '.join('(subpath ' + quote(p) + ')' for p in sorted(roots))
    traversal = ' '.join('(literal ' + quote(p) + ')' for p in sorted(ancestors))
    private_paths = [workspace / name for name in ('.env', '.git', '.ssh', '.aws', '.azure', '.gnupg', '.kube', 'credentials', 'credentials.json', 'config/config.json')]
    private_paths += [home / name for name in ('.ssh', '.aws', '.azure', '.gnupg', '.kube', 'Library/Keychains')]
    private_reads = ' '.join('(subpath ' + quote(p) + ')' for p in private_paths)
    # Ancestor directory access is literal, never recursive HOME access. Metadata
    # visibility is broader than file-content access and is an explicit limitation.
    return ('(version 1)\n(deny default)\n'
        '(allow process-exec process-fork)\n'
        '(allow sysctl-read (sysctl-name "hw.memsize") (sysctl-name "vm.pagesize") (sysctl-name "hw.pagesize_compat") (sysctl-name "hw.pagesize") (sysctl-name "hw.pagesize32") (sysctl-name "hw.pagesize64") (sysctl-name "hw.ncpu") '
        '(sysctl-name "hw.activecpu") (sysctl-name "hw.logicalcpu") (sysctl-name "hw.physicalcpu") '
        '(sysctl-name "hw.logicalcpu_max") (sysctl-name "hw.physicalcpu_max") '
        '(sysctl-name "hw.machine") (sysctl-name "hw.model") (sysctl-name "kern.ostype") '
        '(sysctl-name "kern.osrelease") (sysctl-name "kern.osversion") (sysctl-name "kern.hostname") (sysctl-name "kern.version") (sysctl-name "kern.usrstack64") (sysctl-name "kern.usrstack"))\n'
        '(allow file-read-metadata)\n(allow file-read* ' + read + ' ' + traversal + ')\n'
        '(allow file-read* (literal "/dev/null") (literal "/dev/random") (literal "/dev/urandom"))\n'
        '(allow file-write* (subpath ' + quote(temp) + '))\n'
        '(allow file-write-data (literal "/dev/null"))\n'
        '(deny file-write* (subpath ' + quote(workspace) + '))\n'
        '(deny file-link)\n(deny process-info*)\n(deny file-read* ' + private_reads + ')\n')


PROBE = '''import errno,io,json,os,pathlib,socket,subprocess,sys,unittest
cfg=json.loads(sys.argv[1]);w=pathlib.Path(cfg['workspace']);t=pathlib.Path(cfg['temp']);p=pathlib.Path(cfg['private'])
results={}
results['read_source']=(w/'source.py').read_text()=='source sentinel'
class ReadOnly(unittest.TestCase):
 def runTest(self):self.assertEqual((w/'source.py').read_text(),'source sentinel')
results['unittest']=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([ReadOnly()])).wasSuccessful()
(t/'data').write_text('temporary sentinel');results['temporary_write']=(t/'data').read_text()=='temporary sentinel'
def denied(action):
 try:action()
 except OSError as e:return e.errno in (errno.EPERM,errno.EACCES)
 return False
results['workspace_write']=denied(lambda:(w/'source.py').write_text('BAD'))
results['index_write']=denied(lambda:(w/'.git/index').write_text('BAD'))
results['external_write']=denied(lambda:p.write_text('BAD'))
results['private_read']=denied(lambda:p.read_text())
results['workspace_private_read']=denied(lambda:(w/'.env').read_text()) and denied(lambda:(w/'config/config.json').read_text())
results['workspace_symlink']=denied(lambda:(w/'alias').write_text('BAD'))
results['temp_symlink']=denied(lambda:(t/'alias').write_text('BAD'))
results['hardlink']=denied(lambda:os.link(w/'source.py',t/'hardlink'))
s=socket.socket();s.settimeout(1)
results['network']=denied(lambda:s.connect(('127.0.0.1',cfg['port'])));s.close()
child='import pathlib,sys;'+"\\ntry:pathlib.Path(sys.argv[1]).write_text('BAD')\\nexcept PermissionError:sys.exit(17)"
r=subprocess.run([sys.executable,'-I','-S','-c',child,str(p)],capture_output=True,timeout=2)
results['child_inherits']=r.returncode==17
print(json.dumps(results,sort_keys=True))
'''
CHECKS = frozenset({'read_source', 'unittest', 'temporary_write', 'workspace_write', 'index_write',
                    'external_write', 'private_read', 'workspace_private_read', 'workspace_symlink', 'temp_symlink', 'hardlink', 'network', 'child_inherits'})


async def verify_sandbox(runtime_roots):
    """Only synthetic sentinels are ever probed, even if sandbox-exec is broken."""
    if not available(): return False
    async def accept(reader, writer):
        writer.close(); await writer.wait_closed()
    server = await asyncio.start_server(accept, '127.0.0.1', 0)
    try:
        port = server.sockets[0].getsockname()[1]
        # Establish a real reachable control, not a connection-refused false positive.
        _, writer = await asyncio.open_connection('127.0.0.1', port)
        writer.close(); await writer.wait_closed()
        with tempfile.TemporaryDirectory(prefix='mybot-seatbelt-probe-', dir='/private/tmp') as folder:
            root = Path(folder).resolve(); workspace = root / 'workspace'; temp = root / 'run'
            workspace.mkdir(); temp.mkdir(); (workspace / '.git').mkdir()
            private = root / 'private-data'; private.write_text('private sentinel')
            (workspace / 'source.py').write_text('source sentinel')
            (workspace / '.env').write_text('synthetic private data')
            (workspace / 'config').mkdir(); (workspace / 'config/config.json').write_text('synthetic private data')
            (workspace / '.git/index').write_bytes(b'index sentinel')
            (workspace / 'alias').symlink_to(private); (temp / 'alias').symlink_to(workspace / 'source.py')
            cfg = json.dumps(dict(workspace=str(workspace), temp=str(temp), private=str(private), port=port))
            python = str(Path(getattr(sys, '_base_executable', sys.executable)).resolve())
            launch = Launch((python, '-I', '-S', '-c', PROBE, cfg), tuple(runtime_roots), ())
            fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                result = await run_process(launch, cwd=workspace, cwd_fd=fd, temp=temp,
                    timeout=5, output_limit=8192, profile=profile(workspace, temp, runtime_roots))
            finally: os.close(fd)
            if result.status != 'completed' or result.exit_code != 0 or not result.sandbox_applied: return False
            checks = json.loads(result.stdout)
            return (set(checks) == CHECKS and all(v is True for v in checks.values())
                and (workspace / 'source.py').read_text() == 'source sentinel'
                and (workspace / '.git/index').read_bytes() == b'index sentinel'
                and private.read_text() == 'private sentinel'
                and (temp / 'data').read_text() == 'temporary sentinel')
    except (OSError, ValueError, TypeError): return False
    finally:
        server.close(); await server.wait_closed()
