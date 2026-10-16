"""Offline, real SDK + two HTTP servers + simulated consenting browser. No model API."""
import asyncio
import contextlib
import io
import json
import logging
import os
import socket
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit

import httpx2
from mybot.agent import AgentLoop, ContextBuilder
from mybot.config import PROJECT_DIR
from mybot.mcp_client.config import validate_mcp
from mybot.mcp_client.manager import MCPClientManager, MCPStartupError
from mybot.mcp_client.oauth import MemoryTokenStorage, OAuthBoundary, GuardedOAuth
from mybot.mcp_client.oauth_callback import OAuthCallback, open_authorization
from mybot.mcp_client.errors import HTTPTransportError
from mybot.tools import build_default_tool_registry
from scripts.check_mcp import MCPChecks
from scripts.check_mcp_http import HTTPChecks, approve, deny
from scripts.check_session import call, response, assert_pairs
from scripts.mcp_oauth_demo_server import CLIENT_ID, SCOPES

FIXTURE = r'''
import asyncio,json,socket,sys
from pathlib import Path
import uvicorn
from scripts.mcp_oauth_demo_server import DemoOAuth,reply,read_body
resource_fd,issuer_fd,rp,ip,cp=map(int,sys.argv[1:6]);mode=sys.argv[6];trace=Path(sys.argv[7])
def event(value):
    with trace.open('a') as file:file.write(json.dumps(value)+'\n')
state=DemoOAuth(f'http://127.0.0.1:{rp}/mcp',f'http://127.0.0.1:{ip}',f'http://127.0.0.1:{cp}/oauth/callback',
    lifetime=1 if mode in ('expiry','bad-refresh','refresh-expanded','no-refresh') else 60,observer=event)
resource,issuer=state.resource_app(rp,json_response=mode!='sse'),state.authorization_server
def wrap(app,kind):
    async def wrapped(scope,receive,send):
        if scope['type']!='http':return await app(scope,receive,send)
        path=scope['path']
        if path=='/health':return await app(scope,receive,send)
        if mode=='metadata-sse' and path.startswith('/.well-known'):
            await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'text/event-stream')]})
            return await send({'type':'http.response.body','body':b'data: {}\n\n'})
        if mode=='redirect' and path=='/mcp':return await reply(send,307,{},[(b'location',b'http://127.0.0.1:1/elsewhere')])
        if mode=='extra-scope' and path=='/mcp' and not dict(scope['headers']).get(b'authorization'):
            return await reply(send,401,{},[(b'www-authenticate',f'Bearer resource_metadata="http://127.0.0.1:{rp}/.well-known/oauth-protected-resource/mcp", scope="admin:all"'.encode())])
        if mode=='unknown-discovery' and path=='/mcp':return await reply(send,401,{},[(b'www-authenticate',b'Bearer resource_metadata="http://127.0.0.1:1/evil"')])
        body=await read_body(receive)
        try:rpc=json.loads(body)
        except ValueError:rpc={}
        params=__import__('urllib.parse',fromlist=['parse_qs']).parse_qs(body.decode('ascii',errors='replace'))
        name=rpc.get('params',{}).get('name')
        if mode=='hang-save' and name=='save_note':
            event({'event':'hang-save'});await asyncio.sleep(10)
        if mode in ('bad-refresh','refresh-expanded') and path=='/token' and params.get('grant_type')==['refresh_token'] and mode=='bad-refresh':
            event({'event':'refresh','success':False});return await reply(send,400,{'error':'invalid_grant'})
        sent=False
        async def replay():
            nonlocal sent
            if not sent:sent=True;return {'type':'http.request','body':body,'more_body':False}
            return await receive()
        # Inject effects-then-auth-failure into a real SDK tool call; never duplicate it.
        if (mode=='save-401' and name=='save_note') or (mode=='delete-403' and name=='delete_note'):
            buffered=[]
            async def buffer(message):buffered.append(message)
            await app(scope,replay,buffer)
            status=401 if mode=='save-401' else 403
            return await reply(send,status,{'error':'synthetic'},[(b'www-authenticate',b'Bearer error="insufficient_scope", scope="admin:all"')])
        pending=[]
        mutate=(path.startswith('/.well-known') or path=='/token') and mode in ('bad-issuer','bad-resource','bad-as','bad-endpoint','no-s256','large-metadata','large-token','compressed-metadata','refresh-expanded','bad-audience','extra-scope','no-scope','no-refresh')
        if not mutate:return await app(scope,replay,send)
        async def collect(message):pending.append(message)
        await app(scope,replay,collect)
        start=pending[0];raw=b''.join(m.get('body',b'') for m in pending[1:]);doc=json.loads(raw)
        if 'resource' in doc and mode=='bad-resource':doc['resource']=f'http://127.0.0.1:{rp}/other'
        if 'authorization_servers' in doc and mode=='bad-as':doc['authorization_servers']=['http://127.0.0.1:1']
        if 'issuer' in doc and mode=='bad-issuer':doc['issuer']='http://127.0.0.1:1'
        if 'token_endpoint' in doc and mode=='bad-endpoint':doc['token_endpoint']='http://127.0.0.1:1/token'
        if 'code_challenge_methods_supported' in doc and mode=='no-s256':doc['code_challenge_methods_supported']=['plain']
        if 'scopes_supported' in doc and mode=='extra-scope':doc['scopes_supported']=['admin:all']
        if mode=='no-scope':doc.pop('scopes_supported',None)
        if mode=='no-refresh' and path=='/token':doc.pop('refresh_token',None)
        if mode=='refresh-expanded' and path=='/token' and params.get('grant_type')==['refresh_token']:doc['scope']='admin:all'
        if mode=='bad-audience' and path=='/token':state.access[doc['access_token']]['resource']=f'http://127.0.0.1:{rp}/other'
        if mode=='large-metadata' and path.startswith('/.well-known'):doc['padding']='X'*(3*1024*1024)
        if mode=='large-token' and path=='/token':doc['padding']='X'*(3*1024*1024)
        headers=[]
        if mode=='compressed-metadata':headers=[(b'content-encoding',b'gzip')]
        return await reply(send,start['status'],doc,headers)
    return wrapped
async def main():
    servers=[uvicorn.Server(uvicorn.Config(wrap(app,kind),log_level='critical',access_log=False)) for app,kind in ((resource,'resource'),(issuer,'issuer'))]
    await asyncio.gather(*(server.serve(sockets=[socket.socket(fileno=fd)]) for server,fd in zip(servers,(resource_fd,issuer_fd))))
asyncio.run(main())
'''


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


