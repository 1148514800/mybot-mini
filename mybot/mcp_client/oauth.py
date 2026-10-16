"""Constrain the official SDK flow; PKCE, state, exchange and refresh stay in SDK."""
import json
from urllib.parse import parse_qs, urlsplit

import httpx2
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.exceptions import OAuthFlowError
from mcp.client.auth.utils import (build_protected_resource_metadata_discovery_urls,
                                   build_oauth_authorization_server_metadata_discovery_urls)
from mcp.shared.auth import OAuthClientMetadata, OAuthClientInformationFull

from .config import validate_http_url
from .credentials import BEARER_TOKEN, MAX_TOKEN_BYTES, Credential
from .errors import HTTPTransportError
from .oauth_callback import OAuthCallback, open_authorization
from .transport import HTTPBoundary


def same_url(a, b):
    return isinstance(a, str) and httpx2.URL(a) == httpx2.URL(b)


def origin(url):
    value = urlsplit(url)
    return value.scheme, value.hostname, value.port or (443 if value.scheme == 'https' else 80)


class MemoryTokenStorage:
    def __init__(self, auth):
        self._tokens = None
        self._client = OAuthClientInformationFull(client_id=auth['client_id'], issuer=auth['issuer'],
            redirect_uris=[auth['redirect_uri']], token_endpoint_auth_method='none', scope=auth['scope'])
        self._auth = auth

    async def get_tokens(self):return self._tokens
    async def get_client_info(self):return self._client

    async def set_client_info(self, client_info):
        if (client_info.client_id != self._auth['client_id'] or client_info.client_secret is not None
                or not same_url(client_info.issuer, self._auth['issuer'])
                or client_info.token_endpoint_auth_method != 'none'):
            raise HTTPTransportError('oauth_client_refused')
        self._client = client_info

    async def set_tokens(self, tokens):
        if (not BEARER_TOKEN.fullmatch(tokens.access_token) or len(tokens.access_token) > MAX_TOKEN_BYTES
                or tokens.token_type != 'Bearer' or tokens.expires_in is None or tokens.expires_in <= 0
                or (tokens.scope is not None and not set(tokens.scope.split()) <= set(self._auth['scope'].split()))
                or (tokens.refresh_token is not None and (not 1 <= len(tokens.refresh_token) <= 8192
                    or any(ord(c) < 33 or ord(c) > 126 for c in tokens.refresh_token)))):
            raise HTTPTransportError('oauth_token_refused')
        self._tokens = tokens

    def clear(self):
        self._tokens = self._client = None


