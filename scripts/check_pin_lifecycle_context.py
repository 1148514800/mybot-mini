"""Synthetic AgentLoop request tests, not provider semantics/Judge scores."""
from pathlib import Path
from dataclasses import replace
import tempfile,unittest,json,contextlib,io
from mybot.agent import AgentLoop,ContextBuilder
from mybot.agent.context_manager import ContextManager,ContextBudgetError
from mybot.agent.context_compactor import ContextCompactor,FIELDS
from mybot.agent.planning import Plan
from mybot.agent.pinned_context import PIN_LABEL,render
from mybot.storage.context_projection import ASSISTANT_LABEL,ASSISTANT_OMITTED,LIFECYCLE_LABEL
from mybot.tools import build_default_tool_registry
from scripts.eventstore_fixtures import SyntheticClient
from scripts.source_projection_fixtures import source_fixture,stored,pin,revoke,OLD,NEW,UNITS
from scripts.check_session import response

class LifecycleChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.cfg,self.store,self.h,self.turns,self.new=source_fixture(self.tmp.name);self.addCleanup(self.store.close)
    def agent(self,cfg=None):
        client=SyntheticClient();cfg=cfg or self.cfg;a=AgentLoop(client,cfg,build_default_tool_registry(cfg.workspace),ContextBuilder(cfg.workspace),history=self.h);a.session.restore(self.turns);return a,client
    async def test_actual_request_five_facts_after_replace(self):
        a,c=self.agent();await a.handle_message('目前命名要求？');request=c.requests[-1];self.assertTrue(all(x in str(request) for x in UNITS));self.assertNotIn(OLD,str(request));self.assertIn(NEW,str(request));self.assertEqual(len(c.requests),1);self.assertEqual(a.last_runtime_report['physical_requests'],1)
    async def test_actual_request_five_facts_after_revoke(self):
        revoke(self.h,self.new);a,c=self.agent();await a.handle_message('命名已撤销，继续讨论。');self.assertTrue(all(x in str(c.requests[-1]) for x in UNITS));self.assertNotIn(OLD,str(c.requests));self.assertNotIn(NEW,str(c.requests));self.assertFalse(a.context_manager.pinned_context)
    async def test_lifecycle_empty_category_explicit(self):
        revoke(self.h,self.new);self.h.context_turns(self.turns);m=self.h.lifecycle_reference[0];self.assertEqual(m['role'],'user');d=json.loads(m['content'][len(LIFECYCLE_LABEL):]);self.assertEqual(d['active_by_category']['user_constraint'],[]);self.assertEqual({p['status'] for p in d['inactive']},{'revoked','superseded'});self.assertNotIn(OLD,m['content'])
    async def test_exact_assistant_echo_is_omitted_not_rewritten(self):
        v=self.h.context_turns(self.turns);self.assertEqual(v[0][1]['content'],ASSISTANT_OMITTED);self.assertEqual(self.h.projection_diagnostics['omitted_assistant_messages'],1)
    async def test_semantic_paraphrase_unverified_not_claimed_cleared(self):
        _,t=stored(self.h,'另一个用户事实。','旧文件名字还是之前那个，已经确认。');v=self.h.context_turns([*self.turns,t]);self.assertIn('旧文件名字还是之前那个',v[-1][-1]['content']);self.assertTrue(v[-1][-1]['content'].startswith(ASSISTANT_LABEL));self.assertTrue(self.h.projection_diagnostics['assistant_semantic_rewrites_unverified'])
    async def test_compatible_same_category_not_conflict(self):
        mid,_=stored(self.h,'所有文档扫描必须在本地进行。不得自动删除或修改原始Markdown文件。');pin(self.h,mid,'所有文档扫描必须在本地进行。');pin(self.h,mid,'不得自动删除或修改原始Markdown文件。');ps=self.h.pins.list(active_only=True);self.assertTrue(all(p['multiple_same_category'] and not p['needs_review'] and p['semantic_conflict_unassessed'] for p in ps));self.assertTrue(all(p['status']=='active' for p in ps));self.assertIn('multiple_same_category',str(render(ps)))
    async def test_partial_projection_marks_incomplete_with_same_turn_count(self):
        a,c=self.agent();await a.handle_message('继续');s=a.last_runtime_report['context'];self.assertEqual(s['redacted_source_spans'],1);self.assertTrue(s['history_projection_incomplete']);self.assertTrue(s['history_information_incomplete']);self.assertTrue(s['context_truncated']);self.assertEqual(s['history_coverage'],'unverified');self.assertNotIn('pin_history_turns_removed',s)
    async def test_project_before_semantic_input(self):
        revoke(self.h,self.new);safe=self.h.context_turns(self.turns);cfg=replace(self.cfg,context_compaction={'mode':'semantic','allow_extra_requests':True,'input_tokens':20000});compactor=ContextCompactor(cfg);seen=[]
        async def invoke(request):seen.append(request);d={k:[] for k in FIELDS};d['user_constraints']=[{'turn':1,'message':0,'quote':UNITS[0]}];return response(json.dumps(d,ensure_ascii=False))
        summary,status=await compactor.compact(safe,cfg,invoke);self.assertNotIn(OLD,str(seen));self.assertNotIn(NEW,str(seen));self.assertIn(UNITS[0],summary['content']);self.assertIn('不是用户确认',summary['content']);self.assertEqual(compactor.calls,1)
    async def test_failed_summary_cannot_reintroduce_old_rule(self):
        safe=self.h.context_turns(self.turns);cfg=replace(self.cfg,context_compaction={'mode':'semantic','allow_extra_requests':True,'input_tokens':20000});compactor=ContextCompactor(cfg)
        async def invoke(request):
            d={k:[] for k in FIELDS};d['user_constraints']=[{'turn':1,'message':0,'quote':OLD}];return response(json.dumps(d,ensure_ascii=False))
        summary,status=await compactor.compact(safe,cfg,invoke);self.assertIsNone(summary);self.assertTrue(status.startswith('fallback'));self.assertEqual(self.h.pins.list(active_only=True)[0]['id'],self.new['id'])
    async def test_protected_lifecycle_does_not_bypass_budget(self):
        revoke(self.h,self.new);self.h.context_turns(self.turns);cfg=replace(self.cfg,context_token_budget={'mode':'estimate','input_limit':256});manager=ContextManager(cfg);manager.lifecycle_reference=self.h.lifecycle_reference
        with self.assertRaises(ContextBudgetError):manager.prepare([{'role':'system','content':'rules'},{'role':'user','content':'now'}],[],[],Plan())
    async def test_budget_omission_separate_from_pin_projection(self):
        cfg=replace(self.cfg,context_token_budget={'mode':'estimate','input_limit':10000});_,long=stored(self.h,'long independent fact '*220);self.turns.append(long);a,c=self.agent(cfg);await a.handle_message('继续');stats=a.last_runtime_report['context'];self.assertGreater(stats['history_turns_omitted'],0);self.assertGreater(stats['redacted_source_spans'],0);self.assertLessEqual(stats['estimated_input_tokens'],10000);self.assertTrue(stats['history_information_incomplete'])
    async def test_sse_counts_no_removed_text_or_receipt(self):
        events=[];a,c=self.agent();a._event_callback=events.append;await a.handle_message('继续');updates=[e for e in events if e['type']=='resource_update'];self.assertTrue(updates);self.assertNotIn(OLD,json.dumps(updates,ensure_ascii=False));self.assertNotIn(UNITS[0],json.dumps(updates,ensure_ascii=False));self.assertIsNone(a.last_task_contract);self.assertIsNone(a.last_coding_report)

def check_pin_lifecycle_context():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleChecks))
    if not r.wasSuccessful():raise AssertionError('lifecycle checks failed')
if __name__=='__main__':check_pin_lifecycle_context()