class OAuthChecks(unittest.IsolatedAsyncioTestCase):
    setUp = MCPChecks.setUp
    asyncSetUp = HTTPChecks.asyncSetUp
    stop_servers = HTTPChecks.stop_servers
    manager = HTTPChecks.manager
    read = HTTPChecks.read

    async def start(self, mode='normal'):
        self.trace=self.root/f'oauth-{len(self.processes)}.jsonl'
        fixture=self.root/'oauth_fixture.py';fixture.write_text(FIXTURE)
        with socket.socket() as resource, socket.socket() as issuer, socket.socket() as callback:
            for sock in (resource,issuer,callback):sock.bind(('127.0.0.1',0))
            rp,ip,cp=(s.getsockname()[1] for s in (resource,issuer,callback))
            command=[sys.executable,str(fixture),str(resource.fileno()),str(issuer.fileno()),str(rp),str(ip),str(cp),mode,str(self.trace)]
            self.process=subprocess.Popen(command,pass_fds=(resource.fileno(),issuer.fileno()),cwd=PROJECT_DIR,
                env={**os.environ,'PYTHONPATH':str(PROJECT_DIR)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.processes.append(self.process)
        self.url=f'http://127.0.0.1:{rp}/mcp';self.issuer=f'http://127.0.0.1:{ip}'
        self.trusted_resources=getattr(self,'trusted_resources',set())|{self.url}
        self.redirect=f'http://127.0.0.1:{cp}/oauth/callback'
        self.browser_count=0;self.browser_mode='normal';self.browser_secrets=[]
        self.browser_patch=patch('mybot.mcp_client.oauth.open_authorization',self.browser)
        self.browser_patch.start();self.addCleanup(self.browser_patch.stop)
        async with httpx2.AsyncClient(trust_env=False,timeout=.2) as http:
            for _ in range(200):
                if self.process.poll() is not None:self.fail('OAuth fixture exited')
                try:
                    if (await http.get(self.issuer+'/health')).status_code==200:break
                except httpx2.RequestError:pass
                await asyncio.sleep(.02)
            else:self.fail('OAuth fixture not ready')

    def cfg(self, allowed=None, **policies):
        cfg=HTTPChecks.cfg(self,allowed,**policies)
        cfg.mcp_servers['web']['auth']={'type':'oauth_pkce','issuer':self.issuer,'client_id':CLIENT_ID,'scope':SCOPES,'redirect_uri':self.redirect}
        return cfg

    def events(self):return [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []

    async def browser(self, url):
        self.browser_count+=1
        params=dict(parse_qsl(urlsplit(url).query))
        self.browser_secrets.append(params['state'])
        self.assertEqual(params['code_challenge_method'],'S256');self.assertIn(params['resource'],self.trusted_resources)
        parsed_url=urlsplit(url);issuer=f'{parsed_url.scheme}://{parsed_url.netloc}'
        redirect=params['redirect_uri']
        async with httpx2.AsyncClient(trust_env=False,follow_redirects=False) as http:
            self.assertEqual((await http.get(url)).status_code,200)
            result=await http.post(issuer+'/authorize',data=params|{'approve':'yes'})
            self.assertEqual(result.status_code,302)
            target=urlsplit(result.headers['location']);values=dict(parse_qsl(target.query))
            self.browser_secrets.append(values['code'])
            if self.browser_mode=='state':values['state']='wrong-state'
            if self.browser_mode=='iss':values['iss']='http://127.0.0.1:1'
            if self.browser_mode=='missing-iss':values.pop('iss')
            if self.browser_mode=='timeout':return
            result=await http.get(redirect+'?'+urlencode(values))
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.headers['cache-control'],'no-store')
            for value in values.values():self.assertNotIn(value,result.text)

    async def failure(self, kind=None, cfg=None):
        m=MCPClientManager(cfg or self.cfg(),self.tools)
        with self.assertRaises(MCPStartupError) as caught:
            async with m:pass
        if kind:self.assertIn(kind,str(caught.exception))
        self.assertTrue(m.closed);self.assertFalse(m.clients)
        self.assertFalse(self.tools.has_tool('mcp__web__add'))
        for secret in self.browser_secrets:self.assertNotIn(secret,str(caught.exception))
        return m

    async def test_01_existing_none_bearer_and_oauth_config(self):
        await self.start();server=self.cfg().mcp_servers['web']
        for auth in ({'type':'none'},{'type':'bearer_env','token_env':'MYBOT_TEST_MCP_TOKEN'},server['auth']):
            validate_mcp(True,{'web':server|{'auth':auth}})
        old=dict(server);old.pop('auth');validate_mcp(True,{'web':old})

    async def test_02_stdio_rejects_oauth(self):
        await self.start()
        with self.assertRaises(ValueError):validate_mcp(True,{'local':MCPChecks.demo(self)|{'auth':self.cfg().mcp_servers['web']['auth']}})

    async def test_03_invalid_client_and_fields(self):
        await self.start();server=self.cfg().mcp_servers['web'];auth=server['auth']
        for patch_value in ({'client_id':''},{'client_id':1},{'client_id':'bad\nclient'},{'issuer':'http://example.com'},
                {'issuer':'https://user:pass@example.com'},{'redirect_uri':'http://localhost:43117/oauth/callback'},
                {'redirect_uri':'http://127.0.0.1:43117/other'},{'redirect_uri':'https://example.com/oauth/callback'},
                {'redirect_uri':'http://127.0.0.1/oauth/callback'},{'scope':'notes:read notes:read'},
                {'client_secret':'synthetic'},{'access_token':'synthetic'},{'refresh_token':'synthetic'},{'code_verifier':'synthetic'}):
            with self.subTest(keys=list(patch_value)),self.assertRaises(ValueError):validate_mcp(True,{'web':server|{'auth':auth|patch_value}})

    async def test_04_metadata_issuer_mismatch(self):
        await self.start('bad-issuer');await self.failure('oauth_issuer_refused');self.assertEqual(self.browser_count,0)

    async def test_05_metadata_resource_mismatch(self):
        await self.start('bad-resource');await self.failure('oauth_resource_metadata_refused')

    async def test_06_metadata_authorization_server_mismatch(self):
        await self.start('bad-as');await self.failure('oauth_resource_metadata_refused')

    async def test_07_metadata_endpoint_other_origin(self):
        await self.start('bad-endpoint');await self.failure('oauth_endpoint_refused')

    async def test_08_s256_required(self):
        await self.start('no-s256');await self.failure('oauth_s256_required')

    async def test_09_no_dynamic_registration(self):
        await self.start()
        async with self.manager():pass
        self.assertFalse(any(e.get('path')=='/register' for e in self.events()))

    async def test_10_redirect_refused(self):
        await self.start('redirect');await self.failure('http_redirect_refused');self.assertEqual(self.browser_count,0)

    async def test_11_unknown_discovery_target_refused(self):
        await self.start('unknown-discovery');await self.failure('oauth_target_refused')

    async def test_12_full_sdk_pkce_resource_and_state(self):
        await self.start()
        async with self.manager() as m:
            self.assertTrue((await m.call('web','add',{'a':2,'b':3})).success)
        self.assertEqual(self.browser_count,1)
        events=self.events()
        exchange=next(e for e in events if e['event']=='exchange')
        self.assertTrue(exchange['pkce'] and exchange['resource'] and exchange['success'])
        self.assertEqual(sum(e['event']=='resource' and e['rpc']=='initialize' for e in events),2)
        self.assertTrue(any(e['event']=='resource_metadata' for e in events))
        self.assertTrue(any(e['event']=='resource' and e['method']=='DELETE' and e['authenticated'] for e in events))
        self.assertFalse(any(e.get('identity_header') for e in events));self.assertFalse(any(e.get('refresh_used') for e in events))

    async def test_13_wrong_state_sdk_rejects(self):
        await self.start();self.browser_mode='state';await self.failure('oauth_flow_failed')
        self.assertFalse(any(e['event']=='exchange' for e in self.events()))

    async def test_14_wrong_issuer_sdk_rejects(self):
        await self.start();self.browser_mode='iss';await self.failure('oauth_flow_failed')

    async def test_15_missing_required_iss_sdk_rejects(self):
        await self.start();self.browser_mode='missing-iss';await self.failure('oauth_flow_failed')

    async def test_16_expiry_refresh_and_rotation(self):
        await self.start('expiry')
        tokens=[];original=MemoryTokenStorage.set_tokens
        async def observe(storage,value):tokens.append(value.model_copy());await original(storage,value)
        with patch.object(MemoryTokenStorage,'set_tokens',observe):
            async with self.manager() as m:
                for _ in range(2):
                    await asyncio.sleep(1.1)
                    self.assertTrue((await m.call('web','add',{'a':1,'b':2})).success)
        self.assertEqual(self.browser_count,1)
        self.assertGreaterEqual(len(tokens),3)
        self.assertEqual(len({t.refresh_token for t in tokens}),len(tokens))
        # Actual AS rejects an already-rotated refresh token.
        async with httpx2.AsyncClient(trust_env=False) as http:
            result=await http.post(self.issuer+'/token',data={'grant_type':'refresh_token','client_id':CLIENT_ID,'resource':self.url,'refresh_token':tokens[0].refresh_token})
        self.assertEqual(result.status_code,400)

    async def test_17_invalid_refresh_no_reauth_or_tool_send(self):
        await self.start('bad-refresh')
        async with self.manager() as m:
            await asyncio.sleep(1.1)
            result=await m.call('web','add',{'a':1,'b':2})
            self.assertFalse(result.success);self.assertIn('oauth_refresh_failed',result.error)
        self.assertEqual(self.browser_count,1)
        self.assertFalse(any(e.get('rpc')=='tools/call' for e in self.events()))

    async def test_18_refresh_scope_expansion_refused(self):
        await self.start('refresh-expanded')
        async with self.manager() as m:
            await asyncio.sleep(1.1)
            result=await m.call('web','add',{'a':1,'b':2})
            self.assertFalse(result.success);self.assertIn('oauth_token_refused',result.error)
        self.assertEqual(self.browser_count,1)

    async def test_19_noninteractive_refuses_authorization(self):
        with patch('sys.stdin.isatty',return_value=False):
            with self.assertRaisesRegex(HTTPTransportError,'oauth_interaction_required'):
                await open_authorization('http://127.0.0.1/authorize')

    async def test_20_callback_timeout_releases_port(self):
        await self.start();self.browser_mode='timeout'
        with patch('mybot.mcp_client.oauth_callback.CALLBACK_TIMEOUT',.05):await self.failure('oauth_callback_timeout')
        with socket.socket() as sock:sock.bind(('127.0.0.1',urlsplit(self.redirect).port))

    async def test_21_callback_port_conflict_no_browser(self):
        await self.start()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',urlsplit(self.redirect).port));sock.listen()
            await self.failure('oauth_callback_bind_failed')
        self.assertEqual(self.browser_count,0)

    async def test_22_confirm_denied_has_no_effect(self):
        await self.start()
        async with self.manager(deny) as m:
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'denied'})).success)
            self.assertFalse((await self.read(m)).success)
        self.assertFalse(any(e.get('name')=='save_note' for e in self.events()))

    async def test_23_confirm_approved_has_real_effect(self):
        await self.start()
        async with self.manager(approve) as m:
            self.assertTrue((await m.call('web','save_note',{'key':'k','content':'approved'})).success)
            self.assertIn('approved',(await self.read(m)).output)

    async def test_24_deny_hidden_and_direct_refused(self):
        await self.start()
        async with self.manager(approve,save_note='deny') as m:
            self.assertFalse(self.tools.has_tool('mcp__web__save_note'))
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'denied'})).success)
        self.assertFalse(any(e.get('name')=='save_note' for e in self.events()))

    async def test_25_save_401_no_replay_or_login(self):
        await self.start('save-401')
        async with self.manager(approve) as m:
            result=await m.call('web','save_note',{'key':'k','content':'effect-before-401'})
            self.assertFalse(result.success);self.assertIn('http_401',result.error);self.assertIn('unknown',result.error)
        self.assertEqual(self.browser_count,1)
        self.assertEqual(sum(e.get('name')=='save_note' for e in self.events()),1)
        async with self.manager() as second:self.assertIn('effect-before-401',(await self.read(second)).output)

    async def test_26_delete_403_no_replay_or_stepup(self):
        await self.start('delete-403')
        async with self.manager(approve) as m:
            self.assertTrue((await m.call('web','save_note',{'key':'k','content':'remove'})).success)
            result=await m.call('web','delete_note',{'key':'k'})
            self.assertFalse(result.success);self.assertIn('http_403',result.error)
        self.assertEqual(self.browser_count,1);self.assertEqual(sum(e.get('name')=='delete_note' for e in self.events()),1)
        self.assertEqual(sum(e['event']=='authorize' for e in self.events()),1)
        async with self.manager() as second:self.assertFalse((await self.read(second)).success)

    async def test_27_sdk_scope_choice_cannot_expand_local_scope(self):
        await self.start('extra-scope');await self.failure('oauth_authorization_request_refused')
        self.assertEqual(self.browser_count,0)

    async def test_28_agent_pairs_plan_failure_and_clear(self):
        await self.start('save-401')
        effects=[response(calls=[call('p','create_plan','{"steps":["save","read"]}'),call('s','update_plan','{"step":1,"status":"in_progress"}'),call('w','mcp__web__save_note','{"key":"k","content":"x"}'),call('d','update_plan','{"step":1,"status":"completed"}')]),response('failed')]
        async def create(**kwargs):return effects.pop(0)
        async with self.manager(approve):
            agent=AgentLoop(N(chat=N(completions=N(create=create))),self.cfg(),self.tools,ContextBuilder(self.workspace))
            with contextlib.redirect_stdout(io.StringIO()):await agent.handle_message('save')
            assert_pairs(self,agent.session.history())
            self.assertFalse(agent.plan.steps[0].verified);self.assertEqual(agent.plan.steps[0].status,'failed')
            before=len(self.events());browsers=self.browser_count
            await agent.handle_message('/clear')
            self.assertEqual(agent.session.history(),[]);self.assertEqual(len(self.events()),before);self.assertEqual(self.browser_count,browsers)

    async def test_29_credentials_not_in_logs_model_session_schema_audit(self):
        await self.start();secrets=[];original=MemoryTokenStorage.set_tokens
        async def observe(storage,tokens):
            secrets.extend([tokens.access_token,tokens.refresh_token]);await original(storage,tokens)
        output=io.StringIO();handler=logging.StreamHandler(output);root=logging.getLogger();level=root.level
        root.addHandler(handler);root.setLevel(logging.DEBUG)
        self.addCleanup(root.removeHandler,handler);self.addCleanup(root.setLevel,level)
        requests=[];effects=[response(calls=[call('a','mcp__web__add','{"a":1,"b":2}')]),response('done')]
        async def create(**kwargs):requests.append(kwargs);return effects.pop(0)
        with patch.object(MemoryTokenStorage,'set_tokens',observe):
            async with self.manager() as m:
                cfg=replace(self.cfg(),session_persist=True,session_path=self.root/'state/session.json',debug=True)
                agent=AgentLoop(N(chat=N(completions=N(create=create))),cfg,self.tools,ContextBuilder(self.workspace))
                with contextlib.redirect_stdout(output):await agent.handle_message('add')
                for secret in secrets+self.browser_secrets:
                    for content in (output.getvalue(),json.dumps(requests),json.dumps(agent.session.history()),cfg.session_path.read_text(),json.dumps(m.audit),json.dumps(self.tools.get_definitions())):self.assertNotIn(secret,content)

    async def test_30_two_servers_have_independent_authorization(self):
        await self.start();first=self.cfg(['add']).mcp_servers['web'];first_trace=self.trace
        await self.start();cfg=self.cfg(['add']);cfg.mcp_servers['first']=first
        async with MCPClientManager(cfg,self.tools) as m:
            for server in ('first','web'):self.assertTrue((await m.call(server,'add',{'a':1,'b':2})).success)
        # Browser routes each URL to its own issuer, not the most recent fixture.
        for trace in (first_trace,self.trace):
            events=[json.loads(line) for line in trace.read_text().splitlines()]
            self.assertEqual(sum(e['event']=='exchange' for e in events),1)
            self.assertFalse(next(e for e in events if e['event']=='resource')['has_auth'])

    async def test_31_large_metadata_bounded(self):
        await self.start('large-metadata');await self.failure('http_response_too_large')

    async def test_32_large_token_response_bounded(self):
        await self.start('large-token');await self.failure('http_response_too_large')

    async def test_33_compressed_metadata_refused(self):
        await self.start('compressed-metadata');await self.failure('http_content_encoding_refused')

    async def test_34_sse_real_sdk_after_oauth(self):
        await self.start('sse')
        async with self.manager() as m:self.assertTrue((await m.call('web','echo',{'message':'sse'})).success)

    async def test_35_gateway_close_clears_memory_and_client(self):
        await self.start();boundaries=[];original=OAuthBoundary.__init__;clients=[];http_original=httpx2.AsyncClient
        def capture(boundary,*args):original(boundary,*args);boundaries.append(boundary)
        def client(**kwargs):value=http_original(**kwargs);clients.append(value);return value
        with patch.object(OAuthBoundary,'__init__',capture),patch('mybot.mcp_client.transport.httpx2.AsyncClient',side_effect=client):
            async with self.manager():pass
        self.assertTrue(all(c.is_closed for c in clients))
        for boundary in boundaries:
            self.assertIsNone(await boundary.storage.get_tokens());self.assertIsNone(await boundary.storage.get_client_info())
            self.assertIsNone(boundary.provider.context.current_tokens);self.assertIsNone(boundary.callback.server)
        self.assertIsNone(self.process.poll())

    async def test_36_cancel_callback_releases_listener(self):
        await self.start();self.browser_mode='timeout'
        async def run():
            async with self.manager():pass
        task=asyncio.create_task(run())
        for _ in range(200):
            if self.browser_count:break
            await asyncio.sleep(.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        with socket.socket() as sock:sock.bind(('127.0.0.1',urlsplit(self.redirect).port))

    async def test_37_cancel_tool_closes_manager(self):
        await self.start('hang-save')
        async def run():
            async with self.manager(approve) as m:
                self.active=m;await m.call('web','save_note',{'key':'k','content':'cancel'})
        task=asyncio.create_task(run())
        for _ in range(200):
            if any(e['event']=='hang-save' for e in self.events()):break
            await asyncio.sleep(.01)
        else:self.fail('tool did not reach server')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(self.active.closed);self.assertFalse(self.active.clients)

    async def test_38_proxy_and_netrc_not_inherited(self):
        await self.start();netrc=self.root/'netrc';netrc.write_text('machine 127.0.0.1 login SYNTHETIC_USER password SYNTHETIC_PASSWORD\n')
        with patch.dict(os.environ,{'NETRC':str(netrc),'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':''}):
            async with self.manager() as m:self.assertTrue((await m.call('web','add',{'a':1,'b':2})).success)
        self.assertFalse(any(e.get('identity_header') for e in self.events()))

    async def test_39_bad_audience_token_cannot_initialize(self):
        await self.start('bad-audience');await self.failure('http_401')
        self.assertEqual(self.browser_count,1)

    async def test_40_unknown_endpoint_and_registration_before_send(self):
        await self.start();boundary=OAuthBoundary(self.url,self.cfg().mcp_servers['web']['auth'])
        for method,url in (('GET',self.issuer+'/arbitrary'),('POST',self.issuer+'/register'),('POST','http://127.0.0.1:1/token')):
            with self.assertRaises(HTTPTransportError):await boundary.request(httpx2.Request(method,url))
        self.assertEqual(self.events(),[])

    async def demo_code(self):
        from mcp.client.auth.oauth2 import PKCEParameters
        pkce=PKCEParameters.generate()
        data={'response_type':'code','client_id':CLIENT_ID,'redirect_uri':self.redirect,'resource':self.url,
              'scope':SCOPES,'state':'synthetic-state-for-demo','code_challenge':pkce.code_challenge,'code_challenge_method':'S256','approve':'yes'}
        async with httpx2.AsyncClient(trust_env=False) as http:
            result=await http.post(self.issuer+'/authorize',data=data)
        self.assertEqual(result.status_code,302)
        code=dict(parse_qsl(urlsplit(result.headers['location']).query))['code']
        return {'grant_type':'authorization_code','client_id':CLIENT_ID,'redirect_uri':self.redirect,
                'resource':self.url,'code':code,'code_verifier':pkce.code_verifier}

    async def test_41_wrong_verifier_rejected_by_real_as(self):
        await self.start();data=await self.demo_code();data['code_verifier']='X'*43
        async with httpx2.AsyncClient(trust_env=False) as http:
            result=await http.post(self.issuer+'/token',data=data)
        self.assertEqual(result.status_code,400)
        self.assertFalse(next(e for e in self.events() if e['event']=='exchange')['pkce'])

    async def test_42_authorization_code_single_exchange(self):
        await self.start();data=await self.demo_code()
        async with httpx2.AsyncClient(trust_env=False) as http:
            self.assertEqual((await http.post(self.issuer+'/token',data=data)).status_code,200)
            self.assertEqual((await http.post(self.issuer+'/token',data=data)).status_code,400)

    async def test_43_expired_access_token_refused_by_resource(self):
        await self.start('expiry');tokens=[];original=MemoryTokenStorage.set_tokens
        async def observe(storage,value):tokens.append(value.access_token);await original(storage,value)
        with patch.object(MemoryTokenStorage,'set_tokens',observe):
            async with self.manager():
                await asyncio.sleep(1.1)
                async with httpx2.AsyncClient(trust_env=False) as http:
                    result=await http.post(self.url,headers={'Authorization':'Bearer '+tokens[0]},json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})
                self.assertEqual(result.status_code,401)

    async def test_44_stdio_bearer_oauth_coexist(self):
        from scripts import check_mcp_http as http_base
        from scripts.check_mcp_auth import FIXTURE as bearer_fixture, ENV, TOKEN
        await self.start();oauth=self.cfg(['add']).mcp_servers['web'];oauth_trace=self.trace
        with patch.dict(os.environ,{ENV:TOKEN}),patch.object(http_base,'FIXTURE',bearer_fixture):
            await HTTPChecks.start(self)
            bearer={'transport':'streamable_http','url':self.url,'auth':{'type':'bearer_env','token_env':ENV},
                    'allowed_tools':['add'],'tool_policies':{'add':'allow'},'timeout_seconds':2}
            cfg=replace(self.config,mcp_enabled=True,mcp_servers={'oauth':oauth,'bearer':bearer,'local':MCPChecks.demo(self,('add',))})
            async with MCPClientManager(cfg,self.tools) as m:
                for name in ('oauth','bearer','local'):
                    self.assertTrue((await m.call(name,'add',{'a':1,'b':2})).success)
        events=[json.loads(line) for line in oauth_trace.read_text().splitlines()]
        self.assertFalse(any(e.get('identity_header') for e in events))

    async def test_45_cli_eof_and_denial_never_open_browser(self):
        for text in ('','no\n'):
            read_fd,write_fd=os.pipe()
            with os.fdopen(read_fd) as reader:
                os.write(write_fd,text.encode());os.close(write_fd)
                terminal=N(isatty=lambda:True,fileno=reader.fileno,readline=reader.readline)
                with patch('sys.stdin',terminal),patch('webbrowser.open') as opened,contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(HTTPTransportError,'oauth_authorization_denied'):
                        await open_authorization('http://127.0.0.1:8766/authorize?client_id=local&scope=notes:read')
                    opened.assert_not_called()

    async def test_46_production_demo_cli_full_flow(self):
        # Reserve three distinct ports until launching the real CLI.
        sockets=[socket.socket() for _ in range(3)]
        for sock in sockets:sock.bind(('127.0.0.1',0))
        rp,ip,cp=[s.getsockname()[1] for s in sockets]
        for sock in sockets:sock.close()
        process=subprocess.Popen([sys.executable,'-m','scripts.mcp_oauth_demo_server','--resource-port',str(rp),
            '--issuer-port',str(ip),'--callback-port',str(cp)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,cwd=PROJECT_DIR)
        self.processes.append(process)
        self.url=f'http://127.0.0.1:{rp}/mcp';self.issuer=f'http://127.0.0.1:{ip}';self.redirect=f'http://127.0.0.1:{cp}/oauth/callback'
        self.trusted_resources={self.url};self.browser_count=0;self.browser_mode='normal';self.browser_secrets=[]
        with patch('mybot.mcp_client.oauth.open_authorization',self.browser):
            async with httpx2.AsyncClient(trust_env=False,timeout=.2) as http:
                for _ in range(200):
                    if process.poll() is not None:self.fail('CLI exited')
                    try:
                        if (await http.get(self.issuer+'/health')).status_code==200:break
                    except httpx2.RequestError:pass
                    await asyncio.sleep(.02)
                else:self.fail('CLI not ready')
            async with self.manager() as m:self.assertTrue((await m.call('web','add',{'a':1,'b':2})).success)

    async def test_47_metadata_cannot_bypass_limit_as_sse(self):
        await self.start('metadata-sse');await self.failure('oauth_response_type_refused')

    async def test_48_expired_without_refresh_no_anonymous_tool_call(self):
        await self.start('no-refresh')
        async with self.manager() as m:
            await asyncio.sleep(1.1)
            result=await m.call('web','add',{'a':1,'b':2})
            self.assertFalse(result.success);self.assertIn('oauth_login_required',result.error)
        self.assertEqual(self.browser_count,1)
        self.assertFalse(any(e.get('rpc')=='tools/call' for e in self.events()))


class CallbackChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.uri=f'http://127.0.0.1:{unused_port()}/oauth/callback'
        self.callback=OAuthCallback(self.uri);await self.callback.start();self.addAsyncCleanup(self.callback.close)

    async def test_structure_duplicates_path_method_encoding_and_single_use(self):
        async with httpx2.AsyncClient(trust_env=False) as http:
            for method,target in (('GET','/other?code=x&state=y'),('POST','/oauth/callback?code=x&state=y'),
                    ('GET','/oauth/callback?code=x&code=y&state=z'),('GET','/oauth/callback?code=x&state=y&state=z'),
                    ('GET','/oauth/callback?code=x&state=y&iss=a&iss=b'),('GET','/oauth/callback?code=x&state=%FF'),
                    ('GET','/oauth/callback?code=x&state=y&extra=z'),('GET','/oauth/callback?code='+('X'*4096)+'&state=y')):
                result=await http.request(method,self.uri.rsplit('/',2)[0]+target)
                self.assertEqual(result.status_code,400);self.assertFalse(self.callback.used)
            result=await http.get(self.uri+'?code=x&state=y&iss=http%3A%2F%2F127.0.0.1')
            self.assertEqual(result.status_code,200)
            self.assertEqual((await http.get(self.uri+'?code=x&state=y')).status_code,409)
        value=await self.callback.wait();self.assertEqual(value.code,'x');self.assertEqual(value.state,'y')

    async def test_denied_callback_closes(self):
        async with httpx2.AsyncClient(trust_env=False) as http:await http.get(self.uri+'?error=access_denied&state=x')
        with self.assertRaisesRegex(HTTPTransportError,'oauth_authorization_denied'):await self.callback.wait()
        self.assertIsNone(self.callback.server)

    async def test_cancel_stalled_http_handler(self):
        reader,writer=await asyncio.open_connection('127.0.0.1',urlsplit(self.uri).port)
        writer.write(b'GET /oauth/callback?');await writer.drain()
        await asyncio.sleep(.01);await self.callback.close()
        self.assertEqual(await asyncio.wait_for(reader.read(),1),b'')
        writer.close();await writer.wait_closed()

    async def test_raw_malformed_percent_and_wrong_host(self):
        for query,host in (('code=x&state=%GG',urlsplit(self.uri).netloc),('code=x&state=y','evil.example')):
            reader,writer=await asyncio.open_connection('127.0.0.1',urlsplit(self.uri).port)
            writer.write(f'GET /oauth/callback?{query} HTTP/1.1\r\nHost: {host}\r\n\r\n'.encode());await writer.drain()
            result=await reader.read();writer.close();await writer.wait_closed()
            self.assertIn(b'HTTP/1.1 400',result);self.assertFalse(self.callback.used)


def check_mcp_oauth():
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (OAuthChecks,CallbackChecks))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_mcp_oauth()
