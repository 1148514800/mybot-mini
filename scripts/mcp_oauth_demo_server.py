"""Loopback-only teaching AS + MCP resource; NOT a production identity service."""
import argparse
import asyncio
import base64
import hashlib
import hmac
import html
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlencode

from scripts.mcp_http_demo_server import create_app

SCOPES = 'notes:read notes:write'
CLIENT_ID = 'mybot-mini-local'


async def reply(send, status, document, headers=()):
    body = json.dumps(document).encode()
    await send({'type':'http.response.start','status':status,
                'headers':[(b'content-type',b'application/json'),(b'cache-control',b'no-store'),*headers]})
    await send({'type':'http.response.body','body':body})


async def read_body(receive):
    body = bytearray()
    while True:
        message = await receive()
        if message['type'] != 'http.request':raise ValueError
        body.extend(message.get('body', b''))
        if len(body) > 8192:raise ValueError
        if not message.get('more_body'):return bytes(body)


class DemoOAuth:
    def __init__(self, resource, issuer, redirect, lifetime=30, observer=None):
        self.resource, self.issuer, self.redirect = resource, issuer, redirect
        self.lifetime = lifetime
        self.codes, self.access, self.refresh = {}, {}, {}
        self.observer = observer or (lambda event: None)

    def event(self, event, **fields):self.observer({'event':event, **fields})

    def mint(self, scope):
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        record = {'resource':self.resource,'scope':scope,'expires':time.monotonic()+self.lifetime}
        self.access[access] = record
        self.refresh[refresh] = {'resource':self.resource,'scope':scope}
        return {'access_token':access,'refresh_token':refresh,'token_type':'Bearer',
                'expires_in':self.lifetime,'scope':scope}

    def authorize_params(self, params):
        required = {'response_type','client_id','redirect_uri','resource','scope','state','code_challenge','code_challenge_method'}
        return (set(params) == required and params['response_type'] == 'code'
                and params['client_id'] == CLIENT_ID and params['redirect_uri'] == self.redirect
                and params['resource'] == self.resource and set(params['scope'].split()) <= set(SCOPES.split())
                and params['scope'] and params['code_challenge_method'] == 'S256'
                and re.fullmatch(r'[A-Za-z0-9_-]{43}', params['code_challenge'])
                and re.fullmatch(r'[A-Za-z0-9_-]{16,128}', params['state']))

    async def authorization_server(self, scope, receive, send):
        if scope['type'] != 'http':return
        path, method = scope['path'], scope['method']
        if path == '/health':return await reply(send,200,{'ready':True})
        self.event('as_request', path=path, method=method,
                   identity_header=any(k in (b'authorization',b'cookie',b'proxy-authorization') for k,v in scope['headers']))
        if path in ('/.well-known/oauth-authorization-server','/.well-known/openid-configuration') and method == 'GET':
            return await reply(send,200,{'issuer':self.issuer,'authorization_endpoint':self.issuer+'/authorize',
                'token_endpoint':self.issuer+'/token','registration_endpoint':self.issuer+'/register',
                'response_types_supported':['code'],'grant_types_supported':['authorization_code','refresh_token'],
                'token_endpoint_auth_methods_supported':['none'],'scopes_supported':SCOPES.split(),
                'code_challenge_methods_supported':['S256'],'authorization_response_iss_parameter_supported':True})
        try:
            raw = scope['query_string'] if method == 'GET' else await read_body(receive)
            values = parse_qs(raw.decode('ascii'), strict_parsing=True)
            if any(len(v) != 1 for v in values.values()):raise ValueError
            params = {k:v[0] for k,v in values.items()}
        except (ValueError, UnicodeError):return await reply(send,400,{'error':'invalid_request'})
        if path == '/authorize' and method in ('GET','POST'):
            approved = params.pop('approve', None)
            if not self.authorize_params(params):return await reply(send,400,{'error':'invalid_request'})
            if method == 'GET':
                inputs=''.join(f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v,quote=True)}">' for k,v in params.items())
                body=('<!doctype html><title>Local OAuth teaching consent</title><h1>Local test user</h1>'
                      f'<p>Client: {html.escape(CLIENT_ID)}; scope: {html.escape(params["scope"])}</p>'
                      f'<form method="post" action="/authorize">{inputs}<button name="approve" value="yes">Authorize</button></form>').encode()
                await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'text/html; charset=utf-8'),(b'cache-control',b'no-store'),(b'referrer-policy',b'no-referrer')]})
                return await send({'type':'http.response.body','body':body})
            if approved != 'yes':return await reply(send,403,{'error':'access_denied'})
            code = secrets.token_urlsafe(32)
            self.codes[code] = {'challenge':params['code_challenge'],'scope':params['scope'],'expires':time.monotonic()+60}
            self.event('authorize', s256=True, resource=True, scope=params['scope'])
            location=self.redirect+'?'+urlencode({'code':code,'state':params['state'],'iss':self.issuer})
            return await reply(send,302,{'authorized':True},[(b'location',location.encode())])
        if path == '/token' and method == 'POST':
            grant=params.get('grant_type')
            valid=params.get('client_id') == CLIENT_ID and params.get('resource') == self.resource
            if grant == 'authorization_code':
                record=self.codes.pop(params.get('code'),None)
                verifier=params.get('code_verifier','')
                challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
                pkce=bool(record and hmac.compare_digest(challenge,record['challenge']))
                valid=valid and pkce and record['expires']>time.monotonic() and params.get('redirect_uri')==self.redirect
                self.event('exchange', pkce=pkce, resource=params.get('resource')==self.resource, success=bool(valid))
            elif grant == 'refresh_token':
                record=self.refresh.pop(params.get('refresh_token'),None)
                valid=valid and bool(record) and record['resource']==self.resource
                self.event('refresh', resource=params.get('resource')==self.resource, success=bool(valid))
            else:return await reply(send,400,{'error':'unsupported_grant_type'})
            if not valid:return await reply(send,400,{'error':'invalid_grant'})
            return await reply(send,200,self.mint(record['scope']))
        return await reply(send,404,{'error':'not_found'})

    def resource_app(self, port, *, json_response=True):
        app = create_app(port,json_response=json_response)
        async def protected(scope, receive, send):
            if scope['type'] != 'http':return await app(scope,receive,send)
            path=scope['path']
            if path == '/health':return await reply(send,200,{'ready':True})
            if path in ('/.well-known/oauth-protected-resource/mcp','/.well-known/oauth-protected-resource'):
                self.event('resource_metadata')
                return await reply(send,200,{'resource':self.resource,'authorization_servers':[self.issuer],
                                             'scopes_supported':SCOPES.split(),'bearer_methods_supported':['header']})
            headers=dict(scope['headers'])
            token=headers.get(b'authorization',b'').decode('latin1').removeprefix('Bearer ')
            record=self.access.get(token)
            valid=bool(record and record['resource']==self.resource and record['expires']>time.monotonic())
            body=await read_body(receive)
            try:data=json.loads(body)
            except ValueError:data={}
            name=data.get('params',{}).get('name')
            self.event('resource', method=scope['method'], rpc=data.get('method'), name=name,
                       authenticated=valid, has_auth=bool(headers.get(b'authorization')), refresh_used=token in self.refresh)
            if not valid:
                challenge=f'Bearer resource_metadata="{self.resource.rsplit("/",1)[0]}/.well-known/oauth-protected-resource/mcp", scope="{SCOPES}"'
                return await reply(send,401,{'error':'invalid_token'},[(b'www-authenticate',challenge.encode())])
            required='notes:write' if name in ('save_note','delete_note') else 'notes:read'
            if name and required not in record['scope'].split():
                return await reply(send,403,{'error':'insufficient_scope'},[(b'www-authenticate',b'Bearer error="insufficient_scope", scope="notes:write"')])
            sent=False
            async def replay():
                nonlocal sent
                if not sent:sent=True;return {'type':'http.request','body':body,'more_body':False}
                return await receive()
            return await app(scope,replay,send)
        return protected


