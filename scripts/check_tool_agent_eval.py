"""Phase16 harness tests: fake providers and real local stdio only."""
import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

from mybot.config import GatewayConfig
from mybot.tools import ToolResult
from mybot.mcp_client.manager import MCPClientManager
from mybot.evaluation.tool_agent import (evaluate,Limits,FixedClient,Observation,MeasuringClient,
    usage_values,token_totals,validate_prices,estimated_cost,pair_messages,load_cases,grade,save_report)
from scripts.check_session import response,call
from scripts.compare_tool_discovery import compare


class FakeLive:
    def __init__(self,usage=None):
        self.chat=N(completions=N(create=self.create));self.options=None;self.closed=False;self.usage=usage;self.calls=0
    def with_options(self,**kwargs):self.options=kwargs;return self
    async def close(self):self.closed=True
    async def create(self,**kwargs):
        self.calls+=1
        if len(kwargs['messages'])==2:
            case=next(c for c in load_cases() if c['prompt']==kwargs['messages'][-1]['content'])
            progressive=any(t['function']['name']=='search_mcp_tools' for t in kwargs['tools'])
            self.script=FixedClient(case['offline'],progressive)
        r=await self.script.create(**kwargs);r.usage=self.usage;return r


class SequenceClient:
    def __init__(self,items):self.items=iter(items);self.chat=N(completions=N(create=self.create))
    async def create(self,**kwargs):return next(self.items)


