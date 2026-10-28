"""Bounded, Git-tracked structural facts. No project imports, literals or execution."""
import ast
import asyncio
import json
from pathlib import PurePosixPath
import unicodedata

from .base import ToolResult
from .repository import RepositoryTool, blocked

MAX_FILES = 120
MAX_FILE_BYTES = 512 * 1024
MAX_OUTPUT_BYTES = 12 * 1024
MAX_ITEMS = 64
MAX_NODES = 10000


def display(value):
    """Escape controls (including bidi) as literal display text; bound identifiers."""
    return ''.join(c if unicodedata.category(c)[0] != 'C' else '\\u%04x' % ord(c)
                   for c in str(value)[:256])


def eligible(path):
    p = PurePosixPath(path)
    return (not p.is_absolute() and '..' not in p.parts and not blocked(p)
            and not p.name.casefold().startswith(('credentials','id_rsa','id_ed25519'))
            and p.suffix.casefold() not in ('.sqlite3','.sqlite-wal','.sqlite-shm'))


def module_name(path):
    p = PurePosixPath(path)
    if p.suffix != '.py': return None
    parts = list(p.with_suffix('').parts)
    if parts[-1] == '__init__': parts.pop()
    return '.'.join(parts) if parts and all(n.isidentifier() for n in parts) else None


def facts(data, path, index):
    tree = ast.parse(data, filename='<repo_map>')
    symbols = []; imports = []; limited = False
    def symbol(node, kind, prefix=''):
        nonlocal limited
        if len(symbols) >= MAX_ITEMS: limited=True;return
        name=prefix+node.name
        limited |= len(name)>256
        symbols.append(dict(kind=kind,name=display(name),line=node.lineno,name_truncated=len(name)>256))
    for node in tree.body:
        if len(symbols)>=MAX_ITEMS:limited=True;break
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            symbol(node,'async_function' if isinstance(node,ast.AsyncFunctionDef) else 'function')
        elif isinstance(node,ast.ClassDef):
            symbol(node,'class')
            for method in node.body:
                if len(symbols)>=MAX_ITEMS:limited=True;break
                if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    symbol(method,'async_method' if isinstance(method,ast.AsyncFunctionDef) else 'method',node.name+'.')
    current=module_name(path)
    package=current if path.endswith('/__init__.py') else (current.rpartition('.')[0] if current else '')
    top={id(n) for n in tree.body}
    for count,node in enumerate(ast.walk(tree)):
        if count >= MAX_NODES: limited=True;break
        if not isinstance(node,(ast.Import,ast.ImportFrom)):continue
        if len(imports)>=MAX_ITEMS:limited=True;break
        if isinstance(node,ast.Import):
            modules=[a.name for a in node.names[:MAX_ITEMS]];text='import'
        else:
            base=node.module or ''
            if node.level:
                parts=package.split('.') if package else []
                base='.'.join(parts[:len(parts)-node.level+1]+([base] if base else [])) if len(parts)>=node.level else None
            modules=[] if base is None else [base]
            if base is not None:
                # Candidate submodules, not a claim about runtime attributes/re-exports.
                modules += [base+'.'+a.name for a in node.names[:MAX_ITEMS] if a.name!='*']
            text='from '+'.'*node.level+(node.module or '')
        targets=set();ambiguous=False
        for name in modules:
            candidates=index.get(name,set())
            if len(candidates)==1:targets.update(candidates)
            elif len(candidates)>1:ambiguous=True
        names=[dict(name=display(a.name),alias=display(a.asname) if a.asname else None) for a in node.names[:MAX_ITEMS]]
        limited |= len(node.names)>MAX_ITEMS or len(targets)>MAX_ITEMS or len(text)>256 or any(len(a.name)>256 or len(a.asname or '')>256 for a in node.names[:MAX_ITEMS])
        imports.append(dict(kind=display(text),names=names,line=node.lineno,top_level=id(node) in top,
                            targets=[display(p) for p in sorted(targets)[:MAX_ITEMS]],
                            resolution='ambiguous' if ambiguous else 'local_candidate' if targets else 'external_or_unresolved'))
    return dict(symbols=symbols,imports=imports,symbols_imports_truncated=limited)