def create_apps(resource_port, issuer_port, redirect_uri, *, lifetime=30, observer=None, json_response=True):
    state=DemoOAuth(f'http://127.0.0.1:{resource_port}/mcp',f'http://127.0.0.1:{issuer_port}',redirect_uri,lifetime,observer)
    return state.resource_app(resource_port,json_response=json_response),state.authorization_server


def main():
    import uvicorn
    from mybot.mcp_client.oauth_config import validate_oauth
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-port',type=int,default=8765)
    parser.add_argument('--issuer-port',type=int,default=8766)
    parser.add_argument('--callback-port',type=int,default=43117)
    args=parser.parse_args()
    if len({args.resource_port,args.issuer_port,args.callback_port}) != 3 or any(not 1<=p<=65535 for p in (args.resource_port,args.issuer_port,args.callback_port)):
        parser.error('three distinct valid ports are required')
    redirect=f'http://127.0.0.1:{args.callback_port}/oauth/callback'
    validate_oauth({'type':'oauth_pkce','issuer':f'http://127.0.0.1:{args.issuer_port}',
                    'client_id':CLIENT_ID,'scope':SCOPES,'redirect_uri':redirect})
    resource,issuer=create_apps(args.resource_port,args.issuer_port,redirect)
    async def run():
        servers=[uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False,interface='asgi3'))
                 for app,port in ((resource,args.resource_port),(issuer,args.issuer_port))]
        await asyncio.gather(*(server.serve() for server in servers))
    asyncio.run(run())


if __name__=='__main__':main()
