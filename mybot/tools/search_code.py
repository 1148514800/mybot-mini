"""ripgrep JSON, bounded during reading; no shell, PCRE2, config or code execution."""
import base64
import fnmatch
import json
from pathlib import Path
from .repository import RepositoryTool,json_result,blocked,MAX_FILE_BYTES
from .readonly_process import run_readonly
from .base import ToolResult


class SearchCodeTool(RepositoryTool):
    name='search_code'
    description=('Search workspace code using literal or Rust regex (no PCRE2). Respects gitignore; '
                 'For broad cross-file structure you may first use repo_map, then read_file_range. '
                 'Skips hidden/private/cache/dependency/binary files. Returns bounded paths, lines and UTF-8 byte columns.')
    parameters={'type':'object','properties':{
        'query':{'type':'string','minLength':1,'maxLength':256},'path':{'type':'string','minLength':1,'maxLength':4096},
        'mode':{'type':'string','enum':['literal','regex']},'case_sensitive':{'type':'boolean'},
        'file_glob':{'type':'string','minLength':1,'maxLength':256},'max_results':{'type':'integer','minimum':1,'maximum':50}},
        'required':['query'],'additionalProperties':False}

    async def _execute(self,**args):
        try:
            self.validate(args);q=args['query'];mode=args.get('mode','literal');maximum=args.get('max_results',50)
            if not q.strip() or '\x00' in q:raise ValueError('invalid_query')
            target=self.resolve(args.get('path','.'))
            if not target.exists():raise FileNotFoundError()
            if not (target.is_dir() or target.is_file()):raise ValueError('not_regular_file')
            if target.is_file() and target.stat().st_size>MAX_FILE_BYTES:raise ValueError('file_too_large')
            from .repository import BLOCKED_DIRS,BLOCKED_SUFFIXES
            exclusions=[]
            for pattern in ['!**/.*',*('!**/'+n+'/**' for n in sorted(BLOCKED_DIRS)),
                            *('!*'+s for s in sorted(BLOCKED_SUFFIXES)),
                            '!**/config/config.json','!**/credentials*','!**/id_rsa','!**/id_ed25519']:
                exclusions.append('--iglob='+pattern)
            # Enumerate BEFORE filtering user globs: a positive rg glob otherwise overrides gitignore.
            directory=target if target.is_dir() else target.parent
            listing=await run_readonly('rg',['--no-config','--files','--null','--sort=path','--no-follow',
                '--no-require-git',*(['--max-depth=1'] if target.is_file() else []),*exclusions,
                '--','./'+str(directory.relative_to(self.workspace))],cwd=self.workspace,workspace=self.workspace,
                separator=b'\0',record_limit=2049)
            if listing.timed_out:return ToolResult(False,error='search_timeout',metadata={'timed_out':True,'truncated':True})
            if listing.code not in (0,1) and not (listing.code<0 and listing.truncated):return ToolResult(False,error='search_failed')
            paths=[];file_truncated=listing.truncated
            for raw in listing.stdout.split(b'\0')[:-1]:
                try:
                    path=raw.decode('utf-8');resolved=self.resolve(path)
                    if target.is_file() and resolved!=target:continue
                    if not resolved.is_file() or resolved.stat().st_size>MAX_FILE_BYTES:continue
                    pattern=args.get('file_glob','*')
                    if not (fnmatch.fnmatchcase(path.removeprefix('./'),pattern) or fnmatch.fnmatchcase(resolved.name,pattern)):continue
                except (OSError,ValueError,UnicodeError):continue
                if len(paths)>=2048:file_truncated=True;break
                paths.append('./'+str(resolved.relative_to(self.workspace)))
            if not paths:
                return json_result({'matches':[],'message':'File listing truncated; refine path.' if file_truncated else 'No matches.'},
                    {'shown':0,'truncated':file_truncated,'max_results':maximum,'search_mode':mode,'timed_out':False})
            options=['--no-config','--engine=default','--json','--line-number','--column','--sort=path','--color=never',
                     '--no-follow','--max-filesize=2M','--case-sensitive' if args.get('case_sensitive',True) else '--ignore-case']
            if mode=='literal':options.append('--fixed-strings')
            result=await run_readonly('rg',[*options,'--',q,*paths],cwd=self.workspace,workspace=self.workspace,
                record_limit=maximum+1,record_filter=lambda line: json.loads(line).get('type')=='match')
            if result.timed_out:return ToolResult(False,error='search_timeout',metadata={'timed_out':True,'truncated':True})
            if result.code not in (0,1) and not (result.code<0 and result.truncated):return ToolResult(False,error='search_failed')
            matches=[];truncated=result.truncated or file_truncated;omitted=0;validated=set()
            def value(obj):return obj['text'] if 'text' in obj else base64.b64decode(obj['bytes']).decode('utf-8')
            for raw in result.stdout.splitlines():
                try:event=json.loads(raw)
                except ValueError:
                    if result.truncated:break
                    return ToolResult(False,error='invalid_search_output')
                if event['type']!='match':continue
                data=event['data']
                try:
                    path=value(data['path']);text=value(data['lines'])
                    resolved=self.resolve(path)
                    if resolved not in validated:self.read_text(resolved);validated.add(resolved)
                except (OSError,ValueError,UnicodeError):omitted+=1;continue
                if len(matches)>=maximum:truncated=True;break
                item={'path':str(resolved.relative_to(self.workspace)),'line':data['line_number'],
                      'column':data['submatches'][0]['start']+1,'text':text[:500],
                      'text_truncated':len(text)>500}
                proposal=[*matches,item]
                if len(json.dumps({'matches':proposal},ensure_ascii=False))>14000:truncated=True;break
                matches=proposal
            payload={'matches':matches}
            if not matches:payload['message']='Search truncated; refine query.' if truncated else ('No UTF-8 matches (some results omitted).' if omitted else 'No matches.')
            return json_result(payload,{'shown':len(matches),'truncated':truncated or any(m['text_truncated'] for m in matches),'max_results':maximum,
                                       'search_mode':mode,'timed_out':False,'omitted_non_utf8_or_policy':omitted})
        except (OSError,ValueError) as exc:return self.failure(exc)
