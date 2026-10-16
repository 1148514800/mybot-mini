"""SDK transports with locally configured targets, explicit HTTP policy and quiet wire logs."""
from contextlib import asynccontextmanager, contextmanager
import logging

import httpx2
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from ..config import PROJECT_DIR
from .credentials import load_credential
from .errors import HTTPTransportError
from .response_limit import ResponseLimitTransport


@contextmanager
def quiet_wire_logs():
    # Imported SDK/network loggers can include URLs, headers and full JSON-RPC.
    prefixes = ('mcp.', 'httpx2', 'httpcore')
    loggers = [obj for name,obj in list(logging.Logger.manager.loggerDict.items())
               if name.startswith(prefixes) and isinstance(obj,logging.Logger)]
    states = [(obj,obj.disabled) for obj in loggers]
    for obj,_ in states:obj.disabled = True
    try:
        yield
    finally:
        for obj,disabled in states:obj.disabled = disabled


class HTTPBoundary:
    def __init__(self, url, credential=None):
        self.endpoint = httpx2.URL(url)
        self.get_started = False
        self.credential = credential

    async def request(self, request):
        if request.url != self.endpoint:
            raise HTTPTransportError('http_target_refused')
        # No automatic GET reconnect/resumption, even if the SDK attempts it.
        if request.method == 'GET':
            if self.get_started or 'last-event-id' in request.headers:
                raise HTTPTransportError('http_resume_refused')
            self.get_started = True
        for key in ('authorization','proxy-authorization','cookie'):
            request.headers.pop(key,None)
        request.headers['Accept-Encoding'] = 'identity'
        if self.credential is not None:
            self.credential.apply(request.headers)

    async def response(self, response):
        if 300 <= response.status_code < 400:
            raise HTTPTransportError('http_redirect_refused')
        if response.status_code in (401,403) or (response.status_code >= 400 and response.request.method == 'POST'):
            raise HTTPTransportError(f'http_{response.status_code}' if response.status_code in (401,403,404,405) else 'http_server_error' if response.status_code >= 500 else 'http_request_rejected')


@asynccontextmanager
async def connect_transport(config, *, errlog):
    if config.get('transport','stdio') == 'stdio':
        parameters = StdioServerParameters(command=config['command'],args=config.get('args',[]),cwd=PROJECT_DIR)
        async with stdio_client(parameters,errlog=errlog) as streams:
            yield streams
        return
    auth_config = config.get('auth', {'type':'none'})
    oauth = None
    if auth_config['type'] == 'oauth_pkce':
        from .oauth import OAuthBoundary, GuardedOAuth
        boundary = OAuthBoundary(config['url'], auth_config)
        oauth = GuardedOAuth(boundary)
    else:
        credential = load_credential(auth_config)
        boundary = HTTPBoundary(config['url'],credential)
    timeout = config.get('timeout_seconds',10)
    http = httpx2.AsyncClient(trust_env=False,auth=oauth,follow_redirects=False,
            timeout=httpx2.Timeout(timeout),transport=ResponseLimitTransport(httpx2.AsyncHTTPTransport(trust_env=False,retries=0)),
            event_hooks={'request':[boundary.request],'response':[boundary.response]})
    try:
        with quiet_wire_logs():
            async with http:
                async with streamable_http_client(config['url'],http_client=http,terminate_on_close=True) as streams:
                    yield streams
    finally:
        if oauth is not None:
            await boundary.close()