class AgentEvalChecks(unittest.IsolatedAsyncioTestCase):
    async def test_01_defaults_no_live_client_and_three_modes(self):
        with patch('mybot.evaluation.tool_agent.build_client',side_effect=AssertionError('No real provider')):
            report=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), )
        self.assertEqual(report['mode'],'offline');self.assertEqual(report['sample_count'],36)
        self.assertIsNone(report['actual_tokens']);self.assertIsNone(report['actual_cost']);self.assertIsNone(report['live_task_success_rate'])
        self.assertEqual(report['complete_paired_cases'],12)
        self.assertEqual(report['overall']['eager']['task_success_rate'],1)
        self.assertEqual(report['overall']['progressive_hybrid']['task_success_rate'],1)
        self.assertEqual(report['overall']['progressive_literal']['retrieval_failure_count'],1)
        self.assertTrue(all(r['tool_call_ids_paired'] for r in report['results']))
        self.assertTrue(all(r['cached_input_tokens'] is None for r in report['results']))

    async def test_02_live_requires_both_flags(self):
        with patch('mybot.evaluation.tool_agent.build_client',side_effect=AssertionError('No API')):
            for opts in ({'live':True},{'confirm_api_cost':True},{'live':1},{'live':True,'confirm_api_cost':1}):
                with self.subTest(opts=opts),self.assertRaises(ValueError):await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), **opts)

    async def test_03_live_mock_usage_retry_and_count(self):
        fake=FakeLive(N(prompt_tokens=100,completion_tokens=10,total_tokens=110,prompt_tokens_details=N(cached_tokens=20)))
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), live=True,confirm_api_cost=True,limits=Limits(max_cases=1),client_factory=lambda c:fake)
        self.assertEqual(fake.options,dict(max_retries=0,timeout=10.0));self.assertTrue(fake.closed)
        self.assertEqual(fake.calls,10);self.assertEqual(r['actual_tokens']['prompt_tokens'],1000)
        self.assertEqual(r['actual_tokens']['cached_input_tokens'],200)
        self.assertEqual(r['incomplete_count'],0)

    async def test_04_request_budget_and_partial_pairs(self):
        fake=FakeLive()
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), live=True,confirm_api_cost=True,limits=Limits(max_cases=2,max_requests=3),client_factory=lambda c:fake)
        self.assertEqual(fake.calls,3);self.assertGreater(r['incomplete_count'],0)
        self.assertEqual(r['complete_paired_cases'],0)
        self.assertIsNone(r['paired_differences']['progressive_literal']['task_success_delta'])
        for row in r['results']:
            if row['status']=='incomplete':
                self.assertIsNone(row['task_success']);self.assertEqual(row['failure_category'],'request_budget_exceeded')

    async def test_05_usage_missing_and_cache_missing(self):
        self.assertTrue(all(v is None for v in usage_values(None).values()))
        self.assertIsNone(usage_values(N(prompt_tokens=10,completion_tokens=2,total_tokens=12))['cached_input_tokens'])
        self.assertEqual(usage_values({'prompt_tokens':10,'completion_tokens':2,'total_tokens':12,'prompt_tokens_details':{'cached_tokens':3}})['cached_input_tokens'],3)
        self.assertIsNone(usage_values({'prompt_tokens':10,'prompt_tokens_details':{'cached_tokens':11}})['cached_input_tokens'])
        self.assertIsNone(usage_values({'prompt_tokens':True})['prompt_tokens'])
        self.assertIsNone(token_totals([usage_values(None)],2)['prompt_tokens'])

    async def test_06_explicit_prices_only(self):
        tokens=dict(prompt_tokens=100,completion_tokens=10,cached_input_tokens=20)
        price=validate_prices({'currency':'USD','input_price_per_million':2,'output_price_per_million':4,'cached_input_price_per_million':.5})
        self.assertAlmostEqual(estimated_cost(tokens,price)['amount'],.00021)
        self.assertIsNone(estimated_cost(tokens,None))
        self.assertIsNone(estimated_cost(dict(tokens,cached_input_tokens=None),price))
        self.assertIsNone(estimated_cost(tokens,{k:v for k,v in price.items() if not k.startswith('cached')}))
        for p in ({},dict(price,currency='https://secret'),dict(price,input_price_per_million=-1),dict(price,unknown=1),dict(price,input_price_per_million=float('nan'))):
            with self.assertRaises(ValueError):validate_prices(p)

    async def test_07_same_prompt_isolated_workspaces_and_config(self):
        observed=[]
        def factory(config,case,mode):
            observed.append((config,case['prompt']))
            return FixedClient(case['offline'],mode!='eager')
        base=GatewayConfig(context_token_budget={'input_limit':160000}, mcp_enabled=False,mcp_servers={},mcp_discovery={})
        # Configuration can contain a remote server; harness must replace, never connect to it.
        base.mcp_servers={'private':{'transport':'http','url':'https://private.invalid'}}
        r=await evaluate(limits=Limits(max_cases=1),base_config=base,client_factory=factory)
        self.assertEqual(len({prompt for _,prompt in observed}),1)
        self.assertEqual(len({str(c.workspace) for c,_ in observed}),3)
        for cfg,_ in observed:
            self.assertEqual(set(cfg.mcp_servers),{'catalog'});self.assertNotIn('url',cfg.mcp_servers['catalog'])
            self.assertFalse(cfg.storage_backend != 'memory' or cfg.skills_enabled or cfg.debug)
            self.assertFalse(cfg.workspace.exists());self.assertEqual(cfg.storage_backend, 'memory')
        self.assertTrue(all(x['task_success'] for x in r['results']))

    async def test_08_final_self_report_not_evidence(self):
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1),modes=('eager',),client_factory=lambda *a:SequenceClient([response('TASK-1 TASK-2')]))
        row=r['results'][0];self.assertTrue(row['final_answer_correct']);self.assertFalse(row['tool_call_success']);self.assertFalse(row['task_success'])

    async def test_09_wrong_arguments_not_success(self):
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1),modes=('eager',),client_factory=lambda *a:SequenceClient([
            response(calls=[call('a','mcp__catalog__list_project_tasks','{"project":"wrong"}')]),response('TASK-1 TASK-2')]))
        row=r['results'][0];self.assertEqual(row['actual_mcp_calls'],1);self.assertFalse(row['task_success'])
        self.assertEqual(row['failure_category'],'invalid_tool_arguments')

    async def test_10_snapshot_same_batch(self):
        name='mcp__catalog__list_project_tasks'
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1),modes=('progressive_literal',),client_factory=lambda *a:SequenceClient([
            response(calls=[call('a','activate_mcp_tools',json.dumps({'names':[name]})),call('b',name,'{"project":"mini","status":"pending"}')]),response('TASK-1 TASK-2')]))
        row=r['results'][0];self.assertEqual(row['actual_mcp_calls'],0);self.assertFalse(row['task_success'])
        self.assertIn('tool_not_visible',[row['failure_category'],*row['secondary_failures']]);self.assertTrue(row['tool_call_ids_paired'])

    async def test_11_context_budget_before_model(self):
        with patch('mybot.evaluation.tool_agent.build_client',side_effect=AssertionError('No API')):
            r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1,input_limit=256),modes=('eager',))
        row=r['results'][0];self.assertEqual(row['llm_requests'],0);self.assertEqual(row['failure_category'],'context_budget_exceeded')

    async def test_12_react_limit(self):
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1,max_react_steps=1),modes=('eager',))
        self.assertEqual(r['results'][0]['failure_category'],'react_limit')

    async def test_13_recovered_error_not_terminal_failure(self):
        def factory(config,case,mode):
            client=FixedClient(case['offline'],True)
            client.actions.insert(0,('activate_mcp_tools',{'names':['not-a-tool']},None))
            return client
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1),modes=('progressive_literal',),client_factory=factory)
        row=r['results'][0];self.assertTrue(row['task_success']);self.assertIsNone(row['failure_category'])
        self.assertEqual(row['recovered_errors'],['activation_failed'])

    async def test_14_unsupported_shape_no_json_fallback(self):
        class Unsupported(FakeLive):
            async def create(self,**kwargs):return N(choices=[N(message=N(content='{"tool":"fake"}'))],usage=None)
        fake=Unsupported()
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), live=True,confirm_api_cost=True,limits=Limits(max_cases=1),modes=('eager',),client_factory=lambda c:fake)
        self.assertEqual(r['results'][0]['failure_category'],'provider_unsupported');self.assertFalse(r['results'][0]['task_success'])

    async def test_15_structured_unsupported_api_error_redacted(self):
        class Error(Exception):status_code=400;code='unsupported_parameter'
        class Unsupported(FakeLive):
            async def create(self,**kwargs):raise Error('https://secret.invalid?token=SENSITIVE')
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), live=True,confirm_api_cost=True,limits=Limits(max_cases=1),modes=('eager',),client_factory=lambda c:Unsupported())
        self.assertEqual(r['results'][0]['failure_category'],'provider_unsupported');self.assertNotIn('SENSITIVE',json.dumps(r))

    async def test_16_task_timeout_owner_cleanup(self):
        managers=[]
        class Manager(MCPClientManager):
            async def __aenter__(self):
                value=await super().__aenter__();managers.append(self);return value
        class Slow:
            def __init__(self):self.chat=N(completions=N(create=self.create))
            async def create(self,**kwargs):await asyncio.sleep(10)
        with patch('mybot.evaluation.tool_agent.MCPClientManager',Manager):
            r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1,task_timeout=1),modes=('eager',),client_factory=lambda *a:Slow())
        self.assertEqual(r['results'][0]['failure_category'],'model_timeout')
        self.assertEqual(len(managers),1);self.assertTrue(managers[0].closed);self.assertEqual(managers[0].clients,{})
        self.assertIs(managers[0].owner,asyncio.current_task())

    async def test_17_cancel_owner_cleanup(self):
        managers=[];ready=asyncio.Event()
        class Manager(MCPClientManager):
            async def __aenter__(self):v=await super().__aenter__();managers.append(self);return v
        class Slow:
            def __init__(self):self.chat=N(completions=N(create=self.create))
            async def create(self,**kwargs):ready.set();await asyncio.sleep(10)
        with patch('mybot.evaluation.tool_agent.MCPClientManager',Manager):
            task=asyncio.create_task(evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1),modes=('eager',),client_factory=lambda *a:Slow()))
            await asyncio.wait_for(ready.wait(),5);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(managers[0].closed);self.assertEqual(managers[0].clients,{})

    async def test_18_total_timeout_stops_later_tasks(self):
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=2,total_timeout=.001))
        self.assertEqual(r['incomplete_count'],6);self.assertEqual(sum(x['llm_requests'] for x in r['results']),0)
        self.assertTrue(all(x['failure_category']=='total_time_exceeded' for x in r['results']))

    async def test_19_report_privacy_and_exclusive_save(self):
        r=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1),modes=('eager',))
        text=json.dumps(r)
        for forbidden in ('TASK-1','TASK-2','"arguments"','"prompt"','api_key','base_url','/private/tmp','"reply"'):
            self.assertNotIn(forbidden,text)
        with tempfile.TemporaryDirectory() as folder:
            a=save_report(r,folder);b=save_report(r,folder)
            self.assertNotEqual(a,b);self.assertEqual(json.loads(a.read_text()),r)

    async def test_20_error_taxonomy_and_plan_recovery(self):
        obs=Observation(load_cases()[0])
        for name,error,category in [('activate_mcp_tools','activation_schema_limit','schema_budget_exceeded'),
             ('create_plan','Invalid target status','planning_failed'),('mcp__catalog__list_project_tasks','Invalid MCP arguments','invalid_tool_arguments')]:
            obs.tool(name,{},ToolResult(success=False,error=error));self.assertEqual(obs.errors[-1],category)

    async def test_21_no_tool_case_unnecessary_calls_fail(self):
        case=load_cases()[9];obs=Observation(case);obs.finished=True
        self.assertTrue(grade(obs,'4',False,[])['task_success'])
        self.assertFalse(grade(obs,'42',False,[])['task_success'])
        obs.tool('list_files',{},ToolResult(success=True,output='[]'))
        self.assertFalse(grade(obs,'4',False,[])['task_success'])

    async def test_22_pair_validator(self):
        messages=[{'role':'assistant','tool_calls':[{'id':'1'}]},{'role':'tool','tool_call_id':'1'}]
        self.assertTrue(pair_messages(messages,True));self.assertFalse(pair_messages(messages[:1],True))
        self.assertFalse(pair_messages(messages+messages,True));self.assertFalse(pair_messages([{'role':'tool','tool_call_id':'x'}],True))

    async def test_23_limits_validate(self):
        for kwargs in ({'max_cases':0},{'max_requests':True},{'repeats':6},{'max_output_tokens':4097},{'total_timeout':float('inf')},{'task_timeout':0}):
            with self.assertRaises(ValueError):Limits(**kwargs)
        with self.assertRaises(ValueError):await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), modes=('eager','eager'))

    async def test_24_phase15_comparison_unchanged(self):
        r=await compare()
        self.assertTrue(all(x['task_success'] for x in r['results']))
        self.assertEqual([x['cumulative_schema_chars'] for x in r['results']],[116276,12004,116276,12044,174414,23447])


def check_tool_agent_eval():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AgentEvalChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_tool_agent_eval()
