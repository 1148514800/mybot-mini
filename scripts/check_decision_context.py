"""Public-design synthetic regressions A–E; never instantiate a real provider."""
import json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from mybot.agent import AgentLoop,ContextBuilder
from mybot.agent.context_manager import ContextManager,ContextBudgetError
from mybot.agent.planning import Plan
from mybot.agent.decision_provenance import render_view
from mybot.agent.token_counter import TokenCounter
from mybot.storage.history import SessionHistory,open_store
from mybot.storage.session_store import validate_turns
from mybot.storage.context_projection import LIFECYCLE_LABEL,POLICY
from mybot.tools import build_default_tool_registry
from mybot.web.runtime import Conversation
from mybot.agent.session import Session
from scripts.eventstore_fixtures import configuration,SyntheticClient
from scripts.source_projection_fixtures import stored,pin,revoke,source_fixture,UNITS
from scripts.check_session import response,call

CONSTRAINTS=['笔记数据只能在本地处理。','不允许自动删除原始笔记。']
FALSE='原始笔记永久保留是已确定要求。'
class ContextChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.cfg=configuration(self.root,context_recent_turns=6,context_max_chars=60000,context_token_budget={'mode':'estimate','input_limit':30000});self.s=open_store(self.cfg,'cli');self.addCleanup(self.s.close);self.h=SessionHistory(self.s)
    def agent(self,client=None):
        client=client or SyntheticClient();a=AgentLoop(client,self.cfg,build_default_tool_registry(self.cfg.workspace),ContextBuilder(self.cfg.workspace),history=self.h);a.session.restore(self.h.model_turns());return a,client
    def constraints(self):
        mid,_=stored(self.h,''.join(CONSTRAINTS));return [pin(self.h,mid,t) for t in CONSTRAINTS]
    async def test_A_false_strengthening_not_persisted(self):
        self.constraints()
        class Wrong(SyntheticClient):
            async def create(self,**kw):self.requests.append(kw);return response(FALSE)
        a,c=self.agent(Wrong());reply=await a.handle_message('继续设计');self.assertEqual(reply,FALSE);self.assertEqual({p['original_quote'] for p in self.h.decisions()['items']},set(CONSTRAINTS));self.assertEqual(len(self.h.pins.list()),2);self.assertEqual(len(c.requests),1);self.assertNotIn(FALSE,render_view(self.h.decisions()));self.assertIn('更强义务',str(c.requests[-1]));self.assertFalse(a.last_task_contract)
    async def test_A_free_text_remains_model_text(self):
        self.constraints();stored(self.h,'继续',FALSE);self.assertEqual(self.h.messages()[-1]['role'],'assistant');self.assertNotIn(FALSE,render_view(self.h.decisions()));self.assertIn('推断不是已确认',self.h.decisions()['notice'])
    async def test_B_three_committed_boundaries(self):
        mid,_=stored(self.h,'命名为index.md。');old=pin(self.h,mid,'命名为index.md。');b1=self.h.decisions()['boundary'];mid,_=stored(self.h,'命名为catalog.md。');new=pin(self.h,mid,'命名为catalog.md。',replace_id=old['id'],expected_revision=old['revision']);b2=self.h.decisions()['boundary'];revoke(self.h,new)
        sets=[{p['original_quote'] for p in self.h.decisions(boundary=b)['items'] if p['status_at_boundary']=='active'} for b in (b1,b2,None)];self.assertEqual(sets,[{'命名为index.md。'},{'命名为catalog.md。'},set()]);self.assertIn('不表示当时错误',render_view(self.h.decisions()))
    async def test_C_optional_and_unresolved_no_auto_decision(self):
        stored(self.h,'CLI可以作为可选方案，全文搜索尚未决定。','建议增加数据库缓存。');a,c=self.agent();await a.handle_message('继续');self.assertEqual(self.h.decisions()['items'],[]);self.assertEqual(len(c.requests),1)
    async def test_D_long_history_restart_without_authority(self):
        self.constraints()
        for i in range(8):stored(self.h,f'公开设计轮次{i}。',f'建议{i}，不是批准。')
        prior=self.h.decisions();sid=self.h.sid;self.s.close();self.s=open_store(self.cfg,'cli');self.addCleanup(self.s.close);self.h=SessionHistory(self.s,sid);self.assertEqual(self.h.decisions(),prior);a,c=self.agent();await a.handle_message('恢复后继续');self.assertEqual(len(c.requests),1);self.assertTrue(all(t in str(c.requests[-1]) for t in CONSTRAINTS));self.assertIsNone(a.last_task_contract);self.assertIsNone(a.last_coding_report);self.assertFalse(self.h.status()['execution_evidence_restored'])
    async def test_E_tool_pairing_unchanged(self):
        mid,t=stored(self.h,'独立公开信息');toolcall=call('decision-tool','list_files','{"path":"."}');t.insert(1,{'role':'assistant','content':None,'tool_calls':[{'id':toolcall.id,'type':'function','function':{'name':toolcall.function.name,'arguments':toolcall.function.arguments}}]});t.insert(2,{'role':'tool','tool_call_id':'decision-tool','content':'合成结果'});self.constraints();safe=self.h.context_turns([t]);validate_turns(safe);self.assertEqual(safe[0][1:3],t[1:3])
    async def test_source_aware_units_preserved(self):
        self.s.close();cfg,s,h,turns,new=source_fixture(self.root);self.s=s;self.addCleanup(s.close);self.cfg=cfg;self.h=h;a,c=self.agent();await a.handle_message('继续');self.assertTrue(all(t in str(c.requests[-1]) for t in UNITS))
    async def test_reference_is_user_not_system_authority(self):
        self.constraints();self.h.context_turns([]);self.assertEqual(len(self.h.lifecycle_reference),1);self.assertEqual(self.h.lifecycle_reference[0]['role'],'user');d=json.loads(self.h.lifecycle_reference[0]['content'][len(LIFECYCLE_LABEL):]);self.assertEqual(d['policy'],POLICY);self.assertIn('不授予工具权限',d['policy'])
    async def test_reference_budget_enforced(self):
        self.constraints();self.h.context_turns([]);cfg=replace(self.cfg,context_token_budget={'mode':'estimate','input_limit':256});m=ContextManager(cfg);m.lifecycle_reference=self.h.lifecycle_reference
        with self.assertRaises(ContextBudgetError):m.prepare([{'role':'system','content':'rules'},{'role':'user','content':'now'}],[],[],Plan())
    async def test_output_reserve_unchanged(self):
        self.constraints();a,c=self.agent();await a.handle_message('继续');req=c.requests[-1];self.assertEqual(req['max_tokens'],self.cfg.max_completion_tokens);stats=TokenCounter.inspect(self.cfg,req);self.assertLessEqual(stats['estimated_input_tokens'],30000);self.assertEqual(stats['output_reserved_tokens'],self.cfg.max_completion_tokens)
    async def test_cli_web_same_verified_items_no_requests(self):
        self.constraints();a,c=self.agent();text=await a.handle_message('/decisions');conversation=Conversation(self.h.sid,Session(6),history=self.h);self.assertEqual(text,render_view(conversation.state()['decisions']));self.assertEqual(c.requests,[]);self.assertTrue(all(t in text for t in CONSTRAINTS))
    async def test_cli_historic_boundary(self):
        p=self.constraints()[0];b=self.h.decisions()['boundary'];revoke(self.h,p);a,c=self.agent();text=await a.handle_message('/decisions '+str(b));self.assertIn('该历史边界有效：'+p['content'],text);self.assertEqual(c.requests,[])
    async def test_web_no_raw_decision_sse(self):
        self.constraints();events=[];a,c=self.agent();a._event_callback=events.append;await a.handle_message('继续');safe=[e for e in events if e['type']=='resource_update'];self.assertNotIn(CONSTRAINTS[0],str(safe));self.assertNotIn('confirmation_event_id',str(safe))
    async def test_compatible_pins_not_false_conflict(self):
        self.constraints();self.assertTrue(all(p['multiple_same_category'] and not p['needs_review'] for p in self.h.pins.list()));self.assertEqual(len(self.h.decisions()['items']),2)
    async def test_reference_no_inactive_raw_quotes(self):
        old=self.constraints()[0];revoke(self.h,old);self.h.context_turns([]);reference=str(self.h.lifecycle_reference);self.assertNotIn(old['content'],reference);self.assertIn('valid_until',reference);self.assertIn('追溯纠错',reference)
    async def test_damaged_quote_not_in_trusted_view(self):
        p=self.constraints()[0]
        with self.s.connection() as db:db.execute('UPDATE messages SET truncated=1 WHERE id=?',(p['source_message_id'],))
        self.h.context_turns([]);self.assertFalse(self.h.decisions()['items'][0]['source_verified']);self.assertEqual(self.h.projection_active_pins,[])

def check_decision_context():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContextChecks))
    if not r.wasSuccessful():raise AssertionError('decision context checks failed')
if __name__=='__main__':check_decision_context()
