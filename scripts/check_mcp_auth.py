"""Phase 13: real loopback SDK auth/permissions and adversarial receive streams."""
import asyncio
import contextlib
import io
import json
import logging
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx2
from mybot.agent import AgentLoop, ContextBuilder
from mybot.mcp_client.config import validate_mcp
from mybot.mcp_client.credentials import load_credential, MAX_TOKEN_BYTES
from mybot.mcp_client.manager import MCPClientManager, MCPStartupError
from mybot.mcp_client.response_limit import ResponseLimitTransport, MAX_HTTP_JSON_BYTES
from mybot.mcp_client.transport import HTTPBoundary, HTTPTransportError
from scripts import check_mcp_http as base
from scripts.check_mcp import MCPChecks
from scripts.check_session import call, response, assert_pairs
from types import SimpleNamespace as N

# Only synthetic credentials; trace stores booleans, never header values/bodies.
TOKEN = 'local-synthetic-phase13-value'
ENV = 'MYBOT_TEST_MCP_TOKEN'
AUTH = {'type':'bearer_env','token_env':ENV}
FIXTURE = base.FIXTURE.replace('import asyncio,json,socket,sys', 'import asyncio,json,socket,sys,os,gzip')
FIXTURE = FIXTURE.replace("stateless_http=mode=='stateless')", "stateless_http=mode=='stateless',require_token_env='MYBOT_TEST_MCP_TOKEN')")
FIXTURE = FIXTURE.replace("'has_auth':any", "'auth_ok':headers.get(b'authorization')==('Bearer '+os.environ['MYBOT_TEST_MCP_TOKEN']).encode(),\n          'identity':headers.get(b'accept-encoding')==b'identity',\n          'body_secret':os.environ['MYBOT_TEST_MCP_TOKEN'].encode() in body,\n          'has_auth':any")
FIXTURE = FIXTURE.replace("b'PRIVATE_HTTP_BODY'", "b'PRIVATE_HTTP_BODY'+os.environ['MYBOT_TEST_MCP_TOKEN'].encode()")
FIXTURE = FIXTURE.replace("    if status:\n", "    if mode in ('call-401','call-403') and method=='tools/call':status=int(mode[-3:])\n    if status:\n")
FAULT = '''
    if (mode in ('large','chunked','compressed','sse-large') and method=='tools/call') or (mode=='large-init' and method=='initialize') or (mode=='large-list' and method=='tools/list'):
        data=b'X'*(3*1024*1024)
        headers=[(b'content-type',b'application/json')]
        if mode=='large':headers.append((b'content-length',str(len(data)).encode()))
        if mode=='compressed':
            headers.append((b'content-encoding',b'gzip'));data=gzip.compress(data)
        if mode=='sse-large':
            headers=[(b'content-type',b'text/event-stream')];data=b'event: message\\ndata: '+data+b'\\n\\n'
        await send({'type':'http.response.start','status':200,'headers':headers})
        for offset in range(0,len(data),16384):
            await send({'type':'http.response.body','body':data[offset:offset+16384],'more_body':True})
        return await send({'type':'http.response.body','body':b''})
'''
FIXTURE = FIXTURE.replace('    async def replay():', FAULT+'    async def replay():')


