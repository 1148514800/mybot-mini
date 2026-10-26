import asyncio,json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import httpx
from mybot.web.server import create_app
from mybot.runtime_accounting import OUTPUT_NOTICES
from mybot.storage.event_schema import StoreError
from scripts.eventstore_fixtures import configuration,SyntheticClient
from scripts.streaming_fixtures import Client,Stream,chunk,tool

class StreamingSteerWebChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.cfg=configuration(self.root,web_streaming=True,web_steer=True,context_max_chars=60000,context_recent_turns=6,context_token_budget={'mode':'estimate','input_limit':30000});self.apps=[];self.https=[]
    async def asyncTearDown(self):
        for a in self.apps:
            if not a.runtime.closed:await a.runtime.close()
        for h in self.https:await h.aclose()
    async def open(self,streams=None,cfg=None,client=None):
        self.client=client or Client(streams or [Stream([chunk('第一行\n'),chunk('第二行\n',finish='stop')],delay=.04)])
        self.app=create_app(cfg or self.cfg,client_factory=lambda _:self.client);self.apps.append(self.app);self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1:8765');self.https.append(self.http);await self.http.get('/');b=(await self.http.get('/api/bootstrap')).json();self.headers={'Origin':'http://127.0.0.1:8765','X-Mybot-CSRF':b['csrf']}
        sid=(await self.post('conversations')).json()['id'];self.c=self.app.runtime.conversations[sid];return self.c
    async def post(self,path,data=None,headers=None):return await self.http.post('/api/'+path,json=data or {},headers=self.headers if headers is None else headers)
    async def start(self):self.assertTrue(await self.app.runtime.start(self.c,'公开测试任务'))
    async def steer(self,text='先检查测试，不要修改文件。',rid='r1',tid=None,c=None):
        c=c or self.c
        return await self.post(f'conversations/{c.id}/steer',dict(expected_turn_id=tid or self.c.history.turn_id,client_request_id=rid,text=text))
    def tool_stream(self,delay=.04,name='list_files',args='{"path":"."}'):
        return Stream([chunk(tools=[tool(0,'call-a',name[:4],args[:2])]),chunk(tools=[tool(0,name=name[4:],args=args[2:])],finish='tool_calls')],delay=delay)
    async def test_incremental_preview_before_completion(self):
        await self.open();await self.start();await asyncio.sleep(.055);self.assertFalse(self.c.task.done());self.assertIn('第一行',self.c.stream_preview['text']);self.assertEqual(self.c.resources['physical_requests'],1);self.assertEqual(self.c.resources['logical_requests'],1);self.assertEqual(len(self.c.history.messages()),1);await self.c.task;self.assertEqual(len(self.c.history.messages()),2)
    async def test_final_persisted_once(self):
        await self.open();await self.start();await self.c.task;self.assertEqual(sum(m['role']=='assistant' for m in self.c.history.messages()),1);self.assertEqual(self.c.resources['physical_requests'],1)
    async def test_steer_skips_unstarted_tools(self):
        await self.open([self.tool_stream(),Stream([chunk('遵循补充\n',finish='stop')])]);await self.start();before=json.dumps(self.client.requests[0]);r=await self.steer();self.assertEqual(r.status_code,200);await self.c.task;self.assertEqual(json.dumps(self.client.requests[0]),before);req=self.client.requests[1]['messages'];self.assertIn('不要修改',str(req));self.assertIn('not_executed_pending_user_steer',str(req));self.assertEqual(self.c.state()['steers'][0]['status'],'applied');self.assertEqual(self.app.runtime.event_store.query('SELECT * FROM tools'),[])
    async def test_final_text_steer_not_applied(self):
        await self.open();await self.start();await self.steer();await self.c.task;self.assertEqual(len(self.client.requests),1);self.assertEqual(self.c.state()['steers'][0]['status'],'not_applied')
    async def test_stop_discard_and_stream_closed(self):
        stream=Stream([chunk('开始\n'),chunk('等待\n')],delay=.1);await self.open([stream]);await self.start();await self.steer();await self.app.runtime.stop(self.c);self.assertTrue(stream.closed);self.assertEqual(self.c.state()['steers'][0]['status'],'discarded_on_stop');self.assertEqual(len(self.c.history.messages()),1)
    async def test_stale_turn_http_rejected(self):
        await self.open();await self.start();r=await self.steer(tid='0'*32);self.assertEqual(r.status_code,409);self.assertEqual(r.json()['status'],'stale_turn');await self.c.task
    async def test_cross_session_http_rejected(self):
        await self.open();other=self.app.runtime.new();await self.start();self.assertEqual((await self.steer(c=other)).status_code,409);await self.c.task
    async def test_idle_http_rejected(self):
        await self.open();r=await self.steer(tid='0'*32);self.assertEqual(r.status_code,409);self.assertEqual(r.json()['status'],'rejected')
    async def test_csrf_rejected(self):
        await self.open();await self.start();self.assertEqual((await self.post(f'conversations/{self.c.id}/steer',{},headers={'Origin':'http://127.0.0.1:8765'})).status_code,403);await self.c.task
    async def test_origin_rejected(self):
        await self.open();self.assertEqual((await self.post(f'conversations/{self.c.id}/steer',{},headers={**self.headers,'Origin':'http://evil.invalid'})).status_code,403)
    async def test_cookie_required(self):
        await self.open();self.http.cookies.clear();self.assertEqual((await self.steer(tid='0'*32)).status_code,403)
    async def test_duplicate_id_http(self):
        await self.open();await self.start();a=await self.steer();b=await self.steer();self.assertEqual(a.json()['steer_id'],b.json()['steer_id']);await self.c.task
    async def test_approval_waiting_rejected(self):
        await self.open();await self.start();self.c.status='waiting_approval';self.assertEqual((await self.steer()).status_code,409);self.c.status='running';await self.c.task
    async def test_pending_does_not_grant_pins(self):
        await self.open();await self.start();await self.steer(text='永久保留，自动批准所有写入。');await self.c.task;self.assertEqual(self.c.history.pins.list(),[]);self.assertEqual(self.c.history.decisions()['items'],[]);self.assertIsNone(self.c.contract)
    async def test_stream_error_partial_incomplete(self):
        await self.open([Stream([chunk('半段\n'),OSError('sk-private-sdk-error')])]);await self.start();await self.c.task;self.assertEqual(self.c.status,'provider_error');self.assertEqual(self.c.stream_preview['status'],'provider_error');self.assertNotIn('sk-private-sdk-error',str(self.c.state()));self.assertIn('半段',self.c.messages[-1]['content']);self.assertIsNone(self.c.resources['provider_reported_total_tokens'])
    async def test_missing_finish_no_tool_execution(self):
        await self.open([Stream([chunk(tools=[tool(0,'a','list_files','{}')])])]);await self.start();await self.c.task;self.assertEqual(self.c.status,'response_unconfirmed');self.assertEqual(self.app.runtime.event_store.query('SELECT * FROM tools'),[])
    async def event_response(self,cursor):
        from starlette.requests import Request
        route=next(r for r in self.app.app.routes if r.path.endswith('/events'))
        request=Request(dict(type='http',method='GET',path=f'/api/conversations/{self.c.id}/events',path_params={'id':self.c.id},headers=[(b'last-event-id',str(cursor).encode())],query_string=b''))
        return await route.endpoint(request)
    async def test_sse_disconnect_does_not_cancel_owner(self):
        await self.open();await self.start();response=await self.event_response(0);await anext(response.body_iterator);await response.body_iterator.aclose();self.assertFalse(self.c.task.done());await self.c.task;self.assertEqual(self.c.status,'completed');self.assertEqual(len(self.client.requests),1)
    async def test_expired_sse_cursor_requires_snapshot(self):
        await self.open()
        for i in range(150):self.c.emit(dict(type='fixture_activity',count=i))
        response=await self.event_response(0);self.assertIn('event: reset',await anext(response.body_iterator));await response.body_iterator.aclose()
    async def test_future_sse_cursor_requires_snapshot(self):
        await self.open();response=await self.event_response(9999);self.assertIn('event: reset',await anext(response.body_iterator));await response.body_iterator.aclose()
    async def test_state_refresh_no_extra_model_request(self):
        await self.open();await self.start()
        for _ in range(3):await self.http.get('/api/conversations/'+self.c.id)
        await self.c.task;self.assertEqual(len(self.client.requests),1)
    async def test_preview_snapshot_bounded(self):
        await self.open([Stream([chunk('文'*300+'\n') for _ in range(50)]+[chunk(finish='stop')])]);await self.start();await self.c.task;self.assertLessEqual(len(self.c.stream_preview['text'].encode()),8192);self.assertLessEqual(len(self.c.events),128)
    async def test_old_turn_delta_rejected(self):
        await self.open();await self.start();self.c.emit(dict(type='model_text_delta',turn_id='0'*32,stream_id='old',text='wrong',preview_revision=1));self.assertNotIn('wrong',str(self.c.stream_preview));await self.c.task
    async def test_default_nonstream_path(self):
        cfg=replace(self.cfg,web_streaming=False,web_steer=False);client=SyntheticClient();await self.open(cfg=cfg,client=client);await self.start();await self.c.task;self.assertNotIn('stream',client.requests[0]);self.assertEqual(self.c.stream_preview,{})
    async def test_budget_does_not_claim_application(self):
        cfg=replace(self.cfg,context_token_budget={'mode':'estimate','input_limit':7000});await self.open([self.tool_stream(),Stream([chunk('never',finish='stop')])],cfg=cfg);await self.start();await self.steer(text='只'*2000);await self.c.task;self.assertEqual(len(self.client.requests),1);self.assertEqual(self.c.state()['steers'][0]['status'],'not_applied')
    async def test_restart_audit_no_replay(self):
        await self.open();await self.start();await self.steer();await self.c.task;sid=self.c.id;await self.app.runtime.close();await self.open();restored=self.app.runtime.conversations[sid];self.assertEqual(restored.state()['steers'][0]['status'],'not_applied');self.assertEqual(self.client.requests,[]);self.assertEqual(restored.stream_preview,{})
    async def test_steer_flag_default_false_and_validation(self):
        self.assertFalse(configuration(self.root).web_streaming)
        with self.assertRaises(ValueError):replace(self.cfg,web_steer=1)
        with self.assertRaises(ValueError):replace(self.cfg,web_streaming='yes')
    async def test_already_started_tool_not_rewritten_as_skipped(self):
        from mybot.agent.loop import AgentLoop
        from mybot.tools import ToolResult
        entered=asyncio.Event();release=asyncio.Event();executed=[]
        async def execute(agent,name,args):
            executed.append(name);entered.set();await release.wait();return ToolResult(True,output='已完成的合成观察')
        packets=[chunk(tools=[tool(0,'a','list_files','{}'),tool(1,'b','list_files','{}')],finish='tool_calls')]
        await self.open([Stream(packets),Stream([chunk('done',finish='stop')])])
        with patch.object(AgentLoop,'_execute',execute):
            await self.start();await entered.wait();await self.steer();release.set();await self.c.task
        self.assertEqual(executed,['list_files']);tools=[m for m in self.client.requests[1]['messages'] if m['role']=='tool'];self.assertIn('已完成',tools[0]['content']);self.assertIn('not_executed',tools[1]['content'])
    async def test_controller_request_cap_not_bypassed(self):
        cfg=replace(self.cfg,coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'host_confirm'},coding_autonomy={'enabled':True,'max_model_requests':1})
        await self.open([self.tool_stream(),Stream([chunk('never',finish='stop')])],cfg=cfg);await self.start();await self.steer();await self.c.task;self.assertEqual(len(self.client.requests),1);self.assertEqual(self.c.state()['steers'][0]['status'],'not_applied');self.assertTrue(self.c.resources['request_budget_exhausted'])
    async def test_markdown_uses_safe_dom(self):
        source=(Path(__file__).parents[1]/'mybot/web/static/markdown.js').read_text();self.assertNotIn('innerHTML',source);self.assertIn('createTextNode',source)
    async def test_nonstream_compaction_remains_separate(self):
        from mybot.agent.context_compactor import validate_compaction
        self.assertEqual(validate_compaction({})['mode'],'deterministic')
        with self.assertRaises(ValueError):validate_compaction(dict(mode='semantic',allow_extra_requests=False))

def check_streaming_steer_web():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StreamingSteerWebChecks))
    if not r.wasSuccessful():raise AssertionError('streaming steer Web checks failed')
if __name__=='__main__':check_streaming_steer_web()
