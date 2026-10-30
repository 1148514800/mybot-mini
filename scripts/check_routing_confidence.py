"""Selective v1 evidence, abstention, coverage, isolation and original execution invariants."""
import asyncio
import inspect
import json
import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace as N
from mcp import types
from mybot.config import GatewayConfig
from mybot.agent.token_counter import TokenCounter
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.context_manager import ContextManager, ContextBudgetError
from mybot.mcp_client.adapter import MCPToolAdapter
from mybot.mcp_client.discovery import MCPToolCatalog, validate_discovery
from mybot.mcp_client.relevance import evidence, MAX_CANDIDATES
from mybot.mcp_client.router import AdaptiveToolRouter, RoutingDecision
from mybot.mcp_client.manager import MCPClientManager
from mybot.evaluation.tool_routing import selection_metrics,summarize,route_query,load_cases
from mybot.evaluation.tool_agent import evaluate,Limits
from scripts.check_adaptive_routing import AdaptiveChecks
from scripts.check_tool_discovery import AgentFixture,PROJECT,DOCUMENT
from scripts.check_mcp import MCPChecks
from scripts.check_session import response,call,assert_pairs
from scripts.check_approval import deny,approve
from scripts.compare_selective_routing import MODES


class ConfidenceChecks(AgentFixture,unittest.IsolatedAsyncioTestCase):
    setUp=MCPChecks.setUp
    fake=AdaptiveChecks.fake
    route=AdaptiveChecks.route

    def cfg(self,allowed=None,**options):
        return AdaptiveChecks.cfg(self,allowed,selection_policy='selective',**options)

    async def test_config_strict(self):
        for value in (None,False,1,[],{},'auto'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_discovery({'selection_policy':value})
        for cfg in ({'selection_policy':'selective'},{'enabled':True,'selection_policy':'selective'},
                    {'enabled':False,'routing_mode':'adaptive','selection_policy':'selective'},
                    {'enabled':True,'routing_mode':'manual','selection_policy':'selective'}):
            with self.assertRaises(ValueError):validate_discovery(cfg)
        self.assertNotIn('selection_policy',validate_discovery({}))
        self.assertEqual(validate_discovery({'enabled':False,'selection_policy':'legacy'})['enabled'],False)

    async def test_evidence_grades_and_languages(self):
        a=self.fake()
        for q,t in [('project pending tasks',PROJECT),('查询项目未完成任务',PROJECT),('搜索 architecture 文档',DOCUMENT)]:
            self.assertEqual(evidence(q,a.discovery,[t])[t].level,'strong')
        for q in ('synthetic tools available','help using tool'):
            d=self.route(a,q);self.assertFalse(d.selected_tool_names);self.assertTrue(d.abstained)
        e=evidence('quantum teleportation',a.discovery,[PROJECT])[PROJECT]
        self.assertEqual(e.level,'none');self.assertFalse(e.matched)
        self.assertEqual(evidence('project task',a.discovery,[PROJECT]),evidence('project task',a.discovery,[PROJECT]))

    async def test_weak_operation_and_unknown(self):
        a=self.fake()
        for q in ('list','get','unknownwordzz','teaching','synthetic'):
            self.assertFalse(self.route(a,q).selected_tool_names)
        self.assertEqual(self.route(a,'synthetic').abstention_reason,'generic_only_matches')
        self.assertEqual(self.route(a,'list').evidence_level,'weak')
        self.assertEqual(self.route(a,'unknownwordzz').evidence_level,'none')

    async def test_high_df_descriptions_do_not_gate(self):
        a=self.fake()
        # All fixture tools include synthetic/teaching; not substantive evidence.
        d=self.route(a,'synthetic teaching catalog')
        self.assertFalse(d.selected_tool_names);self.assertGreater(d.rejected_weak_count,0)

    async def test_small_eager_all_relevant(self):
        a=self.fake(['list_project_tasks','search_documents'])
        d=self.route(a,'List project tasks and search architecture documents')
        self.assertEqual(d.routing_strategy,'small_eager');self.assertEqual(set(d.selected_tool_names),{PROJECT,DOCUMENT})

    async def test_selective_small_eager_honors_preselect_limit(self):
        a=self.fake(['list_project_tasks','search_documents'],preselect_limit=1)
        d=self.route(a,'list project tasks and search architecture documents')
        self.assertEqual(len(d.selected_tool_names),1)
        self.assertEqual(d.routing_strategy,'coverage_preselect')
        a.discovery.config['selection_policy']='legacy'
        self.assertEqual(self.route(a,'list project tasks and search architecture documents').routing_strategy,'small_eager')

    async def test_small_eager_chat_no_match(self):
        a=self.fake(['list_project_tasks','search_documents'])
        for q in ('hello','quantum teleportation','synthetic tool available'):
            self.assertEqual(self.route(a,q).selected_tool_names,())

    async def test_small_eager_partial(self):
        a=self.fake(['list_project_tasks','search_documents'])
        d=self.route(a,'project tasks');self.assertEqual(d.selected_tool_names,(PROJECT,))
        self.assertEqual(d.routing_strategy,'coverage_preselect')

    async def test_legacy_small_eager_unchanged(self):
        cfg=AdaptiveChecks.cfg(self,['list_project_tasks','search_documents'])
        manager=N(servers=cfg.mcp_servers)
        from scripts.mcp_catalog_demo_server import DEFINITIONS
        for name in cfg.mcp_servers['catalog']['allowed_tools']:self.tools.register(MCPToolAdapter(manager,'catalog',DEFINITIONS[name]))
        a=AgentLoop(N(),cfg,self.tools,ContextBuilder(self.workspace))
        self.assertEqual(self.route(a,'hello').routing_strategy,'small_eager')
        self.assertEqual(self.route(a,'hello').selection_policy,'legacy')

    async def test_no_fill_and_redundancy(self):
        a=self.fake()
        d=self.route(a,'list project tasks')
        self.assertEqual(d.selected_tool_names,(PROJECT,));self.assertGreater(d.redundant_candidates_skipped,0)

    async def test_cross_domain_and_determinism(self):
        a=self.fake()
        q='list project pending tasks and search architecture documents'
        d=self.route(a,q)
        self.assertTrue({PROJECT,DOCUMENT}<=set(d.selected_tool_names))
        self.assertEqual(d.selected_tool_names,self.route(a,q).selected_tool_names)
        self.assertGreater(d.covered_query_concepts_count,2)

    async def test_coverage_rescues_ranked_duplicates(self):
        a=self.fake()
        ranked=[PROJECT,'mcp__catalog__search_project_tasks','mcp__catalog__get_project_task',DOCUMENT]
        with patch.object(a.discovery,'ranked_names',return_value=ranked):
            d=self.route(a,'list project tasks architecture documents')
            self.assertTrue({PROJECT,DOCUMENT}<=set(d.selected_tool_names))
            self.assertLess(len(d.selected_tool_names),3)
            a.discovery.config['selection_policy']='legacy'
            legacy=self.route(a,'list project tasks architecture documents')
            self.assertNotIn(DOCUMENT,legacy.selected_tool_names)

    async def test_schema_skip_and_context(self):
        a=self.fake(['list_project_tasks','search_documents'])
        for name,e in list(a.discovery.entries.items()):
            if name==PROJECT:
                a.discovery.entries[name]=replace(e,schema_chars=100000)
        d=self.route(a,'list project tasks and search architecture documents')
        self.assertEqual(d.selected_tool_names,(DOCUMENT,));self.assertEqual(d.fallback_reason,'schema_budget_limited')
        a.discovery.config['max_active_schema_chars']=256
        d=self.route(a,'search architecture documents');self.assertFalse(d.selected_tool_names)
        self.assertEqual(d.abstention_reason,'schema_budget_limited');self.assertEqual(d.evidence_level,'strong')

    async def test_context_limits_actual_schemas(self):
        a=self.fake(['list_project_tasks','search_documents']);q='list project tasks and search architecture documents'
        messages=a.context.build_messages(q,[]);base=a.discovery.visible_names()
        a.config.context_token_budget['input_limit']=max(TokenCounter.measure(TokenCounter.request(a.config,messages,a.tools.get_definitions(base|{n})))['estimated_input_tokens'] for n in (PROJECT,DOCUMENT))
        d=self.route(a,q);self.assertEqual(len(d.selected_tool_names),1)
        self.assertEqual(d.fallback_reason,'context_budget_limited')
        a.config.context_token_budget['input_limit']=256
        with self.assertRaises(ContextBudgetError):self.route(a,q)
        self.assertFalse(a.discovery.active)

    async def test_atomicity_and_permissions(self):
        await AdaptiveChecks.test_14_permissions_atomic_apply_late_adapter(self)

    async def test_bounded_candidates_and_input(self):
        a=self.fake();d=self.route(a,'project task search document calendar code dataset')
        self.assertLessEqual(d.candidate_count,MAX_CANDIDATES)
        d=self.route(a,'project'*1000);self.assertEqual(d.abstention_reason,'input_length_limit')
        self.assertFalse(d.selected_tool_names)

    async def test_diagnostics_privacy_and_compatibility(self):
        a=self.fake();d=self.route(a,'project pending tasks')
        text=json.dumps(d.diagnostics())
        for forbidden in ('project pending','selected_tool_names','confidence','probability','mcp__catalog'):
            self.assertNotIn(forbidden,text)
        old=RoutingDecision('manual_fallback',(),0,0,'test',0,0)
        self.assertEqual(old.selection_policy,'legacy')

    async def test_runtime_no_file_gold_or_network(self):
        a=self.fake()
        with (patch('builtins.open',side_effect=AssertionError('no file access')),
              patch('pathlib.Path.read_text',side_effect=AssertionError('no eval access'))):
            d=self.route(a,'project pending tasks')
        self.assertIn(PROJECT,d.selected_tool_names)
        self.assertNotIn('case',inspect.signature(AdaptiveToolRouter.route).parameters)
        self.assertEqual(set(a.router.__dict__),{'catalog'})

    async def test_abstention_preserves_meta_no_plan_evidence(self):
        a=self.fake(['list_project_tasks']);d=self.route(a,'hello')
        a.discovery.apply_preselection(d.selected_tool_names)
        self.assertTrue({'search_mcp_tools','activate_mcp_tools','create_plan','read_file'}<=a.discovery.visible_names())
        self.assertFalse(a.plan.steps)

    async def test_confirm_not_bypassed(self):
        cfg=self.cfg(['list_project_tasks'])
        cfg.mcp_servers['catalog']['tool_policies']['list_project_tasks']='confirm'
        async with MCPClientManager(cfg,self.tools,deny) as manager:
            a=self.agent(cfg,[response(calls=[call('x',PROJECT,'{"project":"mini"}')])])
            await self.handle(a,'list project tasks')
            self.assertEqual(len(manager.audit),1);self.assertFalse(manager.audit[0]['executed'])
            self.assertIn('approval_denied',json.dumps(a.session.history()));assert_pairs(self,a.session.history())

    # Rerun original security/lifecycle contracts with selective cfg(), not copied assumptions.
    test_current_input_only=AdaptiveChecks.test_15_current_input_only_and_readonly_history_plan
    test_first_request=AdaptiveChecks.test_16_real_first_request_direct_schema_no_extra_io
    test_snapshot_manual_replace_once=AdaptiveChecks.test_17_initial_selection_manual_replace_snapshot_and_once
    test_no_io=AdaptiveChecks.test_21_no_io_and_shared_rank_index
    test_planning_evidence=AdaptiveChecks.test_28_planning_only_real_results_verify
    test_late_adapter_react=AdaptiveChecks.test_29_react_limit_and_late_adapter_guard
    test_task_reset_clear=AdaptiveChecks.test_19_task_reset_clear_native_no_tools
    test_exception_timeout_cancel=AdaptiveChecks.test_20_errors_timeout_cancel_clear_and_no_partial_session

    async def test_abstain_recovery_and_actual_hidden_guard(self):
        cfg=self.cfg(['list_project_tasks'])
        from scripts.check_tool_discovery import activate
        async with MCPClientManager(cfg,self.tools) as manager:
            a=self.agent(cfg,[response(calls=[call('hidden',PROJECT,'{"project":"mini"}'),activate(PROJECT)]),
                              response(calls=[call('real',PROJECT,'{"project":"mini"}')]),response('TASK-1')])
            await self.handle(a,'hello')
            self.assertNotIn(PROJECT,self.visible(0));self.assertIn(PROJECT,self.visible(1))
            self.assertEqual(sum(e['executed'] for e in manager.audit),1)
            self.assertIn('mcp_tool_not_visible_in_request',json.dumps(a.session.history()))
            assert_pairs(self,a.session.history())


class RoutingEvaluationChecks(unittest.IsolatedAsyncioTestCase):
    async def test_metric_denominators(self):
        a=selection_metrics([],['a'],['a']);b=selection_metrics(['a','x'],['a','b'],['a','b'])
        c=selection_metrics([],[],[]);d=selection_metrics(['x'],[],[])
        s=summarize([a,b,c,d])
        self.assertEqual(s['precision_denominator'],1);self.assertEqual(s['precision'],.5)
        self.assertEqual(s['recall'],.25);self.assertEqual(s['false_abstention_rate'],.5)
        self.assertEqual(s['correct_abstention_rate'],.5);self.assertEqual(s['false_preselection_rate'],.5)
        self.assertEqual(s['multi_denominator'],1);self.assertEqual(s['multi_tool_full_recall'],0)
        self.assertIsNone(c['precision']);self.assertIsNone(c['recall']);self.assertIsNone(summarize([])['recall'])

    async def test_dataset_is_independent_and_bounded(self):
        cases=load_cases();self.assertGreaterEqual(len(cases),50)
        self.assertGreaterEqual(sum(not c['required_tools'] for c in cases),20)
        self.assertEqual({c['split'] for c in cases},{'design','heldout'})
        from mybot.evaluation.tool_agent import load_cases as agent_cases
        self.assertEqual(len(agent_cases()),12);self.assertEqual(len(agent_cases('routing')),10)
        with self.assertRaises(ValueError):agent_cases('../../config/config')

    async def test_gold_mutation_same_runtime_selection(self):
        from mybot.evaluation.tool_retrieval import synthetic_catalog
        from mybot.config import GatewayConfig
        catalog=synthetic_catalog('hybrid');catalog.config.update(routing_mode='adaptive',selection_policy='selective')
        context=ContextManager(GatewayConfig(context_token_budget={'input_limit':160000}, ))
        c=deepcopy(load_cases()[0]);a=route_query(c['query'],catalog,context)
        c['required_tools']=['CANARY'];c['acceptable_tools']=['CANARY']
        b=route_query(c['query'],catalog,context)
        self.assertEqual(a.selected_tool_names,b.selected_tool_names)
        self.assertNotEqual(selection_metrics(a.selected_tool_names,[],[])['precision'],selection_metrics(b.selected_tool_names,b.selected_tool_names,b.selected_tool_names)['precision'])

    async def test_four_modes_shared_core_and_no_live(self):
        with patch('mybot.evaluation.tool_agent.build_client',side_effect=AssertionError('no real API')):
            r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), modes=MODES,limits=Limits(max_cases=2))
        self.assertEqual(r['complete_paired_cases'],2)
        for m in MODES:self.assertEqual(r['overall'][m]['task_success_count'],2)
        self.assertIsNone(r['actual_tokens']);self.assertIsNone(r['actual_cost'])
        for row in r['results']:
            if row['agent_mode']=='adaptive_selective_hybrid':
                self.assertEqual(row['routing_diagnostics']['selection_policy'],'selective')
            elif row['agent_mode']=='adaptive_hybrid':
                self.assertEqual(row['routing_diagnostics']['selection_policy'],'legacy')

    async def test_core_negative_metrics(self):
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), modes=('adaptive_selective_hybrid',))
        rows=r['results'];self.assertEqual(len(rows),12)
        negative=[r for r in rows if r['category'] in ('no_tool','no_match')]
        self.assertEqual(len(negative),2)
        self.assertTrue(all(r['correct_abstention'] for r in negative))
        self.assertTrue(all(not r['false_preselection'] for r in negative))
        self.assertEqual(r['overall']['adaptive_selective_hybrid']['task_success_count'],12)
        self.assertTrue(all(r['actual_mcp_calls']==0 for r in negative))

    async def test_real_owner_task_cancel_cleans(self):
        MCPChecks.setUp(self)
        from scripts.check_tool_agent_eval import SequenceClient
        from mybot.evaluation.tool_agent import load_cases as core_cases
        cfg=MCPChecks.fixture_config(self,['delay'])
        case=deepcopy(core_cases()[0]);case['prompt']='delay'
        with patch('mybot.evaluation.tool_agent.demo_server',return_value=cfg.mcp_servers['test']), patch('mybot.evaluation.tool_agent.load_cases',return_value=[case]):
            r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), modes=('adaptive_selective_hybrid',),limits=Limits(max_cases=1,task_timeout=1),
                client_factory=lambda *args:SequenceClient([response(calls=[call('delay','mcp__catalog__delay','{}')])]))
        self.assertEqual(r['results'][0]['failure_category'],'model_timeout')
        self.assertEqual(r['results'][0]['actual_mcp_calls'],1)
        self.assertFalse(MCPChecks.alive(self))

    async def test_incomplete_and_live_gate(self):
        for options in ({'live':True},{'confirm_api_cost':True}):
            with patch('mybot.evaluation.tool_agent.build_client',side_effect=AssertionError('no API')):
                with self.assertRaises(ValueError):await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), modes=('adaptive_selective_hybrid',),**options)
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), modes=('adaptive_selective_hybrid',),limits=Limits(max_cases=1,max_requests=1))
        self.assertEqual(r['incomplete_count'],1);self.assertIsNone(r['results'][0]['task_success'])
        self.assertEqual(r['overall']['adaptive_selective_hybrid']['selection_quality']['cases'],0)

    async def test_forced_abstention_manual_recovery(self):
        original=AdaptiveToolRouter.route
        def miss(router,*args,**kwargs):
            with patch.object(router.catalog,'ranked_names',return_value=[]):return original(router,*args,**kwargs)
        with patch.object(AdaptiveToolRouter,'route',miss):
            r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), modes=('adaptive_selective_hybrid',),limits=Limits(max_cases=1))
        row=r['results'][0];self.assertTrue(row['task_success']);self.assertTrue(row['recovered_by_manual_discovery'])
        self.assertEqual(row['actual_mcp_calls'],1);self.assertEqual(row['llm_requests'],4)

    async def test_challenge_builtin_real_effect_and_cleanup(self):
        from mybot.evaluation.tool_agent import load_cases as agent_cases
        from scripts.check_tool_agent_eval import SequenceClient
        # The historical writer challenge must stop at its absent schema.
        with patch('mybot.evaluation.tool_agent.load_cases',return_value=[agent_cases('routing')[-1]]):
            from mybot.config import GatewayConfig
            r=await evaluate(modes=('eager','adaptive_selective_hybrid'),limits=Limits(max_cases=1),
                base_config=GatewayConfig(context_token_budget={'input_limit':160000}, ))
        for row in r['results']:
            self.assertFalse(row['task_success']);self.assertEqual(row['actual_mcp_calls'],0)
            self.assertEqual(row['tool_failures'],0)
            self.assertEqual(row['tool_calls'],0)  # FixedClient refuses the absent schema before dispatch.
            self.assertEqual(row['llm_requests'],1)


def check_routing_confidence():
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (ConfidenceChecks,RoutingEvaluationChecks))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':check_routing_confidence()
