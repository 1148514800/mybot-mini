"""Pins participate in actual request budgets, never system authority or summary memory."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from mybot.agent import AgentLoop,ContextBuilder
from mybot.agent.context_manager import ContextManager,ContextBudgetError
from mybot.agent.planning import Plan
from mybot.agent.pinned_context import PIN_LABEL
from mybot.agent.token_counter import TokenCounter
from mybot.tools import build_default_tool_registry
from mybot.storage.history import SessionHistory,open_store
from scripts.eventstore_fixtures import configuration,SyntheticClient


class ProjectionChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.config=configuration(self.root);self.store=open_store(self.config,'cli');self.addCleanup(self.store.close);self.h=SessionHistory(self.store)
    def add(self,text='CONFIRMED_USER_RULE'):
        self.h.start(text);self.h.finish('ack');m=self.h.messages()[-2]
        self.h.pins.add(m['id'],0,len(m['content']),'user_constraint',confirmed=True)
        return self.h.pins.list(active_only=True)[0]
    def manager(self,config=None):
        manager=ContextManager(config or self.config);manager.pinned_context=self.h.pins.list(active_only=True);return manager
    async def test_pin_is_user_reference_not_system(self):
        p=self.add();manager=self.manager();messages=ContextBuilder(self.config.workspace).build_messages('next')
        view,stats=manager.prepare(messages,[],[],Plan())
        self.assertEqual(view[1]['role'],'user');self.assertTrue(view[1]['content'].startswith(PIN_LABEL))
        self.assertNotIn(p['content'],view[0]['content']);self.assertIn(p['pin_id'],stats['pins_included'])
    async def test_pin_budget_can_omit_without_silent_inclusion(self):
        self.add('z'*512);messages=[{'role':'system','content':'rule'},{'role':'user','content':'current'}]
        manager=self.manager(replace(self.config,context_max_chars=500))
        view,stats=manager.prepare(messages,[],[],Plan())
        self.assertEqual(stats['pins_included'],[]);self.assertEqual(len(stats['pins_omitted']),1)
        self.assertTrue(stats['pinned_context_incomplete']);self.assertNotIn('z'*512,str(view))
    async def test_pin_with_disabled_compaction_still_enters_and_measured(self):
        p=self.add();cfg=replace(self.config,context_enabled=False);client=SyntheticClient()
        a=AgentLoop(client,cfg,build_default_tool_registry(cfg.workspace),ContextBuilder(cfg.workspace),history=self.h)
        await a.handle_message('next');self.assertIn(p['content'],str(client.requests[0]['messages']))
        self.assertGreater(a.last_runtime_report['context']['request_utf8_bytes'],len(p['content']))
    async def test_estimate_output_reserve_and_window_enforced(self):
        self.add('p'*300);cfg=replace(self.config,max_completion_tokens=800,context_token_budget={'mode':'estimate','input_limit':2000,'model_windows':{'offline/synthetic':1800}})
        manager=self.manager(cfg);messages=[{'role':'system','content':'rules'},{'role':'user','content':'new request'}]
        view,stats=manager.prepare(messages,[],[],Plan());measure=TokenCounter.enforce(cfg,TokenCounter.request(cfg,view,[]))
        self.assertLessEqual(measure['estimated_input_tokens']+800,1800)
        self.assertEqual(stats['pins_included'],[]);self.assertTrue(stats['pins_omitted'])
    async def test_legacy_configured_window_cannot_be_bypassed_by_pins(self):
        self.add('x'*200);cfg=replace(self.config,context_enabled=False,max_completion_tokens=800,context_token_budget={'model_windows':{'offline/synthetic':1000}})
        messages=[{'role':'system','content':'x'*1000},{'role':'user','content':'new'}]
        with self.assertRaises(ContextBudgetError):self.manager(cfg).prepare(messages,[],[],Plan())
    async def test_pin_priority_over_old_history(self):
        p=self.add();cfg=replace(self.config,context_max_chars=2000,context_recent_turns=0)
        turns=[[{'role':'user','content':'old'*2000},{'role':'assistant','content':'reply'*1000}]]
        messages=[{'role':'system','content':'rules'},*turns[0],{'role':'user','content':'current'}]
        view,stats=self.manager(cfg).prepare(messages,[],turns,Plan())
        self.assertIn(p['content'],str(view));self.assertTrue(stats['history_turns_omitted'])
    async def test_protocol_groups_preserved_with_pins(self):
        self.add();turn=[{'role':'user','content':'past'},{'role':'assistant','content':None,'tool_calls':[{'id':'t','type':'function','function':{'name':'read_file','arguments':'{}'}}]},{'role':'tool','tool_call_id':'t','content':'observed'},{'role':'assistant','content':'done'}]
        messages=[{'role':'system','content':'rules'},*turn,{'role':'user','content':'next'}]
        view,_=self.manager().prepare(messages,[],[turn],Plan())
        from scripts.check_session import assert_pairs
        assert_pairs(self,view)
    async def test_semantic_failure_does_not_delete_or_create_pins(self):
        self.add();before=self.h.pins.list();cfg=replace(self.config,context_max_chars=6000,context_compaction={'mode':'semantic','allow_extra_requests':True,'input_tokens':30000})
        from scripts.modernization_fixtures import Client
        from scripts.check_session import response
        c=Client(summary=lambda request:None)
        async def bad_summary(request):return response('bad summary JSON')
        c.summary=bad_summary
        a=AgentLoop(c,cfg,build_default_tool_registry(cfg.workspace),ContextBuilder(cfg.workspace),history=self.h)
        a.session.restore([[{'role':'user','content':'past '*3000},{'role':'assistant','content':'old'}]])
        await a.handle_message('new')
        self.assertEqual(self.h.pins.list(),before)
        self.assertTrue(any((m.get('content') or '').startswith(PIN_LABEL) for r in c.requests for m in r['messages']))
    async def test_withdrawal_omits_whole_turn_not_fake_tool_result(self):
        p=self.add('obsolete requirement');self.h.pins.revoke(p['id'],p['revision'],confirmed=True)
        turn=[{'role':'user','content':'obsolete requirement'},{'role':'assistant','content':'old'}]
        self.assertEqual(self.h.context_turns([turn]),[])
        self.assertIn('obsolete requirement',str(self.h.messages()))
    async def test_pins_query_and_recent_history_indexed(self):
        self.add()
        with self.store.connection() as db:
            pin_plan=str([tuple(r) for r in db.execute("EXPLAIN QUERY PLAN SELECT * FROM pins WHERE session_id=? AND status='active' ORDER BY revision",(self.h.sid,))])
            recent_plan=str([tuple(r) for r in db.execute('EXPLAIN QUERY PLAN SELECT * FROM turns WHERE session_id=? ORDER BY sequence DESC LIMIT 6',(self.h.sid,))])
        self.assertIn('active_pins',pin_plan);self.assertIn('recent_turns',recent_plan)


def check_context_projection():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProjectionChecks))
    if not result.wasSuccessful():raise AssertionError('projection checks failed')
if __name__=='__main__':check_context_projection()
