"""One-shot loopback callback; no SDK context is moved to a child task."""
import asyncio
import re
import sys
import webbrowser
from urllib.parse import parse_qsl, urlsplit

from mcp.shared.auth import AuthorizationCodeResult
from .errors import HTTPTransportError

CALLBACK_TIMEOUT = 120


class OAuthCallback:
    def __init__(self, uri):
        self.uri = urlsplit(uri)
        self.server = None
        self.result = None
        self.handlers = set()
        self.used = False

    async def start(self):
        self.result = asyncio.get_running_loop().create_future()
        try:
            self.server = await asyncio.start_server(self.handle, '127.0.0.1', self.uri.port,
                                                     limit=8192, start_serving=True)
        except OSError:
            raise HTTPTransportError('oauth_callback_bind_failed') from None

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        status, value = 400, None
        try:
            head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 5)
            if len(head) > 8192:
                raise ValueError
            lines = head.decode('ascii').split('\r\n')
            method, target, version = lines[0].split(' ')
            if method != 'GET' or version not in ('HTTP/1.0', 'HTTP/1.1') or len(target) > 4096:
                raise ValueError
            # Reject proxy-form URLs, fragments, malformed escapes and invalid UTF-8.
            if not target.startswith('/oauth/callback?') or '#' in target or re.search(r'%(?![0-9a-fA-F]{2})', target):
                raise ValueError
            hosts = [line.split(':',1)[1].strip() for line in lines[1:] if line.lower().startswith('host:')]
            if hosts != [self.uri.netloc]:raise ValueError
            parsed = urlsplit(target)
            if parsed.path != '/oauth/callback' or parsed.netloc or parsed.scheme:
                raise ValueError
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True,
                              encoding='utf-8', errors='strict', max_num_fields=4)
            values = dict(pairs)
            if (len(pairs) != len(values) or set(values) - {'code','state','iss','error'}
                    or any(not v or len(v) > 2048 or any(ord(c) < 33 or ord(c) > 126 for c in v) for v in values.values())):
                raise ValueError
            if self.used or self.result.done():
                status = 409
            elif 'error' in values and set(values) <= {'error','state','iss'}:
                self.used = True
                self.result.set_exception(HTTPTransportError('oauth_authorization_denied'))
                status = 200
            elif {'code','state'} <= values.keys() and 'error' not in values:
                value = AuthorizationCodeResult(**values)
                self.used = True
                self.result.set_result(value)
                status = 200
        except asyncio.CancelledError:
            status = None
            raise
        except (ValueError, UnicodeError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            pass
        finally:
            body = b'Authorization callback received. Return to the terminal.' if status == 200 else b'Callback rejected.'
            try:
                if status is not None:writer.write(f'HTTP/1.1 {status} Callback\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\nPragma: no-cache\r\nReferrer-Policy: no-referrer\r\nContent-Security-Policy: default-src \'none\'\r\nConnection: close\r\nContent-Length: {len(body)}\r\n\r\n'.encode() + body)
                await writer.drain()
            except (ConnectionError, OSError):
                pass
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self.handlers.discard(task)

    async def wait(self):
        try:
            return await asyncio.wait_for(asyncio.shield(self.result), CALLBACK_TIMEOUT)
        except TimeoutError:
            raise HTTPTransportError('oauth_callback_timeout') from None
        finally:
            await self.close()

    async def close(self):
        server, self.server = self.server, None
        if server is not None:server.close()
        tasks = list(self.handlers)
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks, return_exceptions=True)
        if server is not None:await server.wait_closed()
        if self.result is not None:
            if not self.result.done():self.result.cancel()
            elif not self.result.cancelled():self.result.exception()  # consume a rejected callback on cleanup


async def open_authorization(url):
    # Show only trusted endpoint/client/scopes: generated state is never printed.
    if not sys.stdin.isatty():
        raise HTTPTransportError('oauth_interaction_required')
    parsed = urlsplit(url)
    values = dict(parse_qsl(parsed.query))
    print(f'OAuth 授权服务器：{parsed.scheme}://{parsed.netloc}{parsed.path}')
    print(f'Client：{values.get("client_id", "")}；Scope：{values.get("scope", "")}')
    print('输入 yes 后打开浏览器授权：', end='', flush=True)
    # add_reader avoids an uninterruptible input thread on EOF/Ctrl-C/timeout.
    loop = asyncio.get_running_loop()
    line = loop.create_future()
    try:
        loop.add_reader(sys.stdin.fileno(), lambda: line.done() or line.set_result(sys.stdin.readline()))
        answer = await asyncio.wait_for(line, CALLBACK_TIMEOUT)
        if answer.strip() != 'yes':raise HTTPTransportError('oauth_authorization_denied')
        if not webbrowser.open(url):raise HTTPTransportError('oauth_browser_failed')
    except TimeoutError:
        raise HTTPTransportError('oauth_callback_timeout') from None
    finally:
        loop.remove_reader(sys.stdin.fileno())
