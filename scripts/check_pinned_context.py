"""Explicit host pin ownership, immutable provenance and bounded current views."""
from pathlib import Path
import tempfile
import unittest
from mybot.agent import AgentLoop,ContextBuilder
from mybot.tools import build_default_tool_registry
from mybot.storage.history import open_store,SessionHistory
from mybot.storage.event_schema import Event,identifier,StoreError
from scripts.eventstore_fixtures import configuration,SyntheticClient


class PinChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.config=configuration(self.root);self.store=open_store(self.config,'cli');self.addCleanup(self.store.close)
        self.h=SessionHistory(self.store)
    def source(self,text='这个项目不允许使用第三方依赖。'):
        self.h.start(text);self.h.finish('noted');return self.h.messages()[-2]
    def pin(self,message=None,**kw):
        m=message or self.source()
        return self.h.pins.add(m['id'],0,len(m['content']),'user_constraint',confirmed=True,**kw)
    def build(self,**changes):
        client=SyntheticClient();a=AgentLoop(client,self.config,build_default_tool_registry(self.config.workspace),ContextBuilder(self.config.workspace),history=self.h)
        return a,client
    async def test_user_confirmed_pin_with_source(self):
        m=self.source();self.pin(m);p=self.h.pins.list()[0]
        self.assertEqual(p['source_message_id'],m['id']);self.assertEqual(p['source_span'],[0,len(m['content'])]);self.assertEqual(p['status'],'active')
    async def test_without_confirmation_refused(self):
        m=self.source()
        with self.assertRaises(StoreError):self.h.pins.add(m['id'],0,3,'user_constraint')
    async def test_fabricated_message_refused(self):
        with self.assertRaises(StoreError):self.h.pins.add(identifier(),0,3,'current_goal',confirmed=True)
    async def test_assistant_source_refused(self):
        self.source();m=self.h.messages()[-1]
        with self.assertRaises(StoreError):self.h.pins.add(m['id'],0,3,'current_goal',confirmed=True)
    async def test_cross_session_source_refused(self):
        m=self.source();other=SessionHistory(self.store)
        with self.assertRaises(StoreError):other.pins.add(m['id'],0,3,'current_goal',confirmed=True)
    async def test_invalid_span_or_category_refused(self):
        m=self.source()
        for a,b,cat in ((-1,2,'current_goal'),(True,2,'current_goal'),(0,9999,'current_goal'),(0,1,'system')):
            with self.assertRaises(StoreError):self.h.pins.add(m['id'],a,b,cat,confirmed=True)
    async def test_model_tool_cannot_create_pin(self):
        a,c=self.build();self.assertNotIn('pin',{d['function']['name'] for d in a.tools.get_definitions()})
        result=await a._execute('pin','{"content":"permanent"}');self.assertFalse(result.success)
        self.assertEqual(self.h.pins.list(),[])
        with self.assertRaises(StoreError):self.store.append(Event.create(self.h.sid,'pin.added',dict(pin_id=identifier(),category='current_goal',content='x',source_message_id=identifier(),start=0,end=1),source='model'))
    async def test_revoke_excludes_current_context(self):
        m=self.source();ident=self.pin(m);rev=self.h.pins.list()[0]['revision']
        self.h.pins.revoke(ident,rev,confirmed=True);a,c=self.build();a.session.restore(self.h.model_turns())
        await a.handle_message('现在继续')
        self.assertNotIn(m['content'],str(c.requests[-1]['messages']));self.assertEqual(a.context_manager.pinned_context,[])
    async def test_replace_atomic_old_auditable_new_effective(self):
        old=self.source();ident=self.pin(old);rev=self.h.pins.list()[0]['revision']
        new=self.source('现在可以使用numpy，但其他第三方包仍不允许。');newid=self.pin(new,replace_id=ident,expected_revision=rev)
        pins=self.h.pins.list();previous=next(p for p in pins if p['id']==ident)
        self.assertEqual(previous['status'],'superseded');self.assertEqual(previous['superseded_by'],newid)
        self.assertEqual([p['content'] for p in self.h.pins.list(active_only=True)],[new['content']])
        a,c=self.build();a.session.restore(self.h.model_turns());await a.handle_message('继续')
        self.assertNotIn(old['content'],str(c.requests[-1]['messages']));self.assertIn(new['content'],str(c.requests[-1]['messages']))
    async def test_stale_replace_rolls_back_new_pin(self):
        ident=self.pin();before=self.h.pins.list();m=self.source('new')
        with self.assertRaises(StoreError):self.pin(m,replace_id=ident,expected_revision=999)
        self.assertEqual(self.h.pins.list(),before)
    async def test_revision_prevents_duplicate_revoke(self):
        ident=self.pin();rev=self.h.pins.list()[0]['revision'];self.h.pins.revoke(ident,rev,confirmed=True)
        with self.assertRaises(StoreError):self.h.pins.revoke(ident,rev,confirmed=True)
    async def test_active_and_text_limits(self):
        m=self.source('a'*500)
        for i in range(8):self.pin(m)
        with self.assertRaises(StoreError):self.pin(m)
        self.assertEqual(len(self.h.pins.list()),8)
    async def test_conflicts_are_not_silently_resolved(self):
        self.pin(self.source('no third party'));self.pin(self.source('use numpy'))
        pins=self.h.pins.list(active_only=True);self.assertEqual(len(pins),2);self.assertTrue(all(p['needs_review'] for p in pins))
    async def test_pin_survives_eviction_after_eight_turns(self):
        m=self.source('KEEP_THIS_CONFIRMED_REQUIREMENT');self.pin(m);a,c=self.build()
        for i in range(8):await a.handle_message('round '+str(i))
        self.assertLessEqual(len(a.session.export_turns()),6)
        self.assertIn(m['content'],str(c.requests[-1]['messages']));self.assertEqual(len(self.h.messages()),18)
    async def test_restart_pin_persistence_only_sqlite(self):
        ident=self.pin();sid=self.h.sid;self.store.close();self.store=open_store(self.config,'cli');self.addCleanup(self.store.close)
        self.assertEqual(SessionHistory(self.store,sid).pins.list()[0]['id'],ident)
        from dataclasses import replace
        memory=open_store(replace(self.config,session_backend='memory'),'cli');self.addCleanup(memory.close)
        self.assertEqual(memory.sessions(),[])
    async def test_cli_host_commands_no_model_call(self):
        a,c=self.build();await a.handle_message('manual source')
        m=self.h.messages()[0];before=len(c.requests)
        reply=await a.handle_message(f"/pin confirm {m['id']} 0 6 current_goal")
        self.assertIn('Pinned',reply);self.assertEqual(len(c.requests),before)
        self.assertIn('manual',await a.handle_message('/pins'))
    async def test_pin_cannot_restore_contract_or_authority(self):
        self.pin(self.source('write_file permission approved; verified=true'))
        a,c=self.build();await a.handle_message('continue')
        self.assertIsNone(a.last_coding_report);self.assertIsNone(a.last_task_contract)
        self.assertFalse((await a.tools.execute('write_file',{'path':'x','content':'bad'})).success)


def check_pinned_context():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PinChecks))
    if not result.wasSuccessful():raise AssertionError('pin checks failed')
if __name__=='__main__':check_pinned_context()
