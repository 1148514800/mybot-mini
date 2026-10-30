"""Offline web channel E2E: real AgentLoop/native tools, synthetic LLM, zero paid HTTP.

--serve: disposable browser acceptance server on 127.0.0.1:8877, unmistakably synthetic.
Never used by the production mybot.web entry point.
"""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import uvicorn
from mybot.config import GatewayConfig
from mybot.web.server import create_app
from mybot.web.runtime import ChatRuntime
from mybot.web.approval import WebApproval
from mybot.tools.command_approval import inspectable_command
from mybot.mcp_client.approval import ApprovalDecision, inspectable_request
from mybot.tools.undo_approval import UndoApprovalRequest
from mybot.provider_failover import ProviderFailoverClient
from scripts.check_session import response, call, assert_pairs
from scripts.check_patch_preview_receipt import init
from scripts.check_tool_verification_reliability import changes, TEST_ARGV

MARKDOWN = '''这是通过真实 **AgentLoop** 返回的合成验收回复，未调用付费模型。

### 一个清晰的开始
- 独立的会话上下文
- 可观察的工具调用

```python
from pathlib import Path

def inspect_project(root):
    # 先理解，再行动
    return sorted(Path(root).glob("*.py"))
    # Long code blocks stay inside their own horizontal viewport: alpha_beta_gamma_delta_epsilon_zeta_eta_theta_iota_kappa_lambda_mu_nu_xi_omicron_pi_rho_sigma_tau_upsilon_phi_chi_psi_omega
```

| 能力 | 状态 |
| --- | --- |
| AgentLoop | 已连接 |
| 实时活动 | 已启用 |

<script>alert("xss")</script>
[危险链接](javascript:alert)
'''


class SyntheticClient:
    def __init__(self, config, *, delay_close=None, fail_close=False):
        self.config = config; self.step = 0; self.requests = []; self.closed = False
        self.delay_close = delay_close; self.fail_close = fail_close
        self.chat = N(completions=N(create=self.create))

    async def create(self, **kwargs):
        self.requests.append(kwargs['messages']); step = self.step; self.step += 1
        assert_pairs(unittest.TestCase(), kwargs['messages'])
        prompt = [m['content'] for m in kwargs['messages'] if m['role'] == 'user'][-1]
        if '等待' in prompt or '取消' in prompt: await asyncio.Event().wait()
        if '错误' in prompt: raise RuntimeError('sk-THIS_IS_A_SYNTHETIC_SECRET_123456789')
        if '工具' in prompt and step == 0:
            return response(calls=[call('files', 'list_files', '{"path":"."}')])
        if any(word in prompt for word in ('修复', '预览', '不测试')):
            root = self.config.workspace
            if step == 0: return response(calls=[call('read', 'read_file_range', '{"path":"value.py","start_line":1,"end_line":20}')])
            if step == 1: return response(calls=[call('preview', 'apply_patch', json.dumps({'dry_run': True, 'changes': changes(root)}))])
            if step == 2 and '预览' not in prompt:
                meta = json.loads(kwargs['messages'][-1]['content'].split('metadata=', 1)[1])
                return response(calls=[call('commit', 'apply_patch', json.dumps({'dry_run': False, 'preview_receipt': meta['preview_receipt']}))])
            if step == 3 and '不测试' not in prompt and '预览' not in prompt:
                return response(calls=[call('test', 'run_command', json.dumps({'argv': TEST_ARGV}))])
            return response('修改流程结束。')
        return response(MARKDOWN if prompt != '上下文' else '历史用户轮次：' + str(sum(m['role']=='user' for m in kwargs['messages'])))

    async def close(self):
        if self.delay_close: await self.delay_close.wait()
        self.closed = True
        if self.fail_close: raise RuntimeError('synthetic cleanup fault')


def config(root, coding=False):
    return GatewayConfig(workspace=root.resolve(), provider='offline-synthetic', model='synthetic-browser-client',
        context_token_budget={'input_limit':64000}, api_key='synthetic-secret-key', base_url='https://offline.invalid',  skills_enabled=False,
        context_enabled=False, mcp_enabled=False, coding_enabled=coding,
        coding_patch_mode='write' if coding else 'off', coding_preview_receipt=coding,
        coding_command={'mode': 'macos_readonly'} if coding else {},
        coding_autonomy={'enabled': coding}, coding_git_workflow={'enabled': coding}, max_react_steps=12)


class WebChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); init(self.root)
        self.clients = []
        def factory(cfg):
            client = SyntheticClient(cfg); self.clients.append(client); return client
        self.factory = factory
        self.app = create_app(config(self.root), port=8765, client_factory=factory, approval_timeout=.08)
        self.addAsyncCleanup(self.app.runtime.close)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1:8765')
        self.addAsyncCleanup(self.http.aclose)
        await self.http.get('/')
        self.boot = (await self.http.get('/api/bootstrap')).json()
        self.headers = {'Origin': 'http://127.0.0.1:8765', 'X-Mybot-CSRF':self.boot['csrf']}

    async def post(self, path, data=None, **kw):
        return await self.http.post('/api/'+path, json={} if data is None else data, headers=kw.pop('headers',self.headers), **kw)

    async def new(self):
        r = await self.post('conversations'); self.assertEqual(r.status_code,201); return r.json()['id']

    async def run_chat(self, text='你好', identifier=None):
        identifier = identifier or await self.new()
        result = await self.post(f'conversations/{identifier}/messages', {'message':text})
        self.assertEqual(result.status_code,202)
        await self.app.runtime.conversations[identifier].task
        return (await self.http.get(f'/api/conversations/{identifier}')).json()

    async def coding_app(self):
        await self.http.aclose()
        self.app = create_app(config(self.root,True), client_factory=self.factory, approval_timeout=10)
        self.addAsyncCleanup(self.app.runtime.close)
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1:8765');self.addAsyncCleanup(self.http.aclose)
        await self.http.get('/');self.boot=(await self.http.get('/api/bootstrap')).json();self.headers['X-Mybot-CSRF']=self.boot['csrf']

    async def wait_pending(self, c):
        for _ in range(300):
            p = c.approval.public_pending() if c.approval else None
            if p: return p
            if c.task.done(): self.fail('approval not reached: '+c.status)
            await asyncio.sleep(.01)
        self.fail('approval wait timeout')

    async def test_home_static_and_csp(self):
        r=await self.http.get('/');self.assertEqual(r.status_code,200);self.assertIn('mybot-mini',r.text)
        self.assertIn("script-src 'self'",r.headers['content-security-policy']);self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('SameSite=strict',r.headers['set-cookie'])
        for name in ('app.js','style.css','markdown.js'): self.assertEqual((await self.http.get('/static/'+name)).status_code,200)
    async def test_arbitrary_file_forbidden(self):
        for path in ('/static/config.json','/config/config.json','/static/../../etc/passwd'):
            self.assertEqual((await self.http.get(path)).status_code,404)
    async def test_no_cors(self):
        r=await self.http.options('/api/bootstrap',headers={'Origin':'https://evil.invalid'})
        self.assertEqual(r.status_code,403);self.assertNotIn('access-control-allow-origin',r.headers)
    async def test_host_rebinding(self):self.assertEqual((await self.http.get('/api/bootstrap',headers={'Host':'evil.invalid'})).status_code,403)
    async def test_wrong_port(self):self.assertEqual((await self.http.get('/',headers={'Host':'127.0.0.1:9999'})).status_code,403)
    async def test_cross_site_get(self):self.assertEqual((await self.http.get('/api/bootstrap',headers={'Sec-Fetch-Site':'cross-site'})).status_code,403)
    async def test_cookie_required(self):
        self.http.cookies.clear();self.assertEqual((await self.http.get('/api/bootstrap')).status_code,403)
    async def test_csrf_required(self):self.assertEqual((await self.post('conversations',headers={'Origin':self.headers['Origin']})).status_code,403)
    async def test_origin_required(self):self.assertEqual((await self.post('conversations',headers={'X-Mybot-CSRF':self.boot['csrf']})).status_code,403)
    async def test_origin_null(self):self.assertEqual((await self.post('conversations',headers={**self.headers,'Origin':'null'})).status_code,403)
    async def test_empty_input(self):
        c=await self.new();self.assertEqual((await self.post(f'conversations/{c}/messages',{'message':'  '})).status_code,400)
    async def test_oversized_input(self):
        c=await self.new();self.assertEqual((await self.post(f'conversations/{c}/messages',{'message':'x'*17000})).status_code,400)
    async def test_body_limit(self):
        r=await self.http.post('/api/conversations',content=b'x'*40000,headers=self.headers);self.assertEqual(r.status_code,413)
    async def test_invalid_json_duplicate_fields(self):
        c=await self.new();r=await self.http.post(f'/api/conversations/{c}/messages',content='{"message":"a","message":"b"}',headers={**self.headers,'Content-Type':'application/json'});self.assertEqual(r.status_code,400)
    async def test_extra_fields(self):
        c=await self.new();self.assertEqual((await self.post(f'conversations/{c}/messages',{'message':'hello','api_key':'x'})).status_code,400)
    async def test_real_agent_reply_and_prompt(self):
        state=await self.run_chat();self.assertEqual(state['status'],'completed');self.assertIn('AgentLoop',state['messages'][-1]['content']);self.assertEqual(self.clients[0].requests[0][-1]['content'],'你好')
    async def test_multi_turn_context(self):
        state=await self.run_chat();state=await self.run_chat('上下文',state['id']);self.assertIn('2',state['messages'][-1]['content']);self.assertEqual(state['requests'],1);self.assertEqual(sum(e['type']=='message_started' for e in state['events']),1)
    async def test_session_isolation(self):
        first=await self.run_chat('私有第一轮');second=await self.run_chat('上下文');self.assertNotEqual(first['id'],second['id']);self.assertIn('1',second['messages'][-1]['content'])
    async def test_clear(self):
        state=await self.run_chat();self.assertEqual((await self.post(f"conversations/{state['id']}/clear")).status_code,200)
        c=self.app.runtime.conversations[state['id']];self.assertEqual(c.session.history(),[]);self.assertEqual(c.messages,[])
    async def test_conversation_limit(self):
        for _ in range(20):await self.new()
        self.assertEqual((await self.post('conversations')).status_code,409)
    async def test_web_undo_explicitly_unsupported(self):
        c=await self.new();self.assertEqual((await self.post(f'conversations/{c}/messages',{'message':'/undo'})).status_code,400)
    async def test_event_order_and_no_raw_arguments(self):
        state=await self.run_chat('工具');types=[e['type'] for e in state['events']]
        self.assertEqual(types[0],'message_started');self.assertEqual(types[-1],'message_completed');self.assertLess(types.index('tool_started'),types.index('tool_finished'))
        event=next(e for e in state['events'] if e['type']=='tool_finished');self.assertTrue(event['success']);self.assertNotIn('arguments',json.dumps(event))
    async def test_tools_real_file_output(self):
        state=await self.run_chat('工具');self.assertTrue(any(e['type']=='tool_finished' and e['tool']=='list_files' for e in state['events']));self.assertGreaterEqual(len(self.clients[0].requests),2)
    async def test_no_fabricated_streaming_tokens(self):
        state=await self.run_chat();self.assertFalse(any(e['type'] in ('token','text_delta') for e in state['events']));self.assertEqual(state['tokens'],None)
    async def test_error_redaction(self):
        state=await self.run_chat('错误');self.assertEqual(state['status'],'failed');self.assertNotIn('THIS_IS_A',json.dumps(state));self.assertTrue(self.clients[0].closed)
    async def test_config_no_key(self):
        text=json.dumps(self.boot);self.assertNotIn('synthetic-secret-key',text);self.assertNotIn('api_key',text);self.assertFalse(self.boot['persistence'])
    async def test_prompt_key_redacted_only_for_ui(self):
        state=await self.run_chat('synthetic-secret-key');self.assertNotIn('synthetic-secret-key',json.dumps(state));self.assertEqual(self.clients[0].requests[0][-1]['content'],'synthetic-secret-key')
    async def test_markdown_renderer_constructs_dom_only(self):
        text=(Path(__file__).parent.parent/'mybot/web/static/markdown.js').read_text()
        self.assertNotIn('innerHTML',text);self.assertNotIn('eval(',text);self.assertIn('createTextNode',text);self.assertIn("['http:', 'https:']",text)
    async def test_only_theme_in_localstorage(self):
        text=(Path(__file__).parent.parent/'mybot/web/static/app.js').read_text();self.assertEqual(text.count('localStorage.setItem'),1);self.assertIn("localStorage.setItem('mybot-theme',theme)",text)
    async def test_busy_across_conversations(self):
        first=await self.new();second=await self.new();await self.post(f'conversations/{first}/messages',{'message':'等待'})
        self.assertEqual((await self.post(f'conversations/{second}/messages',{'message':'你好'})).status_code,409)
        self.assertEqual((await self.post(f'conversations/{first}/clear')).status_code,409)
        await self.post(f'conversations/{first}/stop');self.assertIsNone(self.app.runtime.owner)
    async def test_cancel_cleanup_barrier(self):
        gate=asyncio.Event();self.app.runtime.client_factory=lambda cfg:SyntheticClient(cfg,delay_close=gate)
        c=await self.new();await self.post(f'conversations/{c}/messages',{'message':'等待'});conv=self.app.runtime.conversations[c]
        stop=asyncio.create_task(self.app.runtime.stop(conv));await asyncio.sleep(.03);self.assertFalse(stop.done());self.assertEqual(self.app.runtime.owner,c)
        gate.set();await stop;self.assertIsNone(self.app.runtime.owner);self.assertEqual(conv.status,'cancelled')
    async def test_cleanup_uncertain_locks_workspace(self):
        self.app.runtime.client_factory=lambda cfg:SyntheticClient(cfg,fail_close=True)
        state=await self.run_chat();self.assertEqual(state['status'],'cleanup_uncertain');self.assertTrue(self.app.runtime.cleanup_uncertain)
        other=await self.new();self.assertEqual((await self.post(f'conversations/{other}/messages',{'message':'你好'})).status_code,409)
    async def test_timeout_cleanup(self):
        self.app.runtime.task_timeout=.03;state=await self.run_chat('等待');self.assertEqual(state['status'],'stopped');self.assertIsNone(self.app.runtime.owner)
    async def test_refresh_running_state(self):
        c=await self.new();await self.post(f'conversations/{c}/messages',{'message':'等待'});state=(await self.http.get(f'/api/conversations/{c}')).json();self.assertEqual(state['status'],'running');self.assertEqual(state['messages'][0]['role'],'user');await self.post(f'conversations/{c}/stop')
    async def test_receipt_preview_not_commit(self):
        await self.coding_app();state=await self.run_chat('只预览');self.assertEqual(state['report']['current_revision'],0)
        e=next(e for e in state['events'] if e['type']=='tool_finished' and e['tool']=='apply_patch');self.assertTrue(e['metadata']['dry_run']);self.assertFalse(e['metadata']['applied']);self.assertNotIn('preview_receipt',json.dumps(e));self.assertIn('value + 1',(self.root/'value.py').read_text())
    async def test_receipt_commit_and_browser_approval(self):
        await self.coding_app();c=await self.new();await self.post(f'conversations/{c}/messages',{'message':'修复'});conv=self.app.runtime.conversations[c];p=await self.wait_pending(conv)
        self.assertIn('argv',p['display']);self.assertNotIn(p['id'],json.dumps(list(conv.events)))
        self.assertEqual((await self.post(f'conversations/{c}/approval',{'id':p['id'],'allow':True})).status_code,200)
        await conv.task;self.assertEqual(conv.report['state'],'verified');self.assertEqual(conv.report['current_revision'],1);self.assertIn('value * 2',(self.root/'value.py').read_text())
        self.assertEqual((await self.post(f'conversations/{c}/approval',{'id':p['id'],'allow':True})).status_code,409)
        self.assertTrue(any(e['type']=='approval_resolved' and e['approved'] for e in conv.events));self.assertNotIn('Strict Success通过',conv.messages[-1]['content'])
    async def test_command_deny(self):
        await self.coding_app();c=await self.new();await self.post(f'conversations/{c}/messages',{'message':'修复'});conv=self.app.runtime.conversations[c];p=await self.wait_pending(conv)
        await self.post(f'conversations/{c}/approval',{'id':p['id'],'allow':False});await conv.task;self.assertNotEqual(conv.report['state'],'verified')
    async def test_approval_wrong_conversation(self):
        await self.coding_app();c=await self.new();other=await self.new();await self.post(f'conversations/{c}/messages',{'message':'修复'});conv=self.app.runtime.conversations[c];p=await self.wait_pending(conv)
        self.assertEqual((await self.post(f'conversations/{other}/approval',{'id':p['id'],'allow':True})).status_code,409);await self.post(f'conversations/{c}/stop');self.assertIsNone(conv.approval.pending);self.assertEqual(conv.report['state'],'cancelled');self.assertEqual(conv.report['committed_patches'],1)
    async def test_no_test_no_verified(self):
        await self.coding_app();state=await self.run_chat('不测试');self.assertNotEqual(state['report']['state'],'verified');self.assertEqual(state['report']['tests_passed_after_last_patch'],0)
    async def test_approval_nonce_timeout(self):
        events=[];broker=WebApproval(events.append,timeout=.02);task=asyncio.create_task(broker(inspectable_command('macos_readonly','.',('python','-m','unittest'),10)));await asyncio.sleep(0);p=broker.public_pending();self.assertIsNotNone(p)
        self.assertIs(await task,ApprovalDecision.DENY);self.assertFalse(broker.resolve(p['id'],True));self.assertIsNone(broker.pending)
    async def test_approval_duplicate_nonce(self):
        b=WebApproval(lambda e:None);task=asyncio.create_task(b(inspectable_command('host_confirm','.',('python','-m','unittest'),10)));await asyncio.sleep(0);p=b.public_pending();self.assertTrue(b.resolve(p['id'],True));self.assertFalse(b.resolve(p['id'],True));self.assertIs(await task,ApprovalDecision.APPROVE)
    async def test_mcp_approval_adapter(self):
        b=WebApproval(lambda e:None);task=asyncio.create_task(b(inspectable_request('demo','echo',{'text':'hello'})));await asyncio.sleep(0);p=b.public_pending();self.assertEqual(p['kind'],'mcp');b.resolve(p['id'],False);self.assertIs(await task,ApprovalDecision.DENY)
    async def test_uninspectable_and_undo_deny(self):
        b=WebApproval(lambda e:None)
        self.assertIs(await b(None),ApprovalDecision.DENY);self.assertIs(await b(UndoApprovalRequest((), '{}')),ApprovalDecision.DENY)
    async def test_approval_known_secret_deny(self):
        b=WebApproval(lambda e:None,secret_values=lambda:('synthetic-value-123',));r=inspectable_command('host_confirm','.',('python','-c','print("synthetic-value-123")'),10)
        self.assertIs(await b(r),ApprovalDecision.DENY)
    async def test_provider_failover_original_adapter(self):
        from scripts.check_coding_failover import connection, client
        cfg=replace(config(self.root),provider='coco',model='primary');backup=replace(cfg,provider='coco2',model='backup')
        self.app.runtime.config=cfg
        def factory(_):return ProviderFailoverClient(client([connection()]),cfg,backup,lambda _:client([response('备用模型真实适配器的合成回复')]))
        self.app.runtime.client_factory=factory;state=await self.run_chat();e=next(e for e in state['events'] if e['type']=='model_request_finished');self.assertEqual(e['provider'],'coco2');self.assertEqual(e['model'],'backup')
    async def test_memory_session_creates_no_legacy_disk(self):
        path=self.root.parent/(self.root.name+'-web-state.json');self.app.runtime.config=replace(config(self.root),session_backend='memory')
        await self.run_chat();self.assertFalse(path.exists())
    async def test_event_observer_failure_does_not_change_agent(self):
        from mybot.agent import AgentLoop, ContextBuilder
        from mybot.tools import build_default_tool_registry
        cfg=config(self.root);c=SyntheticClient(cfg)
        def broken(_):raise RuntimeError('observer')
        agent=AgentLoop(c,cfg,build_default_tool_registry(self.root),ContextBuilder(self.root),event_callback=broken)
        self.assertIn('AgentLoop',await agent.handle_message('你好'))
    async def test_approval_preserves_escaped_controls(self):
        b=WebApproval(lambda e:None);r=inspectable_command('host_confirm','.',('python','-c','print("\u202e")'),10)
        task=asyncio.create_task(b(r));await asyncio.sleep(0);p=b.public_pending()
        self.assertIn('\\u202e',p['display']);self.assertNotIn('\u202e',p['display']);b.resolve(p['id'],False);await task

    async def test_sse_cross_origin_rejected(self):
        c=await self.new();r=await self.http.get(f'/api/conversations/{c}/events',headers={'Origin':'https://evil.invalid'})
        self.assertEqual(r.status_code,403)

    async def test_bounded_event_and_history(self):
        c=await self.new();conv=self.app.runtime.conversations[c]
        for i in range(200):conv.emit({'type':'tool_finished','tool':'x','call_id':str(i),'diff':'字'*40000})
        self.assertEqual(len(conv.events),128)
        self.assertLess(len(json.dumps(conv.state(),ensure_ascii=False).encode()),8*1024*1024)
        self.assertTrue(conv.events[-1]['display_truncated'])

    async def test_real_mcp_owner_and_browser_approval(self):
        server={'command':sys.executable,'args':['-m','scripts.mcp_demo_server'],'allowed_tools':['echo'],'tool_policies':{'echo':'confirm'},'timeout_seconds':5}
        self.app.runtime.config=replace(config(self.root),mcp_enabled=True,mcp_servers={'demo':server})
        self.app.runtime.approval_timeout=5
        effects=[response(calls=[call('mcp','mcp__demo__echo','{"message":"web approved"}')]),response('MCP 完成')]
        fake=N(chat=N(completions=N(create=AsyncMock(side_effect=effects))),close=AsyncMock())
        self.app.runtime.client_factory=lambda _:fake
        c=await self.new();await self.post(f'conversations/{c}/messages',{'message':'MCP'});conv=self.app.runtime.conversations[c];p=await self.wait_pending(conv)
        self.assertEqual(p['kind'],'mcp');await self.post(f'conversations/{c}/approval',{'id':p['id'],'allow':True});await conv.task
        event=next(e for e in conv.events if e['type']=='tool_finished');self.assertTrue(event['success']);self.assertEqual(conv.status,'completed')

    async def test_real_plan_events(self):
        effects=[response(calls=[call('p','create_plan','{"steps":["查看结构","读取实现"]}')]),
            response(calls=[call('s1','update_plan','{"step":1,"status":"in_progress"}')]),
            response(calls=[call('ls','list_files','{"path":"."}')]),
            response(calls=[call('s2','update_plan','{"step":1,"status":"completed"}')]),
            response(calls=[call('s3','update_plan','{"step":2,"status":"in_progress"}')]),
            response(calls=[call('rd','read_file','{"path":"value.py"}')]),
            response(calls=[call('s4','update_plan','{"step":2,"status":"completed"}')]),response('计划已执行')]
        fake=N(chat=N(completions=N(create=AsyncMock(side_effect=effects))),close=AsyncMock());self.app.runtime.client_factory=lambda _:fake
        state=await self.run_chat();event=[e for e in state['events'] if e['type']=='tool_finished'][-1]
        self.assertEqual([s['status'] for s in event['plan']],['completed','completed']);self.assertTrue(all(s['verified'] for s in event['plan']))

    async def test_network_start_sse_authenticated(self):
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();port=sock.getsockname()[1]
        app=create_app(config(self.root),port=port,client_factory=self.factory)
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='critical',access_log=False,lifespan='off'))
        task=asyncio.create_task(server.serve(sockets=[sock]))
        try:
            for _ in range(100):
                if server.started:break
                await asyncio.sleep(.01)
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}') as http:
                await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'Origin':f'http://127.0.0.1:{port}','X-Mybot-CSRF':boot['csrf']}
                c=(await http.post('/api/conversations',json={},headers=headers)).json()['id']
                await http.post(f'/api/conversations/{c}/messages',json={'message':'你好'},headers=headers);await app.runtime.conversations[c].task
                async with http.stream('GET',f'/api/conversations/{c}/events') as stream:
                    self.assertEqual(stream.status_code,200);self.assertIn('text/event-stream',stream.headers['content-type'])
                    data=[]
                    async for line in stream.aiter_lines():
                        if line.startswith('data: '):
                            data.append(json.loads(line[6:]))
                            if data[-1]['type']=='message_completed':break
                    self.assertEqual(data[0]['type'],'message_started');self.assertEqual(data[-1]['type'],'message_completed')
                http.cookies.clear();self.assertEqual((await http.get(f'/api/conversations/{c}/events')).status_code,403)
        finally:server.should_exit=True;await task;await app.runtime.close()


def check_web_ui():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WebChecks))
    if not result.wasSuccessful():raise AssertionError('web checks failed')
    return result.testsRun


def serve():
    with tempfile.TemporaryDirectory(prefix='mybot-web-browser-') as tmp:
        root=Path(tmp).resolve();init(root)
        cfg=config(root,True)
        if '--plain' in sys.argv: cfg=replace(cfg,coding_autonomy={},coding_git_workflow={})
        app=create_app(cfg,port=8877,client_factory=SyntheticClient,approval_timeout=180)
        print('OFFLINE SYNTHETIC ACCEPTANCE ONLY — real AgentLoop, disposable workspace, zero model HTTP',flush=True)
        uvicorn.run(app,host='127.0.0.1',port=8877,access_log=False,log_level='warning',timeout_graceful_shutdown=3)


if __name__=='__main__':
    if '--serve' in sys.argv:serve()
    else:check_web_ui()
