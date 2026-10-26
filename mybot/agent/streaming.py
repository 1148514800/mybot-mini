"""Bounded ChatCompletion stream assembly. No tool executes in this module."""
import asyncio,json,re,time
from types import SimpleNamespace as N
from uuid import uuid4
from contextvars import ContextVar

PROGRESS=ContextVar('stream_progress',default=None)
OBSERVER=ContextVar('stream_observer',default=None)
class StreamCleanupError(RuntimeError):pass

class SafePreview:
    """Release complete bounded lines, never separately redact arbitrary chunks.

    Long lines are suppressed before any prefix is released. Known multi-line
    secrets disable preview. This is conservative display, not secret discovery.
    """
    def __init__(self,secrets=()):
        self.secrets=tuple(s for s in secrets if isinstance(s,str) and s);self.pending='';self.dropping=False
        self.disabled=any('\n' in s or '\r' in s for s in self.secrets)
    def feed(self,text,final=False):
        from ..web.security import redact
        if self.disabled:return ''
        out=[]
        for part in text.splitlines(keepends=True):
            self.pending+=part
            if len(self.pending)>4096:self.pending='';self.dropping=True
            if part.endswith(('\n','\r')):
                out.append('[该段预览已保守隐藏]\n' if self.dropping else self.clean(self.pending,redact))
                self.pending='';self.dropping=False
        if final and (self.pending or self.dropping):
            out.append('[该段预览已保守隐藏]' if self.dropping else self.clean(self.pending,redact));self.pending='';self.dropping=False
        return ''.join(out)
    def clean(self,text,redact):
        for secret in self.secrets:text=text.replace(secret,'[已隐藏]')
        for secret in self.secrets:
            for n in range(min(len(secret)-1,len(text)),0,-1):
                if text.endswith(secret[:n]):text=text[:-n]+'[未完成敏感片段已隐藏]';break
        text=redact(text,self.secrets)
        text=re.sub(r'(?i)((?:nonce|receipt)\s*["\x27]?\s*[:=]\s*)[^\n,;]+',r'\1[已隐藏]',text)
        return re.sub(r'(?<![\w])[A-Za-z0-9_-]{24,}(?![\w])','[不透明标记已隐藏]',text)


def get(obj,key,default=None):return obj.get(key,default) if isinstance(obj,dict) else getattr(obj,key,default)

