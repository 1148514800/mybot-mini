"""OFFLINE/SYNTHETIC bounded compaction with exact source validation."""
import json
from types import SimpleNamespace as N
import unittest
from mybot.agent.context_compactor import ContextCompactor,FIELDS,LABEL
from scripts import modernization_fixtures as fixtures

class AdaptiveChecks(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.Base.setUp
    build=fixtures.Base.build
    history=fixtures.Base.history
    semantic=fixtures.Base.semantic
    async def compact(self,doc,*,room=3000,fits=None,finish='stop'):
        self.config.context_compaction.update(mode='semantic',allow_extra_requests=True,input_tokens=40000)
        compactor=ContextCompactor(self.config);requests=[]
        async def invoke(request):
            requests.append(request);r=fixtures.response(json.dumps(doc,ensure_ascii=False));r.choices[0].finish_reason=finish;return r
        result=await compactor.compact(self.history(),self.config,invoke,
            available_summary_budget=room,fits=fits)
        return result,requests,compactor
    def document(self):
        d={k:[] for k in FIELDS};d['user_constraints']=[dict(turn=1,message=0,quote='不删除用户文件')];return d
    async def test_zero_room_zero_calls(self):
        (summary,status),req,c=await self.compact(self.document(),room=0)
        self.assertIsNone(summary);self.assertEqual(status,'semantic_skipped_insufficient_room');self.assertEqual(req,[]);self.assertEqual(c.calls,0)
    async def test_dynamic_output_limit(self):
        (_,status),req,_=await self.compact(self.document(),room=1500)
        self.assertEqual(status,'semantic_applied');self.assertLessEqual(req[0]['max_tokens'],1200);self.assertLess(req[0]['max_tokens'],1200)
        self.assertIn('TOTAL',req[0]['messages'][1]['content'])
    async def test_valid_nine_fields(self):
        (summary,status),_,_=await self.compact(self.document())
        self.assertEqual(status,'semantic_applied');self.assertEqual(set(json.loads(summary['content'][len(LABEL):])),set(FIELDS))
    async def test_output_truncation_no_retry(self):
        (summary,status),req,c=await self.compact(self.document(),finish='length')
        self.assertIsNone(summary);self.assertEqual(status,'fallback_output_truncated');self.assertEqual(len(req),1);self.assertEqual(c.calls,1)
    async def test_valid_oversize_prunes_low_priority(self):
        d=self.document();d['important_artifacts']=[dict(turn=1,message=0,quote='x'*500)]
        (summary,status),req,_=await self.compact(d,fits=lambda m:len(m['content'])<800)
        self.assertEqual(status,'semantic_applied_pruned');self.assertIn('不删除用户文件',summary['content']);self.assertNotIn('x'*500,summary['content']);self.assertEqual(len(req),1)
    async def test_invalid_citation_cannot_hide_in_pruned_field(self):
        d=self.document();d['important_artifacts']=[dict(turn=1,message=0,quote='fabricated')]
        (summary,status),req,_=await self.compact(d,fits=lambda m:False)
        self.assertIsNone(summary);self.assertIn('fallback',status);self.assertEqual(len(req),1)
    async def test_constraints_not_silently_pruned(self):
        (summary,status),_,_=await self.compact(self.document(),fits=lambda m:False)
        self.assertIsNone(summary);self.assertEqual(status,'fallback_summary_does_not_fit')
    async def test_plan_cannot_become_completed(self):
        d=self.document();d['completed_work']=[dict(turn=1,message=1,quote='计划下一步测试')]
        (summary,status),_,_=await self.compact(d)
        self.assertIsNone(summary);self.assertIn('fallback',status)
    async def test_real_loop_budget_and_session(self):
        self.semantic();before=self.agent.session.export_turns();await self.agent.handle_message('继续')
        report=self.agent.resources.context
        self.assertEqual(report['context_compaction_status'],'semantic_applied');self.assertGreater(report['available_summary_budget'],0)
        self.assertLessEqual(report['estimated_input_tokens'],report['input_token_limit'])
        self.assertEqual(self.agent.session.export_turns()[:-1],before)
    async def test_real_loop_insufficient_room_zero_extra(self):
        self.semantic();self.config.context_summary_max_chars=128
        await self.agent.handle_message('继续')
        self.assertEqual(self.agent.resources.compaction_requests,0)
        self.assertEqual(len(self.client.requests),1)
        self.assertEqual(self.agent.resources.context['context_compaction_status'],'semantic_skipped_insufficient_room')
    async def test_tool_ids_preserved(self):
        self.semantic();history=self.history();history[0].insert(1,dict(role='assistant',content=None,tool_calls=[dict(id='safe-id',type='function',function=dict(name='read_file',arguments='{}'))]));history[0].insert(2,dict(role='tool',tool_call_id='safe-id',content='found'))
        self.agent.session.restore(history);await self.agent.handle_message('继续');self.assertEqual(self.agent.session.export_turns()[:-1],history)
    async def test_dynamic_contract_entry_cap(self):
        d=self.document();d['confirmed_facts']=[dict(turn=1,message=0,quote='GOAL:') for _ in range(6)]
        (summary,status),_,_=await self.compact(d,room=1500)
        self.assertEqual(status,'semantic_applied_pruned')
        selected=json.loads(summary['content'][len(LABEL):]);self.assertLess(sum(map(len,selected.values())),7)
        self.assertIn('不删除用户文件',summary['content'])
    async def test_ui_distinguishes_skipped_pruned_truncated(self):
        from pathlib import Path
        text=Path('mybot/web/static/app.js').read_text()
        for key in ('semantic_applied_pruned:', 'semantic_skipped_insufficient_room:', 'fallback_output_truncated:'):
            self.assertIn(key,text)
    async def test_output_rejected_without_second_request(self):
        self.semantic()
        async def bad(request):return fixtures.response('{')
        self.client.summary=bad;await self.agent.handle_message('继续')
        self.assertEqual(self.agent.resources.compaction_requests,1);self.assertIn('fallback',self.agent.resources.context['context_compaction_status'])

if __name__=='__main__':unittest.main(verbosity=2)
