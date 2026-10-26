"""Same-origin authenticated loopback ASGI app. No filesystem browsing or CORS."""
from contextlib import asynccontextmanager
import asyncio
import json
from pathlib import Path
import secrets

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from .runtime import ChatRuntime
from .security import redact
from ..storage.event_schema import StoreError

STATIC = Path(__file__).parent / 'static'
MAX_BODY = 32768


class Boundary:
    def __init__(self, app, *, authority, cookie, csrf):
        self.app = app; self.authority = authority; self.cookie = cookie; self.csrf = csrf

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope, receive, send)
        headers = dict(scope['headers']); method = scope['method']; path = scope['path']
        origin = headers.get(b'origin', b'').decode('latin1')
        forbidden = (headers.get(b'host', b'').decode('latin1') != self.authority
            or (origin and origin != 'http://' + self.authority)
            or headers.get(b'sec-fetch-site') == b'cross-site')
        if method not in ('GET', 'HEAD'):
            forbidden |= origin != 'http://' + self.authority
            forbidden |= not secrets.compare_digest(headers.get(b'x-mybot-csrf', b''), self.csrf.encode())
        request = Request(scope)
        if path.startswith('/api/'):
            forbidden |= not secrets.compare_digest(request.cookies.get('mybot_browser', '').encode('utf-8'), self.cookie.encode())
        if forbidden:
            return await JSONResponse({'error': 'request_not_authorized'}, status_code=403)(scope, receive, send)
        if headers.get(b'transfer-encoding') or (headers.get(b'content-length') and
                (not headers[b'content-length'].isdigit() or int(headers[b'content-length']) > MAX_BODY)):
            return await JSONResponse({'error': 'body_too_large'}, status_code=413)(scope, receive, send)
        used = 0
        async def bounded_receive():
            nonlocal used
            event = await receive()
            if event['type'] == 'http.request':
                used += len(event.get('body', b''))
                if used > MAX_BODY: raise ValueError('body_too_large')
            return event
        async def secure_send(event):
            if event['type'] == 'http.response.start':
                event['headers'] += [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'), (b'x-frame-options', b'DENY'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
            await send(event)
        await self.app(scope, bounded_receive, secure_send)


SSE_CONNECTION_SECONDS = 2.0  # Finite requests let Uvicorn drain before lifespan shutdown.


def create_app(config=None, *, port=8765, client_factory=None, approval_timeout=90, task_timeout=600):
    options = {} if client_factory is None else {'client_factory': client_factory}
    runtime = ChatRuntime(config, approval_timeout=approval_timeout, task_timeout=task_timeout, **options)
    cookie = secrets.token_hex(32); csrf = secrets.token_hex(32)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await runtime.close()

    async def home(request):
        response = Response((STATIC / 'index.html').read_text(), media_type='text/html')
        response.set_cookie('mybot_browser', cookie, httponly=True, samesite='strict', path='/')
        return response

    async def asset(request):
        name = request.path_params['name']
        types = {'app.js': 'application/javascript', 'style.css': 'text/css', 'markdown.js': 'application/javascript'}
        if name not in types: return Response(status_code=404)
        return Response((STATIC / name).read_bytes(), media_type=types[name])

    async def bootstrap(request):
        try:runtime.sync()
        except StoreError:return JSONResponse({'error':'storage_failed'},status_code=503)
        config = runtime.config
        return JSONResponse({'csrf': csrf, 'workspace': config.workspace.name, 'provider': redact(config.provider, (config.api_key,)),
            'model': redact(config.model, (config.api_key,)), 'persistence': config.storage_backend=='event_sqlite', 'command_mode': config.coding_command['mode'],
            'receipt': config.coding_preview_receipt, 'coding': config.coding_enabled,
            'storage_notice': ('本地SQLite明文历史；不保存完整模型请求或授权。' if config.storage_backend=='event_sqlite' else '仅本次进程内存；固定事项也不跨重启。'),
            'busy': runtime.owner, 'cleanup_uncertain': runtime.cleanup_uncertain,
            'streaming_enabled':runtime.config.web_streaming,'steer_enabled':runtime.config.web_steer,'conversations': [{'id': c.id, 'title': c.title, 'status': c.status} for c in runtime.conversations.values()]})

    def find(request):
        runtime.sync()
        return runtime.conversations.get(request.path_params['id'])

    async def body(request):
        if request.headers.get('content-type', '').split(';')[0] != 'application/json': raise ValueError('invalid_json')
        raw = await request.body()
        if len(raw) > MAX_BODY: raise ValueError('body_too_large')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError('invalid_json')
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(value, dict): raise ValueError('invalid_json')
        return value

    async def conversations(request):
        try: c = runtime.new()
        except ValueError: return JSONResponse({'error': 'conversation_limit'}, status_code=409)
        except StoreError:return JSONResponse({'error':'storage_failed'},status_code=503)
        return JSONResponse(c.state(), status_code=201)

    async def state(request):
        c = find(request)
        return JSONResponse(c.state()) if c else JSONResponse({'error': 'not_found'}, status_code=404)

    async def message(request):
        c = find(request)
        if c is None: return JSONResponse({'error': 'not_found'}, status_code=404)
        try:
            value = await body(request)
            text = value.get('message')
            if set(value) != {'message'} or not isinstance(text, str) or not text.strip() or len(text) > 16000:
                raise ValueError('invalid_message')
            if text.strip().split()[0] in ('/undo','/changes','/clear','/decisions','/pins','/pin','/unpin','/repin','/sessions','/session','/history','/delete-session','/review-session'):
                return JSONResponse({'error': 'web_control_unsupported'}, status_code=400)
            accepted = await runtime.start(c, text)
        except StoreError:return JSONResponse({'error':'storage_failed'},status_code=503)
        except (ValueError, json.JSONDecodeError, RecursionError, UnicodeError):
            return JSONResponse({'error': 'invalid_message_or_unsupported_control'}, status_code=400)
        return JSONResponse({'accepted': accepted}, status_code=202 if accepted else 409)

    async def steer(request):
        c=find(request)
        if c is None:return JSONResponse({'error':'not_found'},status_code=404)
        try:return JSONResponse(runtime.steer(c,await body(request)))
        except StoreError as exc:
            state='stale_turn' if str(exc)=='stale_turn' else 'rejected'
            return JSONResponse({'status':state,'error':'steer_rejected_check_turn_capacity_and_approval'},status_code=409)
        except (ValueError,TypeError):return JSONResponse({'status':'rejected','error':'invalid_steer'},status_code=409)

    async def stop(request):
        c = find(request)
        if c is None: return JSONResponse({'error': 'not_found'}, status_code=404)
        # Shield cancellation of HTTP caller: cleanup/lease settlement continues server-side.
        await asyncio.shield(runtime.stop(c))
        return JSONResponse({'status': c.status})

    async def clear(request):
        c = find(request)
        if c is None: return JSONResponse({'error': 'not_found'}, status_code=404)
        return JSONResponse({'cleared': await runtime.clear(c)}, status_code=409 if runtime.owner is not None else 200)

    async def approval(request):
        c = find(request)
        if c is None: return JSONResponse({'error': 'not_found'}, status_code=404)
        try:
            value = await body(request)
            if set(value) != {'id', 'allow'}: raise ValueError()
            ok = c.approval is not None and runtime.owner == c.id and c.approval.resolve(value['id'], value['allow'])
        except (ValueError, RecursionError, UnicodeError): ok = False
        return JSONResponse({'accepted': ok}, status_code=200 if ok else 409)

    async def history_page(request):
        c=find(request)
        if c is None:return JSONResponse({'error':'not_found'},status_code=404)
        try:
            before=request.query_params.get('before')
            return JSONResponse({'messages':c.history.messages(before=int(before) if before else None)})
        except (StoreError,ValueError):return JSONResponse({'error':'history_unavailable'},status_code=409)

    async def pins(request):
        c=find(request)
        if c is None:return JSONResponse({'error':'not_found'},status_code=404)
        try:
            value=await body(request)
            if set(value)-{'message_id','start','end','category','confirmed','replace_id','expected_revision'}:raise ValueError('pin_fields')
            ident=runtime.pin(c,value)
            return JSONResponse({'pin_id':ident})
        except (StoreError,ValueError,KeyError,TypeError):return JSONResponse({'error':'pin_rejected'},status_code=409)

    async def revoke(request):
        c=find(request)
        if c is None:return JSONResponse({'error':'not_found'},status_code=404)
        try:
            value=await body(request)
            if set(value)!={'confirmed','revision'} or runtime.owner is not None:raise ValueError('pin_fields')
            c.history.pins.revoke(request.path_params['pin'],value['revision'],confirmed=value['confirmed'])
            return JSONResponse({'revoked':True})
        except (StoreError,ValueError):return JSONResponse({'error':'pin_rejected'},status_code=409)

    async def delete_conversation(request):
        c=find(request)
        if c is None:return JSONResponse({'error':'not_found'},status_code=404)
        try:
            value=await body(request)
            if set(value)!={'confirmed'} or value['confirmed'] is not True:raise ValueError('confirmation_required')
            ok=await runtime.delete(c,confirmed=True)
            return JSONResponse({'deleted':ok,'physical_erasure_guaranteed':False},status_code=200 if ok else 409)
        except (StoreError,ValueError):return JSONResponse({'error':'delete_rejected'},status_code=409)

    async def review(request):
        c=find(request)
        if c is None:return JSONResponse({'error':'not_found'},status_code=404)
        try:
            value=await body(request)
            if set(value)!={'confirmed','workspace_and_processes_checked'} or value['confirmed'] is not True or value['workspace_and_processes_checked'] is not True:raise ValueError('confirmation_required')
            runtime.review(c,confirmed=True);return JSONResponse({'reviewed':True})
        except (StoreError,ValueError):return JSONResponse({'error':'review_rejected'},status_code=409)

    async def events(request):
        c = find(request)
        if c is None: return JSONResponse({'error': 'not_found'}, status_code=404)
        try: cursor = max(0, int(request.headers.get('last-event-id', '0')))
        except ValueError: return Response(status_code=400)
        async def stream():
            nonlocal cursor
            retry_sent = False
            deadline = asyncio.get_running_loop().time() + SSE_CONNECTION_SECONDS
            while not runtime.closed and c.id in runtime.conversations:
                if asyncio.get_running_loop().time() >= deadline: return
                c.changed.clear()
                if cursor>c.sequence:
                    cursor=c.sequence
                    yield f'id: {cursor}\nevent: reset\ndata: {{}}\n\n'
                # A missed window triggers full authenticated state refresh, not fabricated events.
                if c.events and cursor < c.events[0]['sequence'] - 1:
                    cursor=c.sequence
                    yield f'id: {cursor}\nevent: reset\ndata: {{}}\n\n'
                for event in list(c.events):
                    if event['sequence'] > cursor:
                        cursor = event['sequence']
                        yield f'id: {cursor}\nevent: activity\ndata: {json.dumps(event, ensure_ascii=True)}\n\n'
                if not retry_sent:
                    # Preserve immediate reset/activity as the first frame.
                    yield 'retry: 250\n\n'
                    retry_sent = True
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0: return
                try: await asyncio.wait_for(c.changed.wait(), remaining)
                except TimeoutError: return  # Native EventSource reconnects with Last-Event-ID.
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})

    routes = [Route('/', home), Route('/static/{name}', asset), Route('/api/bootstrap', bootstrap),
        Route('/api/conversations', conversations, methods=['POST']), Route('/api/conversations/{id}', state),
        Route('/api/conversations/{id}/messages', message, methods=['POST']),
        Route('/api/conversations/{id}/steer',steer,methods=['POST']),
        Route('/api/conversations/{id}/stop', stop, methods=['POST']), Route('/api/conversations/{id}/clear', clear, methods=['POST']),
        Route('/api/conversations/{id}/history',history_page),
        Route('/api/conversations/{id}/pins',pins,methods=['POST']),
        Route('/api/conversations/{id}/pins/{pin}/revoke',revoke,methods=['POST']),
        Route('/api/conversations/{id}/delete',delete_conversation,methods=['POST']),
        Route('/api/conversations/{id}/review',review,methods=['POST']),
        Route('/api/conversations/{id}/approval', approval, methods=['POST']), Route('/api/conversations/{id}/events', events)]
    async def storage_error(request,exc):
        return JSONResponse({'error':'storage_failed'},status_code=503)

    core = Starlette(routes=routes, lifespan=lifespan,exception_handlers={StoreError:storage_error})
    app = Boundary(core, authority=f'127.0.0.1:{port}', cookie=cookie, csrf=csrf)
    app.runtime = runtime
    return app
