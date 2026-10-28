"""One Workspace resolver (FileTool), plus conservative policy for new read-only tools."""
import json
import re
import asyncio
import os
import stat
from pathlib import Path
from jsonschema import Draft202012Validator
from .file import FileTool
from .base import ToolResult
from .readonly_process import run_readonly,GIT_OPTIONS,TIMEOUT_SECONDS

MAX_FILE_BYTES=2*1024*1024
BLOCKED_DIRS=frozenset({'node_modules','venv','__pycache__','dist','build','cache','caches',
                        'sessions','secrets','runs'})
BLOCKED_SUFFIXES=frozenset({'.pem','.key','.p12','.pfx','.db','.sqlite','.pt','.pth','.bin',
                            '.onnx','.safetensors','.zip','.gz','.pyc'})


def blocked(relative):
    p=Path(relative);parts=p.parts
    return (any(v.startswith('.') or v.casefold() in BLOCKED_DIRS for v in parts)
            or p.suffix.casefold() in BLOCKED_SUFFIXES
            or p.name.casefold() in {'credentials','credentials.json','id_rsa','id_ed25519'}
            or tuple(v.casefold() for v in parts[-2:])==('config','config.json'))


class RepositoryTool(FileTool):
    # Agent debug may retain names/counts, never queries, paths or bodies from these tools.
    private_arguments=True

    async def execute(self,**args):
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS):return await self._execute(**args)
        except TimeoutError:
            return ToolResult(False,error='repository_timeout',metadata={'timed_out':True,'truncated':True})

    def validate(self,args):
        if not Draft202012Validator(self.parameters).is_valid(args):raise ValueError('invalid_arguments')

    def resolve(self,path, *, root=None):
        if not isinstance(path,str) or not path or len(path)>4096 or '\x00' in path:raise ValueError('invalid_path')
        base=root or self.workspace
        raw=Path(path).expanduser();raw=raw if raw.is_absolute() else base/raw
        # Check both lexical spelling and resolved destination (internal aliases cannot bypass policy).
        if not raw.is_relative_to(self.workspace):raise ValueError('path_outside_workspace')
        target=self._resolve(str(raw))
        if blocked(raw.relative_to(self.workspace)):raise ValueError('sensitive_path_denied')
        if blocked(target.relative_to(self.workspace)):raise ValueError('sensitive_path_denied')
        if root is not None and not target.is_relative_to(root):raise ValueError('path_outside_repository')
        return target

    def read_bytes(self,target,*,max_bytes=MAX_FILE_BYTES):
        if type(max_bytes) is not int or not 0<max_bytes<=MAX_FILE_BYTES:raise ValueError('invalid_read_limit')
        if not stat.S_ISREG(target.stat().st_mode):raise ValueError('not_regular_file')
        if target.stat().st_size>max_bytes:raise ValueError('file_too_large')
        fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('not_regular_file')
            data=f.read(max_bytes+1)
        if len(data)>max_bytes:raise ValueError('file_too_large')
        if b'\0' in data:raise ValueError('binary_file')
        try:data.decode('utf-8')
        except UnicodeDecodeError:raise ValueError('invalid_utf8') from None
        return data

    def read_text(self,target):
        return self.read_bytes(target).decode('utf-8')

    async def git_root(self,path):
        target=self.resolve(path)
        if not target.is_dir():raise ValueError('not_directory')
        # Do not discover/use a Git checkout above Workspace.
        probe=target
        while not (probe/'.git').exists():
            if probe==self.workspace:raise ValueError('not_git_repository')
            probe=probe.parent
        result=await self.git(['rev-parse','--show-toplevel'],target,stdout_limit=8192)
        if result.timed_out:raise ValueError('process_timeout')
        if result.truncated:raise ValueError('repository_path_too_large')
        if result.code:raise ValueError('not_git_repository')
        root=Path(result.stdout.decode('utf-8').rstrip('\n')).resolve()
        if not root.is_relative_to(self.workspace):raise ValueError('repository_outside_workspace')
        return root

    async def git(self,args,root,**limits):
        overrides=[]
        if args[0] not in ('rev-parse','config'):
            cfg=await run_readonly('git',[*GIT_OPTIONS,'config','--null','--name-only','--get-regexp',r'^filter\.'],
                                   cwd=root,workspace=self.workspace,stdout_limit=16384,separator=b'\0',record_limit=257)
            if cfg.timed_out or cfg.truncated or cfg.code not in (0,1):raise ValueError('unsafe_git_filter_configuration')
            for raw in sorted(set(cfg.stdout.split(b'\0'))-{b''}):
                key=raw.decode('utf-8')
                if key.rsplit('.',1)[-1].casefold() in ('clean','smudge','process','required'):
                    # -c separates at the first '=': ambiguous subsection names must FAIL CLOSED.
                    if not re.fullmatch(r'filter\.[A-Za-z0-9_.-]+\.(?:clean|smudge|process|required)',key,re.IGNORECASE|re.ASCII):
                        raise ValueError('unsafe_git_filter_configuration')
                    overrides+=['-c',key+('=false' if key.rsplit('.',1)[-1].casefold()=='required' else '=')]
        return await run_readonly('git',[*GIT_OPTIONS,*overrides,*args],cwd=root,workspace=self.workspace,**limits)

    @staticmethod
    def failure(exc):
        # Never echo source, query, command stderr or host absolute paths.
        if isinstance(exc,FileNotFoundError):reason='dependency_missing' if 'dependency_missing' in str(exc) else 'not_found'
        elif isinstance(exc,PermissionError):reason='permission_denied'
        elif isinstance(exc,ValueError):reason=str(exc) if str(exc).isidentifier() else 'path_outside_workspace'
        else:reason='repository_tool_failed'
        return ToolResult(False,error=reason)


def json_result(payload,metadata=None):
    return ToolResult(True,json.dumps(payload,ensure_ascii=False),metadata=metadata or {})
