"""Bounded UTF-8 line reads, preserving the underlying file and line endings."""
import hashlib
from .repository import RepositoryTool,json_result
from .base import ToolResult


class ReadFileRangeTool(RepositoryTool):
    name='read_file_range'
    description=('Read 1-based inclusive lines of a UTF-8 workspace file; at most 200 lines/2 MiB file. '
                 'Output is bounded; check truncated/next_start_line. Investigation evidence only, not a repair/test.')
    parameters={'type':'object','properties':{'path':{'type':'string','minLength':1,'maxLength':4096},
        'start_line':{'type':'integer','minimum':1},'end_line':{'type':'integer','minimum':1}},
        'required':['path','start_line','end_line'],'additionalProperties':False}

    def __init__(self, workspace, *, include_version=False):
        super().__init__(workspace)
        self.include_version = include_version

    async def _execute(self,**args):
        try:
            self.validate(args);start,end=args['start_line'],args['end_line']
            if end<start or end-start>=200:raise ValueError('invalid_line_range')
            data=self.read_bytes(self.resolve(args['path']));text=data.decode('utf-8')
            parts=text.split('\n');lines=[p+'\n' for p in parts[:-1]]+([parts[-1]] if parts[-1] else [])
            if lines and start>len(lines):raise ValueError('start_line_out_of_range')
            output=[];size=0;partial=None;last=None
            for n in range(start,min(end,len(lines))+1):
                line=f'{n} | '+lines[n-1]
                room=14500-size
                if len(line)>room:
                    if room>20:output.append(line[:room]);last=n;partial=n
                    break
                output.append(line);size+=len(line);last=n
            truncated=partial is not None or (last is not None and last<min(end,len(lines)))
            next_line=partial or (last+1 if last is not None and last<len(lines) else None)
            return ToolResult(True,''.join(output) if lines else '(empty file)',metadata={
                'requested_start_line':start,'returned_start_line':start if last else None,
                'returned_end_line':last,'total_lines':len(lines),'truncated':truncated,
                'next_start_line':next_line,'partial_line':partial,
                **({'file_sha256':hashlib.sha256(data).hexdigest(),'file_bytes':len(data)} if self.include_version else {})})
        except (OSError,ValueError) as exc:return self.failure(exc)
