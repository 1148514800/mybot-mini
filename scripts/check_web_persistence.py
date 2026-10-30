"""Real ASGI endpoints and restart with SQLite; browser acceptance is separate."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx
from mybot.web.server import create_app
from mybot.storage.event_schema import StoreError
from scripts.eventstore_fixtures import configuration,SyntheticClient


class WebPersistenceChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.config=configuration(self.root);self.clients=[];self.apps=[];self.https=[]
        await self.open()
    async def asyncTearDown(self):
        for http in self.https:await http.aclose()
        for app in self.apps:
            if not app.runtime.closed:await app.runtime.close()
    async def open(self,factory=None):
        def client_factory(cfg):c=SyntheticClient();self.clients.append(c);return c
        self.app=create_app(self.config,client_factory=factory or client_factory)
        self.apps.append(self.app);self.http=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://127.0.0.1:8765');self.https.append(self.http)
        await self.http.get('/');b=(await self.http.get('/api/bootstrap')).json();self.headers={'Origin':'http://127.0.0.1:8765','X-Mybot-CSRF':b['csrf']}
    async def post(self,path,body=None):return await self.http.post('/api/'+path,json=body or {},headers=self.headers)
    async def new(self):
        r=await self.post('conversations');self.assertEqual(r.status_code,201);return r.json()['id']
    async def chat(self,sid,text='hello'):
        r=await self.post(f'conversations/{sid}/messages',{'message':text});self.assertEqual(r.status_code,202)
        await self.app.runtime.conversations[sid].task
        return (await self.http.get('/api/conversations/'+sid)).json()
    async def test_restart_messages_title_id_status(self):
        sid=await self.new();before=await self.chat(sid,'first title');await self.chat(sid,'next')
        await self.app.runtime.close();await self.open()
        b=(await self.http.get('/api/bootstrap')).json();self.assertTrue(b['persistence'])
        self.assertEqual(b['conversations'][0]['id'],sid)
        state=(await self.http.get('/api/conversations/'+sid)).json()
        self.assertEqual(len(state['messages']),4);self.assertEqual(state['title'],before['title']);self.assertEqual(state['status'],'completed')
        self.assertIsNone(state['approval']);self.assertIsNone(state['report'])
    async def test_select_multiple_safe_old_conversations(self):
        first=await self.new();second=await self.new();await self.chat(first,'first');await self.chat(second,'second')
        await self.app.runtime.close();await self.open();await self.chat(first,'continue first')
        messages=(await self.http.get('/api/conversations/'+second)).json()['messages']
        self.assertEqual(len(messages),2);self.assertEqual(messages[0]['content'],'second')
    async def test_early_history_not_lost_at_six_turns(self):
        sid=await self.new()
        for i in range(9):await self.chat(sid,'round '+str(i))
        state=(await self.http.get('/api/conversations/'+sid)).json()
        self.assertEqual(len(state['messages']),18)
        self.assertLessEqual(len(self.app.runtime.conversations[sid].session.export_turns()),6)
        first=state['messages'][0]['sequence'];page=await self.http.get(f'/api/conversations/{sid}/history?before={first+2}')
        self.assertEqual(page.status_code,200);self.assertEqual(page.json()['messages'][0]['content'],'round 0')
    async def test_pin_host_api_and_restart(self):
        sid=await self.new();state=await self.chat(sid,'no extra dependencies');m=state['messages'][0]
        r=await self.post(f'conversations/{sid}/pins',{'message_id':m['id'],'start':0,'end':len(m['content']),'category':'user_constraint','confirmed':True});self.assertEqual(r.status_code,200)
        await self.app.runtime.close();await self.open();state=await self.chat(sid,'next')
        self.assertEqual(len(state['pins']),1);self.assertIn('no extra dependencies',self.clients[-1].requests[-1]['messages'][1]['content'])
    async def test_forged_source_and_numeric_confirm_rejected(self):
        sid=await self.new();state=await self.chat(sid);m=state['messages'][0]
        for values in ({'message_id':'a'*32,'confirmed':True},{'message_id':m['id'],'confirmed':1}):
            r=await self.post(f'conversations/{sid}/pins',{'start':0,'end':2,'category':'current_goal',**values});self.assertEqual(r.status_code,409)
        r=await self.post(f'conversations/{sid}/delete',{'confirmed':1});self.assertEqual(r.status_code,409)
    async def test_delete_removes_normal_interfaces_and_database(self):
        sid=await self.new();await self.chat(sid,'DELETE_WEB_SENTINEL_71586')
        self.assertEqual((await self.post(f'conversations/{sid}/delete',{'confirmed':True})).status_code,200)
        self.assertEqual((await self.http.get('/api/conversations/'+sid)).status_code,404)
        self.assertEqual((await self.http.get(f'/api/conversations/{sid}/history')).status_code,404)
        self.assertNotIn(b'DELETE_WEB_SENTINEL_71586',self.config.session_event_path.read_bytes())
        await self.app.runtime.close();await self.open();self.assertEqual(self.app.runtime.conversations,{})
    async def test_clear_is_not_durable_deletion(self):
        sid=await self.new();await self.chat(sid,'history retained');await self.post(f'conversations/{sid}/clear')
        c=self.app.runtime.conversations[sid]
        self.assertEqual(c.session.history(),[]);self.assertEqual(len(c.history.messages()),2)
        self.assertEqual(c.history.model_turns(),[])
    async def test_database_start_failure_sends_no_model(self):
        sid=await self.new()
        with patch.object(self.app.runtime.event_store,'append_many',side_effect=StoreError('synthetic_disk_full')):
            r=await self.post(f'conversations/{sid}/messages',{'message':'not stored'});self.assertEqual(r.status_code,503)
        self.assertEqual(self.clients,[]);self.assertEqual(self.app.runtime.conversations[sid].messages,[])
    async def test_user_committed_then_publication_failed_not_lost(self):
        sid=await self.new();c=self.app.runtime.conversations[sid];original=c.history.messages
        await self.http.get('/api/conversations/'+sid)
        with patch.object(c.history,'messages',side_effect=StoreError('read_failed')):
            r=await self.post(f'conversations/{sid}/messages',{'message':'durable user'});self.assertEqual(r.status_code,503)
        self.assertEqual(original()[0]['content'],'durable user');self.assertEqual(self.clients,[])
        self.assertEqual(c.history.status()['status'],'failed')
    async def test_finish_append_failure_is_not_saved_success(self):
        sid=await self.new();c=self.app.runtime.conversations[sid]
        with patch.object(c.history,'finish',side_effect=StoreError('write_failed')):
            state=await self.chat(sid)
        self.assertNotEqual(state['status'],'completed');self.assertEqual(len(c.history.messages()),1)
    async def test_sdk_exception_redacted_from_event_log(self):
        class Bad(SyntheticClient):
            async def create(self,**kw):raise RuntimeError('SDK_SECRET_74914 /Users/private/secret')
        await self.open(lambda cfg:Bad());sid=await self.new();state=await self.chat(sid,'safe user text')
        text=str(self.app.runtime.event_store.events(sid));self.assertNotIn('SDK_SECRET_74914',text);self.assertNotIn('/Users/',text)
        self.assertEqual(state['status'],'failed')
    async def test_cancelled_turn_remains_cancelled_after_restart(self):
        gate=asyncio.Event()
        class Slow(SyntheticClient):
            async def create(self,**kw):await gate.wait();return await super().create(**kw)
        await self.open(lambda cfg:Slow());sid=await self.new();await self.post(f'conversations/{sid}/messages',{'message':'wait'})
        await self.app.runtime.stop(self.app.runtime.conversations[sid]);await self.app.runtime.close();await self.open()
        self.assertEqual(self.app.runtime.conversations[sid].status,'cancelled')
    async def test_truncated_delivery_restores_as_truncated(self):
        from scripts.check_session import response
        class Short(SyntheticClient):
            async def create(self,**kw):r=response('partial');r.choices[0].finish_reason='length';return r
        await self.open(lambda cfg:Short());sid=await self.new();state=await self.chat(sid);self.assertEqual(state['status'],'output_truncated')
        await self.app.runtime.close();await self.open();self.assertEqual(self.app.runtime.conversations[sid].status,'output_truncated')
    async def test_cli_namespace_private_not_auto_loaded(self):
        from mybot.storage.history import open_store,SessionHistory
        engine=open_store(self.config,'cli');h=SessionHistory(engine);h.start('CLI_PRIVATE_8741');h.finish('private');engine.close()
        await self.app.runtime.close();await self.open();self.assertEqual(self.app.runtime.conversations,{})
    async def test_legacy_json_not_read_or_migrated_by_web(self):
        old=self.root/'old.json';old.write_text('old JSON preserved')
        with self.assertRaises(TypeError): replace(self.config,session_persist=True,session_path=old)
        self.config=replace(self.config,session_backend='memory')
        await self.open();sid=await self.new();await self.chat(sid)
        self.assertEqual(old.read_text(),'old JSON preserved');self.assertFalse((await self.http.get('/api/bootstrap')).json()['persistence'])
    async def test_external_process_delete_invalidates_cached_conversation(self):
        from mybot.storage.history import open_store
        sid=await self.new();await self.chat(sid,'external delete')
        other=open_store(self.config,'web');other.delete(sid);other.close()
        self.assertEqual((await self.http.get('/api/conversations/'+sid)).status_code,404)
        self.assertNotIn(sid,self.app.runtime.conversations)
    async def test_external_turn_invalidates_cached_report_and_approval(self):
        from mybot.storage.history import open_store,SessionHistory
        sid=await self.new();await self.chat(sid,'old')
        await self.http.get('/api/conversations/'+sid)
        c=self.app.runtime.conversations[sid];c.report={'state':'verified'};c.contract={'fake':'old'}
        other=open_store(self.config,'web');h=SessionHistory(other,sid);h.start('external new');h.finish('external reply');other.close()
        state=(await self.http.get('/api/conversations/'+sid)).json()
        self.assertEqual(state['messages'][-1]['content'],'external reply');self.assertIsNone(state['report']);self.assertIsNone(state['contract']);self.assertIsNone(state['approval'])
    async def test_external_context_clear_invalidates_local_model_history(self):
        from mybot.storage.history import open_store,SessionHistory
        sid=await self.new();await self.chat(sid,'older context');await self.http.get('/api/conversations/'+sid)
        c=self.app.runtime.conversations[sid];self.assertTrue(c.session.export_turns())
        other=open_store(self.config,'web');SessionHistory(other,sid).clear_context();other.close()
        await self.http.get('/api/conversations/'+sid)
        self.assertEqual(c.session.export_turns(),[]);self.assertEqual(len(c.messages),2)
    async def test_cli_history_commands_rejected_in_web_chat(self):
        sid=await self.new()
        for text in ('/session new','/delete-session confirm '+sid,'/pin confirm fake 0 1 current_goal'):
            r=await self.post(f'conversations/{sid}/messages',{'message':text});self.assertEqual(r.status_code,400)
        self.assertEqual(self.clients,[])
    async def test_removed_database_refuses_recreation_without_path_leak(self):
        sid=await self.new();path=self.config.session_event_path;path.unlink()
        response=await self.http.get('/api/conversations/'+sid)
        self.assertEqual(response.status_code,503);self.assertEqual(response.json(),{'error':'storage_failed'})
        self.assertNotIn(str(path),response.text);self.assertFalse(path.exists());self.assertEqual(self.clients,[])
    async def test_sync_storage_failure_returns_generic_503(self):
        sid=await self.new()
        with patch.object(self.app.runtime,'sync',side_effect=StoreError('PRIVATE_STORE_DETAIL')):
            r=await self.http.get('/api/conversations/'+sid)
        self.assertEqual(r.status_code,503);self.assertEqual(r.json(),{'error':'storage_failed'})
    async def test_output_truncation_never_overrides_uncertain_controller(self):
        async def uncertain(agent,text):
            agent.last_coding_report=dict(state='execution_uncertain',committed_patches=0,current_revision=0,tests_passed_after_last_patch=0)
            agent.last_runtime_report={'outcome':'output_truncated','output':{'status':'output_truncated'}}
            return 'synthetic partial reply'
        sid=await self.new()
        with patch('mybot.web.runtime.AgentLoop.handle_message',uncertain):state=await self.chat(sid)
        self.assertEqual(state['status'],'execution_uncertain')
        self.assertEqual(self.app.runtime.conversations[sid].history.status()['status'],'execution_uncertain')
        self.assertTrue(any(e['type']=='message_failed' for e in state['events']))
    async def test_cleanup_failure_persists_unsafe_boundary(self):
        class BadClose(SyntheticClient):
            async def close(self):raise RuntimeError('synthetic cleanup failure')
        await self.open(lambda cfg:BadClose());sid=await self.new();await self.chat(sid)
        self.assertEqual(self.app.runtime.conversations[sid].history.status()['status'],'execution_uncertain')
        await self.app.runtime.close();await self.open()
        self.assertEqual(self.app.runtime.conversations[sid].status,'execution_uncertain')
        self.assertTrue(self.app.runtime.cleanup_uncertain);self.assertIsNone(self.app.runtime.conversations[sid].report)
        self.assertEqual(len(self.app.runtime.conversations[sid].messages),1)
    async def test_default_memory_no_database_created(self):
        unused=self.root/'unused/events.db';self.config=replace(self.config,session_backend='memory',session_event_path=unused)
        await self.open();sid=await self.new();await self.chat(sid);self.assertFalse(unused.exists())


def check_web_persistence():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WebPersistenceChecks))
    if not result.wasSuccessful():raise AssertionError('web persistence checks failed')
if __name__=='__main__':check_web_persistence()
