"""Bounded ChatCompletion stream assembly. No tool executes in this module."""
import asyncio,json,re,time
from types import SimpleNamespace as N
from uuid import uuid4
from contextvars import ContextVar
from collections import deque
from enum import StrEnum

import httpx
from openai.types.chat.chat_completion_chunk import ChoiceDeltaFunctionCall
from openai import APIError

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

class StreamErrorCode(StrEnum):
    CHOICES = 'stream_choices_invalid'
    CHOICE_INDEX = 'stream_choice_index_invalid'
    ROLE = 'stream_role_invalid'
    CONTENT = 'stream_content_type_invalid'
    LEGACY_UNSUPPORTED = 'stream_legacy_function_call_unsupported'
    LEGACY_INVALID = 'stream_legacy_function_call_invalid'
    AFTER_FINISH = 'stream_after_finish_payload'
    DUPLICATE_FINISH = 'stream_duplicate_finish'
    TOOL_FRAGMENT = 'stream_tool_fragment_invalid'
    TOOL_ARGUMENTS = 'stream_tool_arguments_invalid'
    TOOL_GAP = 'stream_tool_index_gap'
    PROVIDER_FRAME = 'stream_provider_error_frame'
    TRANSPORT = 'stream_transport_interrupted'
    BUFFER = 'stream_local_buffer_limit'
    TERMINAL = 'stream_terminal_missing'
    CLOSE = 'stream_close_unconfirmed'
    CANCELLED = 'stream_user_or_caller_cancelled'
    TIMEOUT = 'stream_local_timeout'
    HOST = 'stream_host_failure'


class StreamProtocolError(ValueError):
    def __init__(self, code):
        self.code = StreamErrorCode(code)
        super().__init__(self.code.value)


def _kind(value):
    # Fixed vocabulary: even malicious class names / finish strings cannot escape.
    return ('null' if value is None else 'string' if isinstance(value, str) else
            'list' if isinstance(value, list) else 'object' if isinstance(value, dict) else 'other')


def _finish(value):
    return value if value in ('stop', 'tool_calls', 'length', 'content_filter', None) else 'unknown'


def _legacy(delta):
    """No invocation authority: only known empty dict/SDK fields are ignorable.

    SDK construct parsing may retain invalid types and unknown fields. Never use
    model truthiness or dump its values into diagnostics. Counts are saturated.
    """
    value = get(delta, 'function_call')
    present = ('function_call' in delta if isinstance(delta, dict) else
               'function_call' in getattr(delta, 'model_fields_set', vars(delta) if hasattr(delta, '__dict__') else ()))
    fields = value if isinstance(value, dict) else vars(value) if isinstance(value, ChoiceDeltaFunctionCall) else {}
    extras = (getattr(value, 'model_extra', None) or {}) if isinstance(value, ChoiceDeltaFunctionCall) else {}
    extra_count = len((fields.keys() | extras.keys()) - {'name', 'arguments'})
    name, arguments = get(value, 'name'), get(value, 'arguments')
    valid = (value is None or isinstance(value, (dict, ChoiceDeltaFunctionCall))) and all(v is None or isinstance(v, str) for v in (name, arguments))
    empty = valid and extra_count == 0 and name in (None, '') and arguments in (None, '')
    metadata = dict(legacy_function_call_present=present,
        legacy_function_call_kind='object' if isinstance(value, ChoiceDeltaFunctionCall) else _kind(value),
        legacy_name_kind=_kind(name), legacy_name_length=min(len(name), 65536) if isinstance(name, str) else None,
        legacy_arguments_kind=_kind(arguments), legacy_arguments_length=min(len(arguments), 65536) if isinstance(arguments, str) else None,
        legacy_extra_field_count=min(extra_count, 256), legacy_semantically_empty=empty)
    code = None if empty else StreamErrorCode.LEGACY_INVALID if not valid else StreamErrorCode.LEGACY_UNSUPPORTED
    return metadata, code


