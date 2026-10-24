"""Real loopback HTTP + official SDK; no third-party endpoint or model API."""
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
from unittest.mock import AsyncMock, patch

import httpx2
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.context_manager import ContextManager
from mybot.config import PROJECT_DIR
from mybot.mcp_client.approval import ApprovalDecision as D
from mybot.mcp_client.config import validate_http_url
from mybot.mcp_client.manager import MCPClientManager, MCPStartupError
from mybot.mcp_client.transport import HTTPBoundary, HTTPTransportError
from scripts.legacy_write_fixture import legacy_registry
from mybot.tools import build_default_tool_registry
from scripts.check_mcp import MCPChecks
from scripts.check_session import call, response, assert_pairs


# ASGI fault/trace wrapper; all successful MCP traffic is handled by the SDK.
FIXTURE = r'''
import asyncio,json,socket,sys
from pathlib import Path
import uvicorn
from scripts.mcp_http_demo_server import create_app
from scripts.mcp_demo_server import server
fd,port,mode,trace=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3],Path(sys.argv[4])
@server.tool()
def long_text() -> str:
    return 'SYNTHETIC-'*3000
@server.tool()
def fail() -> str:
    raise ValueError('PRIVATE_HTTP_EXCEPTION')
app=create_app(port,json_response=mode!='sse',stateless_http=mode=='stateless')
async def wrapped(scope,receive,send):
    if scope['type']!='http': return await app(scope,receive,send)
    if scope['path']=='/health':
        await send({'type':'http.response.start','status':200,'headers':[]})
        return await send({'type':'http.response.body','body':b'ready'})
    chunks=[]
    while True:
        message=await receive();chunks.append(message)
        if not message.get('more_body',False): break
    body=b''.join(m.get('body',b'') for m in chunks)
    try: parsed=json.loads(body)
    except ValueError:parsed={}
    method=parsed.get('method')
    name=parsed.get('params',{}).get('name')
    headers=dict(scope.get('headers',[]))
    with trace.open('a') as file:
        file.write(json.dumps({'http':scope['method'],'method':method,'name':name,
          'has_auth':any(k in headers for k in (b'authorization',b'proxy-authorization',b'cookie'))})+'\n')
    status=None
    if mode.startswith('status-') and scope['method']=='POST':status=int(mode.split('-')[1])
    if mode=='get-close' and scope['method']=='GET':status=405
    if mode=='list-fail' and method=='tools/list':status=500
    if mode=='call-fail' and method=='tools/call':status=503
    if mode=='hang-init' and method=='initialize':await asyncio.sleep(5)
    if mode.startswith('redirect') and scope['method']=='POST':
        target=(b'http://127.0.0.1:1/PRIVATE_REDIRECT' if mode=='redirect' else f'http://127.0.0.1:{port}/OTHER'.encode())
        await send({'type':'http.response.start','status':307,'headers':[(b'location',target)]})
        return await send({'type':'http.response.body','body':b'PRIVATE_REDIRECT_BODY'})
    if status:
        await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'text/plain')]})
        return await send({'type':'http.response.body','body':b'PRIVATE_HTTP_BODY'})
    if mode=='broken-init' and method=='initialize':
        await send({'type':'http.response.start','status':200,'headers':[(b'content-type',b'application/json')]})
        return await send({'type':'http.response.body','body':b'invalid PRIVATE_HTTP_BODY'})
    async def replay():
        return chunks.pop(0) if chunks else await receive()
    if mode=='late-save' and name=='save_note':
        pending=[]
        async def buffer(message):pending.append(message)
        await app(scope,replay,buffer)
        await asyncio.sleep(1)
        for message in pending:await send(message)
        return
    await app(scope,replay,send)
uvicorn.Server(uvicorn.Config(wrapped,log_level='critical',access_log=False)).run(sockets=[socket.socket(fileno=fd)])
'''


async def approve(request):return D.APPROVE
async def deny(request):return D.DENY