class RepoMapTool(RepositoryTool):
    name = 'repo_map'
    description = ('Optional first step for broad cross-file Coding analysis: map tracked paths and Python AST '
                   'functions/classes/methods/imports, then use search_code/read_file_range for real implementation. '
                   'No business semantics inferred, no runtime import graph, no execution. Simple tasks need no map. '
                   'At most120 files,512KiB/file,12KiB total; untracked/private/symlink files omitted.')
    parameters = {'type':'object','properties':{'max_files':{'type':'integer','minimum':1,'maximum':MAX_FILES}},'additionalProperties':False}

    async def _execute(self,**args):
        try:
            self.validate(args);maximum=args.get('max_files',MAX_FILES);root=await self.git_root('.')
            listing=await self.git(['ls-files','--cached','-z'],root,stdout_limit=65536,separator=b'\0',record_limit=maximum+1,
                                   record_filter=lambda raw:eligible(raw.decode('utf-8')))
            if listing.timed_out:return ToolResult(False,error='repo_map_timeout',metadata={'truncated':True})
            if listing.code and not (listing.code<0 and listing.truncated):return ToolResult(False,error='repo_map_listing_failed')
            paths=[];truncated=listing.truncated
            for raw in listing.stdout.split(b'\0')[:-1]:
                try:
                    name=raw.decode('utf-8')
                    if eligible(name) and name not in paths:paths.append(name)
                except (UnicodeError,ValueError):truncated=True
                if len(paths)>maximum:truncated=True;break
            paths=paths[:maximum];index={}
            for path in paths:
                try:
                    target=self.resolve(path,root=root)
                    if any(p.is_symlink() for p in [root.joinpath(*PurePosixPath(path).parts[:i]) for i in range(1,len(PurePosixPath(path).parts)+1)]):continue
                    if not target.is_file():continue
                except (OSError,ValueError):continue
                name=module_name(path)
                if name:index.setdefault(name,set()).add(path)
            payload=dict(files=[],scanned_files=0,shown_files=0,skipped_files=0,truncated=truncated,tracked_only=True,
                         static_only=True,import_resolution='bounded repository-path candidates; runtime search path/re-exports not proven',
                         limits=dict(files=maximum,file_bytes=MAX_FILE_BYTES,output_bytes=MAX_OUTPUT_BYTES))
            for path in paths:
                await asyncio.sleep(0)  # Let the original RepositoryTool deadline interrupt between files.
                try:
                    target=self.resolve(path,root=root)
                    if any(root.joinpath(*PurePosixPath(path).parts[:i]).is_symlink() for i in range(1,len(PurePosixPath(path).parts)+1)):
                        payload['skipped_files']+=1;continue
                    if not target.is_file():payload['skipped_files']+=1;continue
                    payload['scanned_files']+=1
                    item=dict(path=display(path),path_truncated=len(path)>256,status='path_only')
                    payload['truncated'] |= item['path_truncated']
                    if target.stat().st_size>MAX_FILE_BYTES:item['status']='file_too_large';payload['truncated']=True
                    elif path.endswith('.py'):
                        # Reuse native regular-file/UTF8/NOFOLLOW policy, with a tighter size cap.
                        data=self.read_bytes(target,max_bytes=MAX_FILE_BYTES)
                        if len(data)>MAX_FILE_BYTES:item['status']='file_too_large';payload['truncated']=True
                        else:
                            try:item.update(facts(data,path,index));item['status']='parsed';payload['truncated']|=item['symbols_imports_truncated']
                            except (SyntaxError,ValueError,RecursionError,MemoryError):item['status']='parse_error'
                    payload['files'].append(item);payload['shown_files']=len(payload['files'])
                    # Keep valid JSON; never cut a serialized string or an import record in half.
                    output_limited=False
                    while len(json.dumps(payload,ensure_ascii=True).encode())>MAX_OUTPUT_BYTES-512:
                        output_limited=True;payload['truncated']=True
                        item['symbols_imports_truncated']=True
                        if item.get('imports'):item['imports'].pop()
                        elif item.get('symbols'):item['symbols'].pop()
                        else:
                            payload['files'].pop();payload['shown_files']=len(payload['files']);break
                    if output_limited:break
                except (OSError,ValueError):payload['skipped_files']+=1
            payload['index_incomplete']=payload['truncated'] or payload['skipped_files']>0
            result=ToolResult(True,json.dumps(payload,ensure_ascii=True),metadata=dict(truncated=payload['truncated'],scanned_files=payload['scanned_files']))
            assert len(result.to_text().encode())<=MAX_OUTPUT_BYTES
            return result
        except (OSError,ValueError) as exc:return self.failure(exc)