class AuthChecks(unittest.IsolatedAsyncioTestCase):
    setUp = MCPChecks.setUp
    asyncSetUp = base.HTTPChecks.asyncSetUp
    stop_servers = base.HTTPChecks.stop_servers
    events = base.HTTPChecks.events
    read = base.HTTPChecks.read
    manager = base.HTTPChecks.manager

    async def start(self, mode='normal', cli=False):
        self.env = patch.dict(os.environ,{ENV:TOKEN});self.env.start();self.addCleanup(self.env.stop)
        with patch.object(base,'FIXTURE',FIXTURE):
            return await base.HTTPChecks.start(self,mode,cli)

    def cfg(self, allowed=None, **policies):
        cfg = base.HTTPChecks.cfg(self,allowed,**policies)
        cfg.mcp_servers['web']['auth'] = dict(AUTH)
        return cfg

    async def startup_failure(self, kind, cfg=None):
        m = MCPClientManager(cfg or self.cfg(),self.tools)
        with self.assertRaises(MCPStartupError) as caught:
            async with m:pass
        self.assertIn(kind,str(caught.exception));self.assertNotIn(TOKEN,str(caught.exception))
        self.assertTrue(m.closed);self.assertFalse(m.clients)
        self.assertFalse(self.tools.has_tool('mcp__web__add'))
        return m

    async def test_01_config_and_legacy_none(self):
        self.url='http://127.0.0.1:1/mcp';cfg=self.cfg()
        for auth in (None,{'type':'none'},AUTH):
            server=dict(cfg.mcp_servers['web'])
            if auth is None:server.pop('auth')
            else:server['auth']=auth
            validate_mcp(True,{'web':server})
        validate_mcp(True,{'local':MCPChecks.demo(self)})

    async def test_02_stdio_refuses_even_none_auth(self):
        for auth in (AUTH,{'type':'none'}):
            with self.assertRaises(ValueError):validate_mcp(True,{'local':MCPChecks.demo(self)|{'auth':auth}})

    async def test_03_strict_auth_fields_and_plaintext(self):
        self.url='http://127.0.0.1:1/mcp';server=self.cfg().mcp_servers['web']
        for auth in (None,{},'none',{'type':'oauth'},AUTH|{'access_token':TOKEN},
                     {'type':'none','token_env':ENV}, {'type':'bearer_env'},
                     {'type':'bearer_env','token_env':1},
                     *({'type':'bearer_env','token_env':v} for v in ('','1TOKEN','A-B','A\n','A'*129))):
            with self.subTest(auth=type(auth)),self.assertRaises(ValueError):validate_mcp(True,{'web':server|{'auth':auth}})
        for key in ('access_token','refresh_token','client_secret','token','headers'):
            with self.assertRaises(ValueError):validate_mcp(True,{'web':server|{key:TOKEN}})

    async def test_04_missing_credential_no_network(self):
        await self.start()
        with patch.dict(os.environ,{},clear=True):await self.startup_failure('credential_missing')
        self.assertEqual(self.events(),[])

    async def test_05_invalid_credential_no_network(self):
        await self.start()
        for value in ('',' ','abc def','a\n','a\r\nb','a\x00','a\t','a\x7f','é','a:b','Bearer abc','a'* (MAX_TOKEN_BYTES+1)):
            with self.subTest(size=len(value)),patch('mybot.mcp_client.credentials.os.environ',{ENV:value}):
                await self.startup_failure('credential_invalid')
        self.assertEqual(self.events(),[])

    async def test_06_valid_token_repr_and_snapshot(self):
        with patch.dict(os.environ,{ENV:TOKEN}):credential=load_credential(AUTH)
        self.assertNotIn(TOKEN,repr(credential))
        with patch.dict(os.environ,{ENV:'changed'}):
            headers={};credential.apply(headers)
        self.assertEqual(headers['Authorization'],'Bearer '+TOKEN)

    async def test_07_authenticated_sdk_post_get_delete(self):
        await self.start()
        async with self.manager() as m:
            self.assertTrue((await m.call('web','add',{'a':2,'b':3})).success)
            with patch.dict(os.environ,{ENV:'changed-after-connect'}):
                self.assertTrue((await m.call('web','echo',{'message':'snapshot'})).success)
        events=self.events()
        self.assertTrue({'POST','GET','DELETE'} <= {e['http'] for e in events})
        self.assertTrue(all(e['auth_ok'] and e['identity'] and not e['body_secret'] for e in events))

    async def test_08_wrong_token_401_no_retry(self):
        await self.start()
        with patch.dict(os.environ,{ENV:'wrong-synthetic'}):await self.startup_failure('http_401')
        self.assertEqual(sum(e['method']=='initialize' for e in self.events()),1)

    async def test_09_anonymous_401_no_downgrade(self):
        await self.start();cfg=self.cfg();cfg.mcp_servers['web'].pop('auth')
        await self.startup_failure('http_401',cfg)
        self.assertEqual(len(self.events()),1);self.assertFalse(self.events()[0]['has_auth'])

    async def test_10_demo_raw_missing_wrong_and_no_echo(self):
        await self.start()
        async with httpx2.AsyncClient(trust_env=False) as http:
            for headers in ({},{'Authorization':'Bearer wrong-synthetic'}):
                result=await http.post(self.url,headers=headers,content='{}')
                self.assertEqual(result.status_code,401)
                self.assertNotIn(TOKEN,result.text);self.assertNotIn('wrong-synthetic',result.text)

    async def test_11_precise_target_and_header_replacement(self):
        with patch.dict(os.environ,{ENV:TOKEN}):credential=load_credential(AUTH)
        url='https://trusted.example/mcp';boundary=HTTPBoundary(url,credential)
        for target in ('https://other.example/mcp',url+'/other',url+'?token=x','http://trusted.example/mcp'):
            request=httpx2.Request('POST',target)
            with self.assertRaisesRegex(HTTPTransportError,'http_target_refused'):await boundary.request(request)
            self.assertNotIn('authorization',request.headers)
        for method in ('POST','GET','DELETE'):
            request=httpx2.Request(method,url,headers={'Authorization':'Basic unintended','Cookie':'private','Proxy-Authorization':'private'})
            await boundary.request(request)
            self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN)
            self.assertNotIn('cookie',request.headers);self.assertNotIn('proxy-authorization',request.headers)

    async def test_12_redirect_other_origin(self):
        await self.start('redirect');await self.startup_failure('http_redirect_refused')
        self.assertEqual(len(self.events()),1)

    async def test_13_redirect_other_endpoint(self):
        await self.start('redirect-same');await self.startup_failure('http_redirect_refused')
        self.assertEqual(len(self.events()),1)

    async def test_14_proxy_netrc_logging_audit_session_isolation(self):
        await self.start();output=io.StringIO();handler=logging.StreamHandler(output)
        root=logging.getLogger();old=root.level;root.setLevel(logging.DEBUG);root.addHandler(handler)
        self.addCleanup(root.setLevel,old);self.addCleanup(root.removeHandler,handler)
        netrc=self.root/'netrc';netrc.write_text('machine 127.0.0.1 login SYNTHETIC_USER password SYNTHETIC_PASSWORD\n')
        with patch.dict(os.environ,{'NETRC':str(netrc),'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':''}):
            async with self.manager() as m:
                effects=[response(calls=[call('a','mcp__web__add','{"a":1,"b":2}')]),response('done')]
                async def create(**kwargs):
                    self.assertNotIn(TOKEN,json.dumps(kwargs));return effects.pop(0)
                session_path=self.root/'state/session.json'
                cfg=replace(self.cfg(),session_persist=True,session_path=session_path,debug=True)
                agent=AgentLoop(N(chat=N(completions=N(create=create))),cfg,self.tools,ContextBuilder(self.workspace))
                with contextlib.redirect_stdout(output):self.assertEqual(await agent.handle_message('add'),'done')
                assert_pairs(self,agent.session.history())
                self.assertNotIn(TOKEN,json.dumps(agent.session.history()))
                self.assertNotIn(TOKEN,session_path.read_text())
                self.assertNotIn(TOKEN,json.dumps(self.tools.get_definitions()))
        self.assertNotIn(TOKEN,output.getvalue());self.assertNotIn(TOKEN,json.dumps(m.audit))
        self.assertTrue(all(e['auth_ok'] for e in self.events()))

    async def test_15_confirm_denied_save_no_call_or_effect(self):
        await self.start()
        async with self.manager(base.deny) as m:
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'blocked'})).success)
            self.assertFalse((await self.read(m)).success)
        self.assertFalse(any(e['name']=='save_note' for e in self.events()))

    async def test_16_confirm_approved_real_effect(self):
        await self.start()
        async with self.manager(base.approve) as m:
            self.assertTrue((await m.call('web','save_note',{'key':'k','content':'approved'})).success)
            self.assertIn('approved',(await self.read(m)).output)

    async def test_17_deny_hidden_and_unavailable(self):
        await self.start()
        async with self.manager(base.approve,save_note='deny') as m:
            self.assertFalse(self.tools.has_tool('mcp__web__save_note'))
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'denied'})).success)
        self.assertFalse(any(e['name']=='save_note' for e in self.events()))

    async def test_18_call_401_safe_no_retry(self):
        await self.call_failure('call-401','http_401')

    async def test_19_call_403_safe_no_retry(self):
        await self.call_failure('call-403','http_403')

    async def call_failure(self,mode,kind):
        await self.start(mode)
        clients=[];original=httpx2.AsyncClient
        def observe(**kwargs):
            client=original(**kwargs);clients.append(client);return client
        with patch('mybot.mcp_client.transport.httpx2.AsyncClient',side_effect=observe):
            async with self.manager() as m:
                result=await m.call('web','add',{'a':1,'b':2})
                self.assertFalse(result.success)
                self.assertIn(kind,result.error);self.assertIn('unknown',result.error)
                self.assertNotIn(TOKEN,result.error);self.assertTrue(m.closed);self.assertFalse(m.clients)
        self.assertTrue(all(c.is_closed for c in clients));self.assertEqual(len(clients),1)
        self.assertEqual(sum(e['method']=='tools/call' for e in self.events()),1)
        self.assertIsNone(self.process.poll())

    async def test_20_declared_large_json(self):
        await self.call_failure('large','http_response_too_large')

    async def test_21_unknown_length_chunked_oversize_json(self):
        await self.call_failure('chunked','http_response_too_large')

    async def test_22_compressed_response_refused(self):
        await self.call_failure('compressed','http_content_encoding_refused')

    async def test_23_oversize_init_atomic_cleanup(self):
        await self.start('large-init');await self.startup_failure('http_response_too_large')

    async def test_24_oversize_discovery_atomic_cleanup(self):
        await self.start('large-list');await self.startup_failure('http_response_too_large')

    async def test_25_sse_real_sdk(self):
        await self.start('sse')
        async with self.manager() as m:
            self.assertIn('sse-ok',(await m.call('web','echo',{'message':'sse-ok'})).output)

    async def test_26_sse_event_limit_still_enforced(self):
        await self.start('sse-large')
        async with self.manager() as m:
            result=await m.call('web','add',{'a':1,'b':2})
            self.assertFalse(result.success);self.assertNotIn('http_response_too_large',result.error)

    async def test_27_cancel_releases_session(self):
        await base.HTTPChecks.test_cancel_call_wait_cleans_http_session(self)
        self.assertTrue(all(e['auth_ok'] for e in self.events()))

    async def test_28_mixed_transports(self):
        await base.HTTPChecks.test_dual_transports_same_remote_name_and_atomic_registration(self)
        self.assertTrue(all(e['auth_ok'] for e in self.events()))

    async def test_29_connection_and_timeout_categories(self):
        await self.start('hang-init');cfg=self.cfg();cfg.mcp_servers['web']['timeout_seconds']=.1
        await self.startup_failure('timeout',cfg)
        cfg.mcp_servers['web']['url']='http://127.0.0.1:1/mcp'
        await self.startup_failure('http_connection_error',cfg)

    async def test_30_demo_cli_auth_mode(self):
        # Real production CLI entry point, on a reserved test port.
        import socket,subprocess,sys
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.url=f'http://127.0.0.1:{port}/mcp'
        with patch.dict(os.environ,{ENV:TOKEN}):
            process=subprocess.Popen([sys.executable,'-m','scripts.mcp_http_demo_server','--port',str(port),'--require-token-env',ENV],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.processes.append(process)
            async with httpx2.AsyncClient(trust_env=False,timeout=.2) as http:
                for _ in range(150):
                    try:
                        if (await http.get(self.url)).status_code==401:break
                    except httpx2.RequestError:pass
                    await asyncio.sleep(.02)
                else:self.fail('CLI auth readiness failed')
            async with self.manager() as m:
                self.assertTrue((await m.call('web','add',{'a':1,'b':2})).success)

    async def test_31_credentials_isolated_between_servers(self):
        await self.start();protected_trace=self.trace
        cfg=self.cfg(['add'])
        # A second real SDK server deliberately has no auth policy.
        await base.HTTPChecks.start(self)
        anonymous_trace=self.trace
        anonymous=dict(cfg.mcp_servers['web']);anonymous.pop('auth');anonymous['url']=self.url
        cfg.mcp_servers['anonymous']=anonymous
        async with MCPClientManager(cfg,self.tools) as m:
            for name in ('anonymous','web'):
                self.assertTrue((await m.call(name,'add',{'a':1,'b':2})).success)
        events=[json.loads(line) for line in anonymous_trace.read_text().splitlines()]
        self.assertTrue(events);self.assertFalse(any(e['has_auth'] for e in events))
        events=[json.loads(line) for line in protected_trace.read_text().splitlines()]
        self.assertTrue(events);self.assertTrue(all(e['auth_ok'] for e in events))

    async def test_32_missing_credential_cleans_previous_stdio_process(self):
        await self.start();cfg=self.cfg(['add'])
        cfg.mcp_servers['aaa']=MCPChecks.fixture_config(self,['typed']).mcp_servers['test']
        with patch.dict(os.environ,{},clear=True):
            await self.startup_failure('credential_missing',cfg)
        pid=int(self.pid.read_text())
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)
        self.assertFalse(self.tools.has_tool('mcp__aaa__typed'))


