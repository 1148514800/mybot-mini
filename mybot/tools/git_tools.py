"""Read-only, literal-path Git status and bounded unified diff. No external drivers."""
import json
from pathlib import Path
from .repository import RepositoryTool,json_result,blocked,MAX_FILE_BYTES
from .base import ToolResult

DIFF_OPTIONS=['--no-ext-diff','--no-textconv','--no-color','--no-renames','--ignore-submodules=all']


def decode_path(raw):
    try:return raw.decode('utf-8')
    except UnicodeDecodeError:raise ValueError('invalid_path_encoding') from None


class GitStatusTool(RepositoryTool):
    name='git_status'
    description=('Read Git status inside Workspace, including staged/unstaged/untracked and rename paths. '
                 'At most 200 entries; truncated is never a clean assertion. Does not change the Index.')
    parameters={'type':'object','properties':{'repo_path':{'type':'string','minLength':1,'maxLength':4096}},
                'additionalProperties':False}

    async def _execute(self,**args):
        try:
            self.validate(args);root=await self.git_root(args.get('repo_path','.'))
            result=await self.git(['status','--porcelain=v1','-z','--untracked-files=normal',
                                   '--ignore-submodules=all','--renames'],root,separator=b'\0',record_limit=402)
            if result.timed_out:return ToolResult(False,error='git_timeout',metadata={'timed_out':True,'truncated':True})
            if result.code and not (result.code<0 and result.truncated):return ToolResult(False,error='git_status_failed')
            pieces=result.stdout.split(b'\0');files=[];i=0;truncated=result.truncated
            while i<len(pieces)-1:
                raw=pieces[i];i+=1
                if len(raw)<4:raise ValueError('invalid_git_status')
                xy=raw[:2].decode('ascii');path=decode_path(raw[3:]);previous=None
                if 'R' in xy or 'C' in xy:
                    if i>=len(pieces)-1:truncated=True;break
                    previous=decode_path(pieces[i]);i+=1
                if len(files)>=200:truncated=True;break
                labels={'M':'modified','A':'added','D':'deleted','R':'renamed','C':'copied','U':'unmerged','T':'type_changed','?':'untracked',' ':'unmodified'}
                item={'path':path,'index_status':xy[0],'worktree_status':xy[1],
                      'staged':xy[0] not in (' ','?'),'unstaged':xy[1] not in (' ','?'),
                      'untracked':xy=='??','status':'untracked' if xy=='??' else labels.get(xy[0] if xy[0]!=' ' else xy[1],'changed')}
                if previous is not None:item['previous_path']=previous
                proposal=[*files,item]
                if len(json.dumps(proposal,ensure_ascii=False))>45000:truncated=True;break
                files=proposal
            return json_result({'clean':not files and not truncated,'files':files,'truncated':truncated},
                               {'shown':len(files),'truncated':truncated,'timed_out':False})
        except (OSError,ValueError) as exc:return self.failure(exc)


class GitDiffTool(RepositoryTool):
    name='git_diff'
    description=('Read tracked-file unified diff: unstaged is Working Tree vs Index; staged is Index vs HEAD. '
                 'No pager/external diff/textconv. Bounded to 300 lines/24000 characters; check truncated. '
                 'Untracked content is absent: use git_status and read_file_range. Private paths are excluded.')
    parameters={'type':'object','properties':{'repo_path':{'type':'string','minLength':1,'maxLength':4096},
                'scope':{'type':'string','enum':['unstaged','staged']},
                'file_path':{'type':'string','minLength':1,'maxLength':4096}},'additionalProperties':False}

    async def _execute(self,**args):
        try:
            self.validate(args);root=await self.git_root(args.get('repo_path','.'))
            scope=args.get('scope','unstaged');options=['diff',*DIFF_OPTIONS,*(['--cached'] if scope=='staged' else [])]
            paths=[];truncated=False;excluded=0
            if 'file_path' in args:
                target=self.resolve(args['file_path'],root=root)
                if target.is_dir():raise ValueError('file_path_must_be_file')
                if target.exists() and target.stat().st_size>MAX_FILE_BYTES:raise ValueError('file_too_large')
                paths=[str(target.relative_to(root))]
            else:
                names=await self.git([*options,'--name-only','-z','--'],root,separator=b'\0',record_limit=202)
                if names.timed_out:return ToolResult(False,error='git_timeout',metadata={'timed_out':True,'truncated':True})
                if names.code and not (names.code<0 and names.truncated):return ToolResult(False,error='git_diff_failed')
                truncated=names.truncated
                for raw in names.stdout.split(b'\0')[:-1]:
                    try:
                        target=self.resolve(decode_path(raw),root=root)
                        if target.exists() and (not target.is_file() or target.stat().st_size>MAX_FILE_BYTES):raise ValueError('excluded_file')
                    except (OSError,ValueError):excluded+=1;continue
                    paths.append(str(target.relative_to(root)))
            text=''
            if paths:
                result=await self.git([*options,'--unified=3','--',*paths],root,stdout_limit=100000,record_limit=302)
                if result.timed_out:return ToolResult(False,error='git_timeout',metadata={'timed_out':True,'truncated':True})
                if result.code and not (result.code<0 and result.truncated):return ToolResult(False,error='git_diff_failed')
                try:text=result.stdout.decode('utf-8')
                except UnicodeDecodeError:
                    if not result.truncated:raise ValueError('invalid_utf8_diff') from None
                    # Trim only a possibly incomplete terminal UTF-8 sequence, never replace bytes.
                    for trim in (1,2,3):
                        try:text=result.stdout[:-trim].decode('utf-8');break
                        except UnicodeDecodeError:continue
                    else:raise ValueError('invalid_utf8_diff')
                truncated|=result.truncated
            lines=text.splitlines(keepends=True)
            clipped=''.join(lines[:300])[:23000]
            truncated|=len(clipped)!=len(text)
            empty = '(diff truncated; no complete text shown)' if truncated else ('(no eligible tracked diff; policy exclusions apply)' if excluded else '(no tracked diff)')
            return ToolResult(True,clipped or empty,metadata={
                'scope':scope,'truncated':truncated,'shown_lines':len(clipped.splitlines()),'timed_out':False,
                'excluded_private_or_large_files':excluded,'untracked_content_included':False})
        except (OSError,ValueError) as exc:return self.failure(exc)