async def consume(stream,*,record=None,notify=None,secrets=()):
    record=record if record is not None else {};sid=uuid4().hex;text='';calls={};finish=None;usage=None;status=None
    first=False;safe=SafePreview(secrets);preview='';revision=0;last=0.;pending=False;closed=False
    def emit(kind,**kw):
        if notify:notify(dict(type=kind,stream_id=sid,**kw))
    def flush(fragment='',final=False):
        nonlocal preview,revision,last,pending
        released=safe.feed(fragment,final=final)
        preview=(preview+released).encode('utf-8')[:8192].decode('utf-8',errors='ignore');pending|=bool(released)
        if pending and (final or time.monotonic()-last>=.1):
            revision+=1;emit('model_text_delta',text=preview,preview_revision=revision);record['output_exposed']=True;last=time.monotonic();pending=False
    record.update(streaming=True,first_chunk_received=False,output_exposed=False,terminal_trusted=False,stream_status='consuming')
    emit('model_stream_started',status='generating',text='',preview_revision=0)
    try:
        async for chunk in stream:
            first=True;record['first_chunk_received']=True
            progress=PROGRESS.get()
            if progress is not None:progress['received']=True
            if get(chunk,'error'):raise ValueError('stream_provider_error')
            if get(chunk,'usage') is not None:usage=get(chunk,'usage')
            choices=get(chunk,'choices')
            if not isinstance(choices,list):raise ValueError('stream_choices')
            if not choices:continue
            if len(choices)!=1 or get(choices[0],'index',0)!=0:raise ValueError('stream_choice_index')
            choice=choices[0];delta=get(choice,'delta');content=get(delta,'content');parts=get(delta,'tool_calls')
            if get(delta,'role') not in (None,'assistant'):raise ValueError('stream_role')
            if get(delta,'function_call') or (finish is not None and (content or parts)):raise ValueError('stream_after_finish')
            if content is not None:
                if not isinstance(content,str):raise ValueError('stream_content')
                if len(text)+len(content)>32768:
                    text+=content[:32768-len(text)];status='output_truncated';break
                text+=content
                flush(content)
            if parts is not None:
                if not isinstance(parts,list):raise ValueError('stream_calls')
                for part in parts:
                    i=get(part,'index')
                    if type(i) is not int or not 0<=i<16:raise ValueError('stream_tool_index')
                    c=calls.setdefault(i,dict(id='',name='',arguments=''))
                    f=get(part,'function');kind=get(part,'type')
                    if kind not in (None,'function'):raise ValueError('stream_tool_type')
                    for key,value in [('id',get(part,'id')),('name',get(f,'name')),('arguments',get(f,'arguments'))]:
                        if value is not None:
                            if not isinstance(value,str):raise ValueError('stream_tool_fragment')
                            limit=256 if key=='id' else 128 if key=='name' else 65536
                            if len(c[key])+len(value)>limit or sum(len(v) for call in calls.values() for v in call.values())+len(value)>65536:raise ValueError('stream_tool_limit')
                            c[key]+=value
                    if len(c['id'])>256 or len(c['name'])>128 or sum(len(v) for call in calls.values() for v in call.values())>65536:raise ValueError('stream_tool_limit')
            reason=get(choice,'finish_reason')
            if reason is not None:
                if finish is not None:raise ValueError('stream_duplicate_finish')
                finish=reason
        if status is None:
            status={'stop':'complete' if text.strip() and not calls else 'provider_error' if calls else 'empty_response',
                'tool_calls':'tool_calls' if calls else 'provider_error','length':'output_truncated','content_filter':'content_filtered'}.get(finish,'response_unconfirmed')
        if status=='tool_calls':
            from ..tools.arguments import parse_object
            if sorted(calls)!=list(range(len(calls))):raise ValueError('stream_tool_gap')
            ids=set()
            for c in calls.values():
                if not c['id'] or c['id'] in ids or not re.fullmatch(r'[A-Za-z0-9_]{1,128}',c['name']) or not isinstance(parse_object(c['arguments'],max_bytes=65536),dict):raise ValueError('stream_tool_incomplete')
                ids.add(c['id'])
    except asyncio.CancelledError:
        status='cancelled';raise
    except Exception:
        if not first:raise  # Only the original failover policy may retry before any chunk.
        status='provider_error';usage=None
    finally:
        record['stream_status']=status or 'provider_error'
        try:
            close=getattr(stream,'close',None) or getattr(stream,'aclose',None)
            if close is None:raise StreamCleanupError('stream_close_unavailable')
            await asyncio.wait_for(close(),3);closed=True
        except BaseException as exc:
            record.update(stream_status='interrupted',terminal_trusted=False)
            emit('model_stream_incomplete',status='interrupted',text=preview,preview_revision=revision)
            raise StreamCleanupError('stream_cleanup_unconfirmed') from exc
        finally:
            if closed:
                flush(final=True)
                emit('model_stream_finished' if status in ('complete','tool_calls') else 'model_stream_incomplete',
                    status=status or 'provider_error',text=preview,preview_revision=revision)
    trusted=finish in ('stop','tool_calls','length','content_filter') and status in ('complete','tool_calls','output_truncated','content_filtered','empty_response')
    record.update(terminal_trusted=trusted,stream_status=status)
    if not trusted:usage=None
    assembled=[N(id=c['id'],type='function',function=N(name=c['name'],arguments=c['arguments'])) for _,c in sorted(calls.items())] if status=='tool_calls' else None
    return N(choices=[N(message=N(content=text[:32768],tool_calls=assembled),finish_reason=finish)],usage=usage,
        stream_delivery=dict(status=status,finish_reason=finish if isinstance(finish,str) else 'unknown',complete=status=='complete'))