class HTTPChecks(unittest.IsolatedAsyncioTestCase):
    setUp = MCPChecks.setUp

    async def asyncSetUp(self):
        self.processes=[]
        self.addAsyncCleanup(self.stop_servers)

    async def stop_servers(self):
        for process in self.processes:
            if process.poll() is None:process.terminate()
        for process in self.processes:
            try:await asyncio.to_thread(process.wait,timeout=5)
            except subprocess.TimeoutExpired:
                process.kill();await asyncio.to_thread(process.wait)

    async def start(self,mode='normal',cli=False):
        trace=self.root/f'trace-{len(self.processes)}.jsonl'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            if cli:
                sock.close()
                command=[sys.executable,'-m','scripts.mcp_http_demo_server','--port',str(port)]
                options={}
            else:
                fixture=self.root/'http_fixture.py';fixture.write_text(FIXTURE)
                command=[sys.executable,str(fixture),str(sock.fileno()),str(port),mode,str(trace)]
                options={'pass_fds':(sock.fileno(),)}
            process=subprocess.Popen(command,cwd=PROJECT_DIR,env={**os.environ,'PYTHONPATH':str(PROJECT_DIR)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**options)
            self.processes.append(process)
        self.url=f'http://127.0.0.1:{port}/mcp';self.trace=trace;self.process=process
        async with httpx2.AsyncClient(trust_env=False,timeout=.2) as http:
            for _ in range(150):
                if process.poll() is not None:raise AssertionError('HTTP demo exited before readiness')
                try:
                    result=await http.get(f'http://127.0.0.1:{port}/health' if not cli else self.url)
                    if result.status_code in (200,400,405):break
                except httpx2.RequestError:pass
                await asyncio.sleep(.02)
            else:raise AssertionError('HTTP demo readiness timeout')
        return self.url

    def cfg(self,allowed=None,**policies):
        allowed=allowed or ['add','echo','save_note','read_note','delete_note']
        server=dict(transport='streamable_http',url=self.url,allowed_tools=allowed,
                    tool_policies={n:('confirm' if n in ('save_note','delete_note') else 'allow') for n in allowed},timeout_seconds=2)
        server['tool_policies'].update(policies)
        return replace(self.config,mcp_enabled=True,mcp_servers={'web':server})

    def manager(self,provider=None,**policies):
        self.tools=legacy_registry(self.workspace)
        return MCPClientManager(self.cfg(**policies),self.tools,provider)

    def events(self):
        return [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []

    async def read(self,m,key='k'):
        return await m.call('web','read_note',{'key':key})

    async def test_legacy_stdio_and_http_config(self):
        legacy=MCPChecks.demo(self)
        cfg=replace(self.config,mcp_servers={'old':legacy})
        self.assertNotIn('transport',cfg.mcp_servers['old'])
        self.url='http://127.0.0.1:8765/mcp';replace(self.cfg())
        template=json.loads((PROJECT_DIR/'config/config.example.json').read_text())
        replace(self.config,mcp_servers=template['mcp']['servers'])

    async def test_strict_transport_fields_and_policies(self):
        self.url='http://127.0.0.1:8765/mcp';valid=self.cfg().mcp_servers['web']
        for extra in ({'command':'python'},{'args':[]},{'headers':{}},{'transport':'sse'},{'transport':None},{'tool_policies':{'other':'allow'}},{'timeout_seconds':True}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                replace(self.config,mcp_servers={'web':valid|extra})
        for missing in ('url','allowed_tools'):
            invalid=dict(valid);del invalid[missing]
            with self.assertRaises(ValueError):replace(self.config,mcp_servers={'web':invalid})
        with self.assertRaises(ValueError):replace(self.config,mcp_servers={'old':MCPChecks.demo(self)|{'url':self.url}})

    async def test_url_restrictions_and_https_explicit_trust(self):
        for value in (None,1,'','http://example.com/mcp','http://localhost/mcp','http://0.0.0.0/mcp','http://169.254.169.254/mcp',
                      'http://127.1/mcp','http://2130706433/mcp',
                      'https://user:password@example.com/mcp','https://user@example.com/mcp','https://example.com/mcp?q=secret',
                      'https://example.com/mcp?','https://example.com/mcp#','https://example.com/\npath','ftp://127.0.0.1/mcp',
                      'https://%65xample.com/mcp','http://127.0.0.1:0/mcp','http://127.0.0.1:99999/mcp','https://example.com\\@evil/mcp'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_http_url(value)
        for value in ('http://127.0.0.1/mcp','http://[::1]/mcp','https://trusted.example/mcp'):
            validate_http_url(value)

    async def test_real_cli_demo_handshake_list_add_echo(self):
        await self.start(cli=True)
        async with self.manager() as m:
            self.assertEqual(m.protocols['web'],'2025-11-25')
            self.assertEqual(len(m._adapters),5)
            self.assertIn('5',(await self.tools.execute('mcp__web__add',{'a':2,'b':3})).output)
            self.assertIn('hello',(await self.tools.execute('mcp__web__echo',{'message':'hello'})).output)
        self.assertIsNone(self.process.poll())

    async def test_stateful_http_delete_session_and_server_survives(self):
        await self.start()
        clients=[];original=httpx2.AsyncClient
        def observe(**kwargs):
            http=original(**kwargs);clients.append(http);return http
        with patch('mybot.mcp_client.transport.httpx2.AsyncClient',side_effect=observe):
            async with self.manager() as m:
                self.assertTrue((await m.call('web','add',{'a':1,'b':2})).success)
        self.assertTrue(all(http.is_closed for http in clients));self.assertEqual(len(clients),1)
        self.assertTrue(m.closed);self.assertEqual(m.clients,{})
        self.assertTrue(any(e['http']=='DELETE' for e in self.events()))
        self.assertIsNone(self.process.poll())
        async with self.manager() as second:
            self.assertTrue((await second.call('web','add',{'a':3,'b':4})).success)

    async def test_sse_response_with_official_sdk(self):
        await self.start('sse')
        async with self.manager() as m:
            self.assertIn('sse-ok',(await m.call('web','echo',{'message':'sse-ok'})).output)

    async def test_stateless_json_with_official_sdk(self):
        await self.start('stateless')
        async with self.manager() as m:
            self.assertTrue((await m.call('web','add',{'a':3,'b':4})).success)
        self.assertFalse(any(e['http']=='DELETE' for e in self.events()))

    async def test_dual_transports_same_remote_name_and_atomic_registration(self):
        await self.start()
        cfg=self.cfg(['add']);cfg.mcp_servers['local']=MCPChecks.demo(self,('add',))
        async with MCPClientManager(cfg,self.tools) as m:
            self.assertEqual(set(m.clients),{'local','web'})
            for name in ('mcp__local__add','mcp__web__add'):
                self.assertTrue((await self.tools.execute(name,{'a':1,'b':2})).success)
        self.assertIsNone(self.process.poll())
        self.tools=legacy_registry(self.workspace)
        cfg.mcp_servers['web']['url']=self.url+'/missing'
        with self.assertRaises(MCPStartupError):
            async with MCPClientManager(cfg,self.tools):pass
        self.assertEqual(len(self.tools.get_definitions()),3)

    async def test_allowlist_and_deny_direct_adapter_manager(self):
        await self.start()
        cfg=self.cfg(['add','save_note','read_note'],save_note='deny')
        async with MCPClientManager(cfg,self.tools,approve) as m:
            self.assertFalse(self.tools.has_tool('mcp__web__echo'));self.assertFalse(self.tools.has_tool('mcp__web__save_note'))
            self.assertFalse((await m.call('web','echo',{'message':'no'})).success)
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'no'})).success)
            self.assertFalse((await m._adapters['web','save_note'].execute(key='k',content='no')).success)
            self.assertFalse((await self.read(m)).success)
        self.assertFalse(any(e['name']=='save_note' for e in self.events()))

    async def test_confirm_denied_save_sends_no_call(self):
        await self.start()
        async with self.manager(deny) as m:
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'denied'})).success)
            self.assertFalse((await self.read(m)).success)
        self.assertFalse(any(e['name']=='save_note' for e in self.events()))

    async def test_approve_save_reject_delete_then_approve_delete(self):
        await self.start()
        provider=AsyncMock(side_effect=[D.APPROVE,D.DENY,D.APPROVE])
        async with self.manager(provider) as m:
            self.assertTrue((await m.call('web','save_note',{'key':'k','content':'kept'})).success)
            self.assertIn('kept',(await self.read(m)).output)
            self.assertFalse((await m.call('web','delete_note',{'key':'k'})).success)
            self.assertIn('kept',(await self.read(m)).output)
            self.assertTrue((await m.call('web','delete_note',{'key':'k'})).success)
            self.assertFalse((await self.read(m)).success)
            self.assertEqual(provider.await_count,3)
        self.assertEqual(sum(e['name']=='delete_note' for e in self.events()),1)

    async def test_missing_provider_default_confirm_and_sensitive_denial(self):
        await self.start()
        cfg=self.cfg();del cfg.mcp_servers['web']['tool_policies']['save_note']
        async with MCPClientManager(cfg,self.tools) as m:
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'no'})).success)
            m.approval_provider=approve
            self.assertFalse((await m.call('web','save_note',{'key':'k','content':'sk-'+'A'*30})).success)
            self.assertFalse((await self.read(m)).success)
        self.assertFalse(any(e['name']=='save_note' for e in self.events()))

    async def test_snapshot_no_reuse_and_schema_enforced(self):
        await self.start();arguments={'key':'original','content':'inspected'}
        async def tamper(request):
            arguments.update(key='changed',content='unapproved');return D.APPROVE
        async with self.manager(tamper) as m:
            self.assertFalse((await m.call('web','save_note',{'key':2,'content':'bad'})).success)
            self.assertTrue((await m.call('web','save_note',arguments)).success)
            self.assertIn('inspected',(await self.read(m,'original')).output)
            self.assertFalse((await self.read(m,'changed')).success)
            m.approval_provider=deny
            self.assertFalse((await m.call('web','delete_note',{'key':'original'})).success)
            self.assertIn('inspected',(await self.read(m,'original')).output)

    async def test_planning_evidence_batch_pairs_clear_no_replay(self):
        await self.start()
        cfg=self.cfg();effects=[response(calls=[call('p','create_plan','{"steps":["save","read"]}'),
            call('s','update_plan','{"step":1,"status":"in_progress"}'),
            call('w','mcp__web__save_note','{"key":"k","content":"denied"}'),
            call('later','mcp__web__add','{"a":1,"b":2}'),
            call('done','update_plan','{"step":1,"status":"completed"}')])]
        async with MCPClientManager(cfg,self.tools,deny) as m:
            client=N(chat=N(completions=N(create=AsyncMock(side_effect=effects))))
            agent=AgentLoop(client,cfg,self.tools,ContextBuilder(self.workspace))
            with contextlib.redirect_stdout(io.StringIO()):reply=await agent.handle_message('save and read')
            self.assertIn('未获批准',reply);assert_pairs(self,agent.session.history())
            self.assertEqual(agent.plan.steps[0].status,'failed');self.assertFalse(agent.plan.steps[0].verified)
            self.assertFalse(any(e['method']=='tools/call' for e in self.events()))
            await agent.handle_message('/clear');self.assertEqual(agent.session.history(),[])
            self.assertEqual(len(m.audit),1)
            m.approval_provider=approve
            agent.plan.create(['add','next']);agent.plan.update(1,'in_progress')
            self.assertTrue((await agent._execute('mcp__web__add','{"a":1,"b":2}')).success)
            self.assertTrue(agent.plan.steps[0].verified)
            agent.plan.update(1,'completed');agent.plan.update(2,'in_progress')
            self.assertFalse((await agent._execute('mcp__web__delete_note','{"key":"k"}')).success)
            self.assertFalse(agent.plan.steps[1].verified);self.assertEqual(agent.plan.steps[1].status,'failed')

    async def test_context_counts_http_schema_clips_copy_session_retains_original(self):
        await self.start()
        cfg=replace(self.cfg(['long_text']),context_enabled=True,context_max_chars=50000,context_tool_result_max_chars=256)
        requests=[];effects=[response(calls=[call('long','mcp__web__long_text','{}')]),response('excerpt')]
        async def create(**kwargs):requests.append(kwargs);return effects.pop(0)
        async with MCPClientManager(cfg,self.tools) as m:
            agent=AgentLoop(N(chat=N(completions=N(create=create))),cfg,self.tools,ContextBuilder(self.workspace))
            await agent.handle_message('read long output')
            history=agent.session.history();original=next(x['content'] for x in history if x['role']=='tool')
            clipped=next(x['content'] for x in requests[-1]['messages'] if x['role']=='tool')
            self.assertGreater(len(original),10000);self.assertLess(len(clipped),500)
            self.assertIn('已裁剪',clipped);self.assertIn('truncated',original);assert_pairs(self,history)
            definitions=requests[0]['tools']
            self.assertIn('mcp__web__long_text',[d['function']['name'] for d in definitions])
            without_http=[d for d in definitions if not d['function']['name'].startswith('mcp__web__')]
            self.assertGreater(ContextManager.count(requests[0]['messages'],definitions),ContextManager.count(requests[0]['messages'],without_http))

    async def test_iserror_never_success_or_raw_exception(self):
        await self.start()
        async with MCPClientManager(self.cfg(['fail']),self.tools) as m:
            result=await m.call('web','fail',{})
            self.assertFalse(result.success);self.assertNotIn('PRIVATE_HTTP_EXCEPTION',result.to_text())
            self.assertFalse(m.audit[-1]['success']);self.assertFalse(m.closed)

    async def test_http_status_errors_are_sanitized(self):
        for status in (401,403,404,500):
            await self.start('status-'+str(status))
            with self.subTest(status=status),self.assertRaises(MCPStartupError) as caught:
                async with self.manager():pass
            self.assertIn('http_'+str(status) if status!=500 else 'http_server_error',str(caught.exception))
            self.assertNotIn(self.url,str(caught.exception));self.assertNotIn('PRIVATE',str(caught.exception))

    async def test_redirects_never_followed(self):
        for mode in ('redirect','redirect-same'):
            await self.start(mode)
            with self.assertRaises(MCPStartupError) as caught:
                async with self.manager():pass
            self.assertIn('http_redirect_refused',str(caught.exception))
            self.assertEqual(len(self.events()),1)

    async def test_connection_refused_wrong_endpoint_bad_init_and_list(self):
        await self.start();self.process.terminate();await asyncio.to_thread(self.process.wait)
        with self.assertRaises(MCPStartupError) as caught:
            async with self.manager():pass
        self.assertIn('http_connection_error',str(caught.exception))
        for mode in ('broken-init','list-fail'):
            await self.start(mode)
            with self.assertRaises(MCPStartupError):
                async with self.manager():pass
            self.assertEqual(len(self.tools.get_definitions()),3)
        await self.start();self.url+='/missing'
        with self.assertRaises(MCPStartupError) as caught:
            async with self.manager():pass
        self.assertIn('http_404',str(caught.exception))

    async def test_initialize_timeout_and_tools_call_http_failure(self):
        await self.start('hang-init');cfg=self.cfg();cfg.mcp_servers['web']['timeout_seconds']=.2
        with self.assertRaises(MCPStartupError):
            async with MCPClientManager(cfg,self.tools):pass
        await self.start('call-fail')
        async with self.manager() as m:
            result=await m.call('web','add',{'a':1,'b':2})
            self.assertFalse(result.success);self.assertIn('http_server_error',result.error);self.assertTrue(m.closed)

    async def test_timeout_has_unknown_effects_and_no_retry(self):
        await self.start('late-save');cfg=self.cfg();cfg.mcp_servers['web']['timeout_seconds']=.2
        async with MCPClientManager(cfg,self.tools,approve) as m:
            result=await m.call('web','save_note',{'key':'k','content':'actual-effect'})
            self.assertFalse(result.success);self.assertIn('unknown',result.error);self.assertTrue(m.closed)
        async with self.manager() as second:
            self.assertIn('actual-effect',(await self.read(second)).output)
        self.assertEqual(sum(e['name']=='save_note' for e in self.events()),1)

    async def test_server_disconnect_closes_client_without_retry(self):
        await self.start()
        async with self.manager() as m:
            self.process.kill();await asyncio.to_thread(self.process.wait)
            result=await m.call('web','add',{'a':1,'b':2})
            self.assertFalse(result.success);self.assertTrue(m.closed);self.assertEqual(m.clients,{})

    async def test_owner_task_cancel_and_exception_release_only_client(self):
        await self.start()
        async def cancel(request):
            self.assertIs(asyncio.current_task(),m.owner)
            asyncio.current_task().cancel();await asyncio.sleep(0)
        m=self.manager(cancel)
        with self.assertRaises(asyncio.CancelledError):
            async with m:await m.call('web','save_note',{'key':'k','content':'no'})
        self.assertTrue(m.closed);self.assertIsNone(self.process.poll())
        async with self.manager() as second:
            child=await asyncio.create_task(second.call('web','add',{'a':1,'b':2}))
            self.assertFalse(child.success)
            self.assertFalse((await self.read(second)).success)
        with self.assertRaisesRegex(RuntimeError,'body'):
            async with self.manager():raise RuntimeError('body')
        self.assertIsNone(self.process.poll())

    async def test_cancel_call_wait_cleans_http_session(self):
        await self.start('late-save')
        async def run():
            async with self.manager(approve) as m:
                self.waiting=m
                await m.call('web','save_note',{'key':'k','content':'possibly-saved'})
        task=asyncio.create_task(run())
        for _ in range(150):
            if any(e['name']=='save_note' for e in self.events()):break
            await asyncio.sleep(.01)
        else:self.fail('call never reached real server')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(self.waiting.closed);self.assertEqual(self.waiting.clients,{})
        self.assertIsNone(self.process.poll())

    async def test_no_environment_credentials_or_proxy_and_no_wire_logs(self):
        await self.start()
        root=logging.getLogger();old=root.level;output=io.StringIO();handler=logging.StreamHandler(output)
        root.addHandler(handler);root.setLevel(logging.DEBUG)
        self.addCleanup(root.setLevel,old);self.addCleanup(root.removeHandler,handler)
        netrc=self.root/'netrc';netrc.write_text('machine 127.0.0.1 login SYNTHETIC_USER password SYNTHETIC_PASSWORD\n')
        with patch.dict(os.environ,{'NETRC':str(netrc),'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1','ALL_PROXY':'http://127.0.0.1:1','NO_PROXY':''}):
            async with self.manager() as m:
                self.assertTrue((await m.call('web','echo',{'message':'PRIVATE_HTTP_ECHO'})).success)
        self.assertFalse(any(e['has_auth'] for e in self.events()))
        for secret in (self.url,'PRIVATE_HTTP_ECHO','Mcp-Session-Id'):
            self.assertNotIn(secret,output.getvalue())
        self.assertNotIn('PRIVATE_HTTP_ECHO',json.dumps(m.audit))

    async def test_host_origin_security(self):
        await self.start()
        async with httpx2.AsyncClient(trust_env=False) as http:
            result=await http.post(self.url,headers={'host':'evil.example','content-type':'application/json'},content='{}')
            self.assertEqual(result.status_code,421)
            result=await http.post(self.url,headers={'origin':'https://evil.example','content-type':'application/json'},content='{}')
            self.assertEqual(result.status_code,403)

    async def test_optional_get_not_reconnected_on_wire(self):
        await self.start('get-close')
        async with self.manager() as m:
            await asyncio.sleep(1.15)
            self.assertTrue((await m.call('web','add',{'a':1,'b':2})).success)
        self.assertEqual(sum(e['http']=='GET' for e in self.events()),1)

    async def test_boundary_blocks_get_reconnect_and_clears_credentials(self):
        boundary=HTTPBoundary('http://127.0.0.1/mcp')
        first=httpx2.Request('GET','http://127.0.0.1/mcp',headers={'authorization':'PRIVATE','cookie':'PRIVATE'})
        await boundary.request(first);self.assertNotIn('authorization',first.headers);self.assertNotIn('cookie',first.headers)
        with self.assertRaises(HTTPTransportError):await boundary.request(httpx2.Request('GET','http://127.0.0.1/mcp'))
        with self.assertRaises(HTTPTransportError):await boundary.request(httpx2.Request('POST','http://example.com/mcp'))


def check_mcp_http():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HTTPChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_mcp_http()
