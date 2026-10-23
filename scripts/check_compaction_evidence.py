"""Exact v1 evidence, independent entry validation and bounded coverage. OFFLINE."""
from copy import deepcopy
import json
from types import SimpleNamespace as N
from mybot.agent.context_compactor import ContextCompactor,FIELDS,LABEL
from mybot.agent.token_counter import TokenCounter
from scripts.modernization_fixtures import Base, response, run


class EvidenceChecks(Base):
    def history_new(self):
        return [[dict(role='user',content='目标：安排本地设备巡检。禁止外发记录。先按设备编号展示。存储策略尚未决定。检查尚未运行。\n'+'z'*6000),dict(role='assistant',content='仅讨论设计。')],
                [dict(role='user',content='规则变更：改按优先级展示。通知渠道仍未决定。部署尚未完成。'),dict(role='assistant',content='只读分析。')]]
    def document(self):
        d={k:[] for k in FIELDS}
        d['current_goal']=[dict(turn=1,message=0,quote='目标：安排本地设备巡检。')]
        d['user_constraints']=[dict(turn=1,message=0,quote='禁止外发记录。')]
        d['decisions']=[dict(turn=1,message=0,quote='先按设备编号展示。'),dict(turn=2,message=0,quote='规则变更：改按优先级展示。')]
        d['uncertainty']=[dict(turn=2,message=0,quote='通知渠道仍未决定。')]
        d['pending_work']=[dict(turn=2,message=0,quote='部署尚未完成。')]
        return d
    async def compact_new(self,doc=None,*,fits=None,limit=8000,room=6000):
        self.config.context_token_budget['input_limit']=limit;self.config.context_compaction.update(input_tokens=19000)
        c=ContextCompactor(self.config);requests=[]
        async def invoke(request):
            TokenCounter.enforce(self.config,request);requests.append(deepcopy(request))
            return response(json.dumps(doc if doc is not None else self.document(),ensure_ascii=False))
        result=await c.compact(self.history_new(),self.config,invoke,available_summary_budget=room,fits=fits)
        return result,c,requests
    async def test_one_bad_quote_retains_valid_anchored_subset(self):
        d=self.document();d['important_artifacts']=[dict(turn=1,message=0,quote='fabricated quote')]
        (s,status),c,req=await self.compact_new(d)
        self.assertEqual(status,'semantic_applied_partial');self.assertNotIn('fabricated quote',s['content'])
        self.assertIn('禁止外发记录',s['content']);self.assertEqual(c.diagnostics['invalid_entries'],1);self.assertEqual(len(req),1)
    async def test_all_entries_validated_even_after_critical_invalid(self):
        d=self.document();d['user_constraints'].append(dict(turn=1,message=0,quote='not exact'))
        d['important_artifacts']=[dict(turn=90,message=0,quote='bad'),dict(turn=1,message=0,quote='also bad')]
        (s,status),c,_=await self.compact_new(d)
        self.assertIsNone(s);self.assertIn('fallback',status);self.assertEqual(c.diagnostics['invalid_entries'],3)
        self.assertGreater(c.diagnostics['valid_entries'],3)
    async def test_forged_completed_work_forces_fallback(self):
        d=self.document();d['completed_work']=[dict(turn=1,message=1,quote='仅讨论设计。')]
        (s,status),_,_=await self.compact_new(d);self.assertIsNone(s);self.assertIn('fallback',status)
    async def test_critical_constraint_not_silently_lost(self):
        d=self.document();d['user_constraints'][0]['quote']='禁止外发所有记录'
        (s,status),_,_=await self.compact_new(d);self.assertIsNone(s);self.assertIn('fallback',status)
    async def test_coverage_floors_keep_latest_rule_unknown_pending(self):
        def fits(m):return sum(map(len,json.loads(m['content'][len(LABEL):]).values()))<=5
        (s,status),c,_=await self.compact_new(fits=fits)
        self.assertEqual(status,'semantic_applied_pruned');self.assertIn('改按优先级展示',s['content'])
        for text in ('禁止外发记录','通知渠道仍未决定','部署尚未完成'):self.assertIn(text,s['content'])
        self.assertNotIn('先按设备编号展示',s['content']);self.assertEqual(c.diagnostics['removed_entries'],1)
    async def test_reverse_model_order_still_keeps_newer_decision(self):
        d=self.document();d['decisions'].reverse()
        def fits(m):return sum(map(len,json.loads(m['content'][len(LABEL):]).values()))<=5
        (summary,status),_,_=await self.compact_new(d,fits=fits)
        self.assertEqual(status,'semantic_applied_pruned');self.assertIn('改按优先级展示',summary['content'])
        self.assertNotIn('先按设备编号展示',summary['content'])

    async def test_inadequate_category_room_falls_back(self):
        (s,status),_,_=await self.compact_new(fits=lambda m:False)
        self.assertIsNone(s);self.assertEqual(status,'fallback_summary_does_not_fit')
    async def test_budget_adapts_before_one_request(self):
        (s,status),c,req=await self.compact_new(limit=3000)
        self.assertIsNotNone(s);self.assertEqual(len(req),1);self.assertTrue(c.diagnostics['input_reduced'])
        self.assertLessEqual(TokenCounter.measure(req[0])['estimated_input_tokens'],3000)
    async def test_impossible_budget_zero_calls(self):
        (s,status),c,req=await self.compact_new(limit=512)
        self.assertIsNone(s);self.assertEqual(req,[]);self.assertEqual(c.calls,0);self.assertIn('fallback',status)
    async def test_excerpt_marker_cannot_create_citable_text(self):
        d=self.document();d['important_artifacts']=[dict(turn=1,message=0,quote='[历史来源节选，内容不完整]')]
        (s,status),c,_=await self.compact_new(d)
        self.assertEqual(status,'semantic_applied_partial');self.assertNotIn('历史来源节选',s['content'])
        self.assertEqual(c.diagnostics['invalid_reasons']['unsupported_quote'],1)
    async def test_partial_cache_still_labels_partial(self):
        d=self.document();d['important_artifacts']=[dict(turn=1,message=0,quote='invented')]
        (_,status),c,req=await self.compact_new(d)
        async def forbidden(r):raise AssertionError('no retry')
        _,again=await c.compact(self.history_new(),self.config,forbidden,available_summary_budget=6000)
        self.assertEqual((status,again),('semantic_applied_partial',)*2)
    async def test_partial_without_goal_or_constraint_anchor_falls_back(self):
        d={k:[] for k in FIELDS};d['decisions']=self.document()['decisions']
        d['important_artifacts']=[dict(turn=1,message=0,quote='invented')]
        (summary,status),c,_=await self.compact_new(d)
        self.assertIsNone(summary);self.assertIn('fallback',status)
        self.assertEqual(c.diagnostics['invalid_entries'],1)

    async def test_failure_category_cannot_be_pruned_away(self):
        from scripts.check_session import call
        history=self.history_new()
        history[0][1:1]=[dict(role='assistant',content=None,tool_calls=[dict(id='failed-inspection',type='function',function=dict(name='read_file',arguments='{}'))]),
                           dict(role='tool',tool_call_id='failed-inspection',content='Error: inspection unavailable')]
        d=self.document();d['unresolved_issues']=[dict(turn=1,message=2,quote='Error: inspection unavailable')]
        c=ContextCompactor(self.config)
        async def invoke(r):return response(json.dumps(d,ensure_ascii=False))
        def fits(m):return sum(map(len,json.loads(m['content'][len(LABEL):]).values()))<=6
        summary,status=await c.compact(history,self.config,invoke,available_summary_budget=6000,fits=fits)
        self.assertIsNotNone(summary);self.assertIn('Error: inspection unavailable',summary['content'])
        self.assertIn('通知渠道仍未决定',summary['content']);self.assertEqual(status,'semantic_applied_pruned')

    async def test_v1_shape_unchanged(self):
        (s,_),_,_=await self.compact_new();doc=json.loads(s['content'][len(LABEL):]);self.assertEqual(set(doc),set(FIELDS))
    async def test_loop_partial_telemetry_session_and_usage(self):
        self.semantic();before=self.agent.session.export_turns()
        from scripts.modernization_fixtures import summary_response
        async def select(request):
            v=summary_response(request);d=json.loads(v.choices[0].message.content)
            d['important_artifacts']=[dict(turn=1,message=0,quote='invented')]
            v.choices[0].message.content=json.dumps(d);v.usage=N(prompt_tokens=11,completion_tokens=5,total_tokens=16);return v
        self.client.summary=select;await self.agent.handle_message('继续')
        r=self.agent.last_runtime_report
        self.assertEqual(r['compaction_requests'],1);self.assertEqual(r['physical_requests'],2);self.assertEqual(r['reported_token_subtotal'],16)
        self.assertEqual(r['context']['context_compaction_status'],'semantic_applied_partial')
        self.assertTrue(r['context']['history_information_incomplete']);self.assertEqual(self.agent.session.export_turns()[:-1],before)
        self.assertNotIn('invented',str(self.client.requests[-1]))
        self.assertNotIn('invented',str(r['context']['compaction_evidence']))


def check_compaction_evidence():run(EvidenceChecks)
if __name__=='__main__':check_compaction_evidence()