class OAuthBoundary(HTTPBoundary):
    def __init__(self, url, auth):
        super().__init__(url)
        self.auth = auth
        self.storage = MemoryTokenStorage(auth)
        self.callback = None
        self.provider = None
        self.resource_metadata = {httpx2.URL(u) for u in build_protected_resource_metadata_discovery_urls(None, url)}
        self.server_metadata = {httpx2.URL(u) for u in build_oauth_authorization_server_metadata_discovery_urls(auth['issuer'], url)}
        self.resource_verified = False
        self.authorization_endpoint = self.token_endpoint = None
        self.initialized = False

    def target_kind(self, request):
        if request.url == self.endpoint:return 'resource'
        if request.method == 'GET' and request.url in self.resource_metadata:return 'resource_metadata'
        if request.method == 'GET' and request.url in self.server_metadata and self.resource_verified:return 'server_metadata'
        if request.method == 'POST' and self.token_endpoint and request.url == self.token_endpoint:return 'token'
        if request.method == 'POST':raise HTTPTransportError('oauth_registration_refused')
        raise HTTPTransportError('oauth_target_refused')

    async def request(self, request):
        kind = self.target_kind(request)
        if kind == 'resource':
            await super().request(request)
            current = self.provider.context.current_tokens
            # SDK assigns context tokens before calling storage validation. Only
            # a snapshot accepted by this server's storage may reach the wire.
            if current is not None and current is not await self.storage.get_tokens():
                raise HTTPTransportError('oauth_token_refused')
            if current is not None:Credential(current.access_token).apply(request.headers)
        else:
            for key in ('authorization','proxy-authorization','cookie','mcp-session-id'):
                request.headers.pop(key, None)
            request.headers['Accept-Encoding'] = 'identity'

    async def response(self, response):
        if 300 <= response.status_code < 400:raise HTTPTransportError('http_redirect_refused')
        kind = self.target_kind(response.request)
        media = response.headers.get('content-type', '').split(';',1)[0].strip().lower()
        if media == 'text/event-stream' and (kind != 'resource' or response.status_code == 401):
            raise HTTPTransportError('oauth_response_type_refused')
        if kind == 'resource':
            if (response.status_code == 401 and response.request.extensions.get('oauth_bootstrap')
                    and not self.initialized):
                return
            await super().response(response)
        elif kind == 'token' and response.status_code not in (200,201):
            data = parse_qs(response.request.content.decode('ascii'))
            raise HTTPTransportError('oauth_refresh_failed' if data.get('grant_type') == ['refresh_token'] else 'oauth_token_exchange_failed')

    async def inspect_request(self, request, original, sends):
        kind = self.target_kind(request)
        if kind == 'resource':
            if request is not original:raise HTTPTransportError('oauth_resource_replay_refused')
            body = json.loads(request.content) if request.method == 'POST' else {}
            initialize = body.get('method') == 'initialize' and not self.initialized
            if sends > (2 if initialize else 1):raise HTTPTransportError('oauth_resource_replay_refused')
            if not self.provider.context.is_token_valid() and not (initialize and sends == 1):
                raise HTTPTransportError('oauth_login_required')
            request.extensions['oauth_bootstrap'] = initialize and sends == 1
        elif kind == 'token':
            if not self.authorization_endpoint:raise HTTPTransportError('oauth_metadata_required')
            params = parse_qs(request.content.decode('ascii'), strict_parsing=True)
            grant = params.get('grant_type')
            allowed = {'grant_type','client_id','resource'} | ({'code','code_verifier','redirect_uri'} if grant == ['authorization_code'] else {'refresh_token'})
            if (set(params) != allowed or any(len(v) != 1 for v in params.values())
                    or params.get('client_id') != [self.auth['client_id']]
                    or params.get('resource') != [str(self.endpoint)]
                    or grant not in (['authorization_code'], ['refresh_token'])):
                raise HTTPTransportError('oauth_token_request_refused')

    async def inspect_response(self, response):
        kind = self.target_kind(response.request)
        if kind == 'resource':
            body = json.loads(response.request.content) if response.request.method == 'POST' else {}
            if response.status_code < 300 and body.get('method') == 'initialize':self.initialized = True
            return
        if response.status_code == 404 and kind in ('resource_metadata','server_metadata'):return
        if response.status_code != 200:raise HTTPTransportError('oauth_metadata_failed')
        # ResponseLimitTransport is below this read; no unbounded JSON decode.
        document = json.loads(await response.aread())
        if kind == 'resource_metadata':
            if (not same_url(document.get('resource'), str(self.endpoint))
                    or not isinstance(document.get('authorization_servers'), list)
                    or len(document['authorization_servers']) != 1
                    or not same_url(document['authorization_servers'][0], self.auth['issuer'])):
                raise HTTPTransportError('oauth_resource_metadata_refused')
            self.resource_verified = True
        elif kind == 'server_metadata':
            if not same_url(document.get('issuer'), self.auth['issuer']):
                raise HTTPTransportError('oauth_issuer_refused')
            if 'S256' not in document.get('code_challenge_methods_supported', []):
                raise HTTPTransportError('oauth_s256_required')
            for key in ('authorization_endpoint','token_endpoint'):
                value = document.get(key)
                validate_http_url(value)
                if origin(value) != origin(self.auth['issuer']):raise HTTPTransportError('oauth_endpoint_refused')
            self.authorization_endpoint = httpx2.URL(document['authorization_endpoint'])
            self.token_endpoint = httpx2.URL(document['token_endpoint'])
            registration = document.get('registration_endpoint')
            if (self.authorization_endpoint == self.token_endpoint
                    or registration is not None and any(same_url(registration,str(endpoint)) for endpoint in (self.authorization_endpoint,self.token_endpoint))):
                raise HTTPTransportError('oauth_endpoint_refused')
        # Token response parsing/validation/storage remains the SDK's responsibility.

    async def redirect(self, url):
        parsed = httpx2.URL(url)
        params = parse_qs(urlsplit(url).query, strict_parsing=True)
        if (parsed.copy_with(query=None) != self.authorization_endpoint
                or any(len(v) != 1 for v in params.values())
                or params.get('resource') != [str(self.endpoint)]
                or params.get('client_id') != [self.auth['client_id']]
                or params.get('redirect_uri') != [self.auth['redirect_uri']]
                or params.get('code_challenge_method') != ['S256']
                or set(params.get('scope',[''])[0].split()) != set(self.auth['scope'].split())):
            raise HTTPTransportError('oauth_authorization_request_refused')
        self.callback = OAuthCallback(self.auth['redirect_uri'])
        await self.callback.start()  # Must bind before showing/launching authorization.
        await open_authorization(url)

    async def receive_callback(self):return await self.callback.wait()

    async def close(self):
        try:
            if self.callback:await self.callback.close()
        finally:
            self.storage.clear()
            if self.provider:
                self.provider.context.clear_tokens()
                self.provider.context.client_info = None


class GuardedOAuth(httpx2.Auth):
    """Drive, inspect and constrain the unmodified SDK async generator."""
    def __init__(self, boundary):
        self.boundary = boundary
        auth = boundary.auth
        self.sdk = OAuthClientProvider(str(boundary.endpoint),
            OAuthClientMetadata(redirect_uris=[auth['redirect_uri']], scope=auth['scope'],
                                token_endpoint_auth_method='none'), boundary.storage,
            redirect_handler=boundary.redirect, callback_handler=boundary.receive_callback)
        boundary.provider = self.sdk

    async def async_auth_flow(self, request):
        # SDK holds its OAuth lock across a resource response. On cancellation,
        # Streamable HTTP sends DELETE before cancelling that in-flight POST.
        # A cleanup DELETE must not wait for the POST's lock/timeout or log in.
        if request.method == 'DELETE' and request.url == self.boundary.endpoint and self.sdk.context.lock.locked():
            if not self.sdk.context.is_token_valid():raise HTTPTransportError('oauth_login_required')
            response = yield request
            await self.boundary.inspect_response(response)
            return
        flow = self.sdk.async_auth_flow(request)
        sends = 0
        try:
            outgoing = await flow.__anext__()
            while True:
                if outgoing.url == self.boundary.endpoint:sends += 1
                await self.boundary.inspect_request(outgoing, request, sends)
                response = yield outgoing
                await self.boundary.inspect_response(response)
                outgoing = await flow.asend(response)
        except StopAsyncIteration:
            return
        except HTTPTransportError:
            raise
        except Exception:
            # SDK exceptions may embed state, response JSON or a token. Never propagate text.
            raise HTTPTransportError('oauth_flow_failed') from None
        finally:
            await flow.aclose()