class ProbeStream(httpx2.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks=chunks;self.reads=0;self.closed=False
    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads+=1;yield chunk
    async def aclose(self):self.closed=True


class ProbeTransport(httpx2.AsyncBaseTransport):
    def __init__(self, stream, headers):
        self.stream,self.headers=stream,headers;self.closed=False
    async def handle_async_request(self, request):
        return httpx2.Response(200,headers=self.headers,stream=self.stream)
    async def aclose(self):self.closed=True


class ReceiveChecks(unittest.IsolatedAsyncioTestCase):
    async def test_forged_length_cannot_bypass_stream_limit_and_stop_early(self):
        for length in (None,'1',str(MAX_HTTP_JSON_BYTES*10)):
            stream=ProbeStream([b'x'*65536]*100)
            headers={'content-type':'application/json'}
            if length:headers['content-length']=length
            inner=ProbeTransport(stream,headers);forwarded=0
            async with httpx2.AsyncClient(transport=ResponseLimitTransport(inner)) as http:
                with self.assertRaisesRegex(HTTPTransportError,'http_response_too_large'):
                    async with http.stream('GET','http://127.0.0.1/mcp') as result:
                        async for chunk in result.aiter_bytes():forwarded+=len(chunk)
            self.assertEqual(forwarded,MAX_HTTP_JSON_BYTES)
            self.assertEqual(stream.reads,33);self.assertTrue(stream.closed and inner.closed)

    async def test_small_and_exact_limit_json(self):
        for size in (10,MAX_HTTP_JSON_BYTES):
            stream=ProbeStream([b'x'*size]);inner=ProbeTransport(stream,{'content-type':'application/json'})
            async with httpx2.AsyncClient(transport=ResponseLimitTransport(inner)) as http:
                result=await http.get('http://127.0.0.1/mcp');self.assertEqual(len(result.content),size)
            self.assertTrue(stream.closed)

    async def test_non_sse_unknown_media_also_bounded(self):
        stream=ProbeStream([b'x'*(MAX_HTTP_JSON_BYTES+1)])
        async with httpx2.AsyncClient(transport=ResponseLimitTransport(ProbeTransport(stream,{}))) as http:
            with self.assertRaisesRegex(HTTPTransportError,'http_response_too_large'):await http.get('http://127.0.0.1/mcp')
        self.assertTrue(stream.closed)

    async def test_compression_rejected_before_first_read(self):
        for encoding in ('gzip','br','deflate','identity, gzip','unknown'):
            stream=ProbeStream([b'compressed'])
            async with httpx2.AsyncClient(transport=ResponseLimitTransport(ProbeTransport(stream,{'content-encoding':encoding}))) as http:
                with self.assertRaisesRegex(HTTPTransportError,'http_content_encoding_refused'):await http.get('http://127.0.0.1/mcp')
            self.assertEqual(stream.reads,0);self.assertTrue(stream.closed)

    async def test_sse_aggregate_not_json_limited(self):
        stream=ProbeStream([b': small event\n\n'*4096]*50)
        async with httpx2.AsyncClient(transport=ResponseLimitTransport(ProbeTransport(stream,{'content-type':'Text/Event-Stream; charset=utf-8'}))) as http:
            async with http.stream('GET','http://127.0.0.1/mcp') as result:
                total=0
                async for chunk in result.aiter_bytes():total+=len(chunk)
        self.assertGreater(total,MAX_HTTP_JSON_BYTES);self.assertTrue(stream.closed)

    async def test_stream_cancel_closes_underlying_response(self):
        started=asyncio.Event()
        class WaitingStream(ProbeStream):
            async def __aiter__(self):
                yield b'partial'
                started.set()
                await asyncio.Event().wait()
        stream=WaitingStream([]);inner=ProbeTransport(stream,{'content-type':'application/json'})
        async def read():
            async with httpx2.AsyncClient(transport=ResponseLimitTransport(inner)) as http:
                await http.get('http://127.0.0.1/mcp')
        task=asyncio.create_task(read());await started.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(stream.closed and inner.closed)


def check_mcp_auth():
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (AuthChecks,ReceiveChecks))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_mcp_auth()