async def consume(stream, *, record=None, notify=None, secrets=()):
    record = record if record is not None else {}
    sid = uuid4().hex
    text = ''; calls = {}; finish = None; usage = None; status = None
    safe = SafePreview(secrets); preview = ''; revision = 0; last = 0.; pending = False
    count = 0; terminals = 0; eof = False; closed = False; close_called = False
    phase = 'opening'; code = None; origin = None; recent = deque(maxlen=8); iterator = None

    def reject(reason):
        raise StreamProtocolError(reason)

    def diagnostic():
        return dict(stream_id=sid, error_code=code.value if code else None, origin=origin,
                    phase=phase, chunk_index=count, chunks_observed=count,
                    finish_reason=_finish(finish), terminal_count=terminals,
                    text_received=bool(text), natural_eof=eof, close_called=close_called,
                    closed=closed, recent_chunks=list(recent))

    def emit(kind, **kw):
        if notify: notify(dict(type=kind, stream_id=sid, **kw))

    def flush(fragment='', final=False):
        nonlocal preview, revision, last, pending
        released = safe.feed(fragment, final=final)
        preview = (preview + released).encode('utf-8')[:8192].decode('utf-8', errors='ignore')
        pending |= bool(released)
        if pending and (final or time.monotonic() - last >= .1):
            revision += 1
            emit('model_text_delta', text=preview, preview_revision=revision)
            record['output_exposed'] = True; last = time.monotonic(); pending = False

    record.update(streaming=True, first_chunk_received=False, output_exposed=False,
                  terminal_trusted=False, stream_status='consuming')
    emit('model_stream_started', status='generating', text='', preview_revision=0)
    try:
        iterator = stream.__aiter__()
        while True:
            phase = 'sdk_iteration'
            try:
                chunk = await anext(iterator)
            except StopAsyncIteration:
                eof = True
                break
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                code = StreamErrorCode.TIMEOUT; origin = 'timeout'
                raise
            except (APIError, httpx.HTTPError, OSError):
                code = StreamErrorCode.TRANSPORT; origin = 'sdk_transport'
                if not count: raise  # Original failover boundary, before any genuine chunk.
                status = 'provider_error'; usage = None
                break
            count += 1; record['first_chunk_received'] = True
            progress = PROGRESS.get()
            if progress is not None: progress['received'] = True
            phase = 'protocol_validation'
            choices = get(chunk, 'choices')
            choice = choices[0] if isinstance(choices, list) and choices else None
            delta = get(choice, 'delta'); content = get(delta, 'content'); parts = get(delta, 'tool_calls')
            reason = get(choice, 'finish_reason')
            if reason is not None: terminals += 1
            legacy, legacy_error = _legacy(delta)
            recent.append(dict(chunk_index=count,
                choices_count=len(choices) if isinstance(choices, list) else None,
                delta_present=delta is not None, role_present=get(delta, 'role') is not None,
                content_type=_kind(content), content_length=len(content) if isinstance(content, str) else None,
                tool_calls_count=len(parts) if isinstance(parts, list) else None,
                finish_reason=_finish(reason), **legacy))
            if get(chunk, 'error'): reject(StreamErrorCode.PROVIDER_FRAME)
            if get(chunk, 'usage') is not None: usage = get(chunk, 'usage')
            if not isinstance(choices, list): reject(StreamErrorCode.CHOICES)
            if not choices: continue  # Standard usage-only trailer, including after finish.
            if len(choices) != 1 or type(get(choice, 'index', 0)) is not int or get(choice, 'index', 0) != 0:
                reject(StreamErrorCode.CHOICE_INDEX)
            if delta is not None and not isinstance(delta, dict) and not hasattr(type(delta), 'model_fields'):
                reject(StreamErrorCode.CHOICES)
            if get(delta, 'role') not in (None, 'assistant'): reject(StreamErrorCode.ROLE)
            if legacy_error is not None: reject(legacy_error)
            if finish is not None and (content or parts):
                reject(StreamErrorCode.AFTER_FINISH)
            if content is not None:
                if not isinstance(content, str): reject(StreamErrorCode.CONTENT)
                if len(text) + len(content) > 32768:
                    text += content[:32768-len(text)]
                    code = StreamErrorCode.BUFFER; origin = 'local_limit'; status = 'output_truncated'
                    break
                text += content
                phase = 'preview'; flush(content); phase = 'protocol_validation'
            if parts is not None:
                if not isinstance(parts, list): reject(StreamErrorCode.TOOL_FRAGMENT)
                for part in parts:
                    i = get(part, 'index')
                    if type(i) is not int or not 0 <= i < 16: reject(StreamErrorCode.TOOL_FRAGMENT)
                    c = calls.setdefault(i, dict(id='', name='', arguments=''))
                    f = get(part, 'function')
                    if get(part, 'type') not in (None, 'function'): reject(StreamErrorCode.TOOL_FRAGMENT)
                    for key, value in [('id', get(part, 'id')), ('name', get(f, 'name')), ('arguments', get(f, 'arguments'))]:
                        if value is not None:
                            if not isinstance(value, str): reject(StreamErrorCode.TOOL_FRAGMENT)
                            limit = 256 if key == 'id' else 128 if key == 'name' else 65536
                            if len(c[key])+len(value)>limit or sum(len(v) for call in calls.values() for v in call.values())+len(value)>65536:
                                reject(StreamErrorCode.BUFFER)
                            c[key] += value
            if reason is not None:
                if finish is not None: reject(StreamErrorCode.DUPLICATE_FINISH)
                finish = reason
        if status is None:
            phase = 'terminal_validation'
            status = {'stop': 'complete' if text.strip() and not calls else 'provider_error' if calls else 'empty_response',
                      'tool_calls': 'tool_calls' if calls else 'provider_error', 'length': 'output_truncated',
                      'content_filter': 'content_filtered'}.get(_finish(finish), 'response_unconfirmed')
            if status == 'response_unconfirmed': code = StreamErrorCode.TERMINAL; origin = 'protocol_validation'
            if status == 'provider_error': reject(StreamErrorCode.TOOL_ARGUMENTS)
        if status == 'tool_calls':
            from ..tools.arguments import parse_object
            if sorted(calls) != list(range(len(calls))): reject(StreamErrorCode.TOOL_GAP)
            ids = set()
            for c in calls.values():
                if not c['id'] or c['id'] in ids or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', c['name']):
                    reject(StreamErrorCode.TOOL_FRAGMENT)
                try: arguments = parse_object(c['arguments'], max_bytes=65536)
                except (ValueError, TypeError): reject(StreamErrorCode.TOOL_ARGUMENTS)
                if not isinstance(arguments, dict): reject(StreamErrorCode.TOOL_ARGUMENTS)
                ids.add(c['id'])
    except StreamProtocolError as exc:
        code = exc.code; origin = 'provider_frame' if code == StreamErrorCode.PROVIDER_FRAME else 'local_limit' if code == StreamErrorCode.BUFFER else 'protocol_validation'
        status = 'provider_error'; usage = None
    except asyncio.CancelledError:
        code = StreamErrorCode.CANCELLED; origin = 'caller_cancellation'; status = 'cancelled'
        raise
    except TimeoutError:
        code = StreamErrorCode.TIMEOUT; origin = 'timeout'; status = 'interrupted'
        raise
    except BaseException:
        # Includes budget/freeze/store/approval and unexpected host failures. Do NOT
        # disguise these as provider errors or make them eligible for retry.
        if code is None: code = StreamErrorCode.HOST; origin = 'host'
        status = 'interrupted'
        raise
    finally:
        failure_phase = phase
        record['stream_status'] = status or 'provider_error'
        try:
            close_called = True
            async def close_owned():
                try:
                    # Close a distinct generator before its owner settles resource
                    # accounting, so local rejection is not mistaken for EOF.
                    if iterator is not None and iterator is not stream:
                        end = getattr(iterator, 'aclose', None)
                        if end is not None: await end()
                finally:
                    close = getattr(stream, 'close', None) or getattr(stream, 'aclose', None)
                    if close is None: raise StreamCleanupError('stream_close_unavailable')
                    await close()
            await asyncio.wait_for(close_owned(), 3); closed = True
        except BaseException as exc:
            # Preserve the primary error classification in a separate bounded field.
            record['stream_primary_error_code'] = code.value if code else None
            code = StreamErrorCode.CLOSE; origin = 'cleanup'; phase = 'close'
            record.update(stream_status='interrupted', terminal_trusted=False, stream_diagnostic=diagnostic())
            emit('model_stream_incomplete', status='interrupted', text=preview,
                 preview_revision=revision, error_code=code.value)
            raise StreamCleanupError(code.value) from None
        finally:
            if closed:
                phase = failure_phase
                record['stream_diagnostic'] = diagnostic()
                flush(final=True)
                emit('model_stream_finished' if status in ('complete', 'tool_calls') else 'model_stream_incomplete',
                     status=status or 'provider_error', text=preview, preview_revision=revision,
                     error_code=code.value if code else None)
    trusted = eof and closed and finish in ('stop', 'tool_calls', 'length', 'content_filter') and status in ('complete', 'tool_calls', 'output_truncated', 'content_filtered', 'empty_response')
    record.update(terminal_trusted=trusted, stream_status=status)
    if not trusted: usage = None
    assembled = [N(id=c['id'], type='function', function=N(name=c['name'], arguments=c['arguments'])) for _, c in sorted(calls.items())] if status == 'tool_calls' and trusted else None
    return N(choices=[N(message=N(content=text[:32768], tool_calls=assembled), finish_reason=finish)], usage=usage,
             stream_delivery=dict(status=status, finish_reason=_finish(finish) or 'unknown', complete=status=='complete' and trusted,
                                  error_code=code.value if code else None))
