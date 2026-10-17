"""Internal bounded git/rg runner. Never registered as a model tool."""
import asyncio
import os
from pathlib import Path
import shutil
import signal
from dataclasses import dataclass

TIMEOUT_SECONDS = 5.0


def executable(name, workspace):
    if name not in ('git','rg'):raise ValueError('unsupported_program')
    directories=[]
    for value in ('/usr/bin','/bin','/opt/homebrew/bin','/usr/local/bin',*os.get_exec_path()):
        p=Path(value)
        if not p.is_absolute():continue
        resolved=p.resolve()
        trusted=(str(resolved).startswith(('/usr/bin','/bin','/opt/homebrew/','/usr/local/'))
                 or '.app/Contents/' in str(resolved))
        if trusted and not resolved.is_relative_to(workspace):directories.append(str(resolved))
    candidate=shutil.which(name,path=os.pathsep.join(dict.fromkeys(directories)))
    if not candidate:raise FileNotFoundError('dependency_missing: '+name)
    resolved=Path(candidate).resolve()
    if (resolved.is_relative_to(workspace) or not (str(resolved).startswith(('/usr/bin/','/bin/','/opt/homebrew/','/usr/local/')) or '.app/Contents/' in str(resolved))):raise ValueError('untrusted_executable')
    return str(resolved),os.pathsep.join(dict.fromkeys(directories))


@dataclass(frozen=True)
class ProcessResult:
    code: int
    stdout: bytes
    truncated: bool
    timed_out: bool


async def run_readonly(program, args, *, cwd, workspace, stdout_limit=131072,
                       separator=b'\n', record_limit=None, record_filter=None, timeout=TIMEOUT_SECONDS):
    exe,path=executable(program,workspace)
    env={'PATH':path,'LANG':'C','LC_ALL':'C','GIT_CONFIG_NOSYSTEM':'1',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0',
         'GIT_LITERAL_PATHSPECS':'1','GIT_NO_LAZY_FETCH':'1','GIT_NO_REPLACE_OBJECTS':'1','GIT_ATTR_NOSYSTEM':'1'}
    proc=await asyncio.create_subprocess_exec(exe,*args,cwd=str(cwd),env=env,
        stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,start_new_session=True,limit=8192)
    truncated=False
    killed=False
    def kill():
        nonlocal killed
        if killed:return
        killed=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except PermissionError:
            if proc.returncode is None:
                try:proc.kill()
                except ProcessLookupError:pass
        except ProcessLookupError:pass
    async def drain(stream,limit,records=None):
        nonlocal truncated
        data=bytearray();count=0;pending=bytearray()
        while chunk:=await stream.read(4096):
            room=max(0,limit-len(data));data.extend(chunk[:room])
            if record_filter is None:count+=chunk.count(separator)
            elif len(data)<=limit:
                pending.extend(chunk[:room])
                while separator in pending:
                    line,_,rest=pending.partition(separator);pending=bytearray(rest)
                    try:count+=bool(record_filter(line))
                    except (ValueError,KeyError):pass
            if len(chunk)>room or (records is not None and count>=records):
                truncated=True;kill()
        return bytes(data)
    output=asyncio.create_task(drain(proc.stdout,stdout_limit,record_limit))
    errors=asyncio.create_task(drain(proc.stderr,4096))
    work=asyncio.gather(proc.wait(),output,errors)
    timed_out=False
    try:
        await asyncio.wait_for(asyncio.shield(work),timeout)
    except TimeoutError:
        timed_out=True;kill();await asyncio.shield(work)
    except BaseException:
        kill();await asyncio.shield(asyncio.gather(proc.wait(),output,errors,return_exceptions=True));raise
    return ProcessResult(proc.returncode,output.result(),truncated,timed_out)


GIT_OPTIONS=['--no-pager','--no-optional-locks','-c','core.fsmonitor=false',
             '-c','core.hooksPath=/dev/null','-c','core.pager=cat','-c','core.attributesFile=/dev/null',
             '-c','core.untrackedCache=false','-c','core.preloadIndex=false',
             '-c','core.excludesFile=/dev/null','-c','core.quotePath=false']
