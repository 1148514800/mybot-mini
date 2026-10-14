"""Offline framework verification; no live API, keys or normal workspace access."""
import asyncio
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

from mybot.config import GatewayConfig, PROJECT_DIR
from mybot.evaluation.grader import grade, summarize
from mybot.evaluation.runner import OfflineClient, evaluate, load_cases, save_report
from mybot.evaluation.trace import Trace
from scripts.eval_agent import parser


class EvaluationChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cases = load_cases()
        self.config = GatewayConfig(skills_enabled=False,skills_path=PROJECT_DIR/'skills',session_persist=False,
                                    context_enabled=True,context_max_chars=40000,context_tool_result_max_chars=1000,
                                    debug=False,max_react_steps=16,api_key='PRIVATE_SENTINEL_CREDENTIAL')

    async def run_cases(self, cases=None, **kwargs):
        return await evaluate(self.cases if cases is None else cases,base_config=self.config,**kwargs)

    async def test_offline_no_real_api_and_default(self):
        self.assertFalse(parser().parse_args([]).live)
        self.assertTrue(parser().parse_args(['--live']).live)
        with patch('mybot.evaluation.runner.build_client',side_effect=AssertionError('No API')):
            report = await self.run_cases()
        self.assertEqual(report['mode'],'offline')
        self.assertFalse(report['ability_score'])
        self.assertEqual(len(report['results']),20)
        self.assertTrue(all(r['task_success'] for r in report['results']))
        self.assertEqual(report['overall']['off']['task_success_count'],10)

    async def test_workspace_registry_session_isolation(self):
        paths, registries, sessions = [], [], []
        from mybot.evaluation.trace import TracedAgent
        class Capture(TracedAgent):
            def __init__(agent,*args,**kwargs):
                super().__init__(*args,**kwargs)
                paths.append(agent.config.workspace)
                registries.append(agent.tools)
                sessions.append(agent.session)
                self.assertFalse(agent.config.session_persist)
                self.assertFalse(agent.config.debug)
                self.assertFalse((agent.config.workspace/'hello.txt').exists())
                self.assertEqual(agent.session.history(),[])
        with patch('mybot.evaluation.runner.TracedAgent',Capture):
            await self.run_cases([self.cases[9]],repeats=2)
        self.assertEqual(len(set(paths)),4)
        self.assertEqual(len({id(r) for r in registries}),4)
        self.assertEqual(len({id(r) for r in sessions}),4)
        self.assertTrue(all(not p.exists() for p in paths))

    async def test_tool_trace_real_results(self):
        report = await self.run_cases([self.cases[9]],groups=(False,))
        r = report['results'][0]
        self.assertEqual(r['tool_calls'],1)
        self.assertEqual(r['tool_failures'],0)
        self.assertEqual(r['llm_requests'],2)
        self.assertEqual([e['name'] for e in r['trace'] if e['event']=='tool'],['write_file'])
        self.assertTrue(r['checks']['artifact:hello.txt'])

    async def test_failed_tool_not_success(self):
        case = deepcopy(self.cases[2])
        case['offline']['actions'][0]['args']['path']='absent.txt'
        report = await self.run_cases([case],groups=(False,))
        r = report['results'][0]
        self.assertEqual(r['tool_failures'],1)
        self.assertFalse(r['task_success'])
        self.assertFalse(r['process_checks']['tool_results'])

    async def test_expected_missing_file(self):
        r = (await self.run_cases([self.cases[7]],groups=(False,)))['results'][0]
        self.assertTrue(r['task_success'])
        self.assertEqual(r['tool_failures'],1)
        self.assertTrue(r['checks']['failure:read_file'])

    async def test_self_claim_without_artifact_fails(self):
        case = deepcopy(self.cases[9]); case['offline']['actions']=[]
        r = (await self.run_cases([case],groups=(False,)))['results'][0]
        self.assertFalse(r['task_success'])
        self.assertFalse(r['checks']['artifact:hello.txt'])

    async def test_wrong_file_contents_fails(self):
        case = deepcopy(self.cases[9]); case['offline']['actions'][0]['args']['content']='wrong'
        r = (await self.run_cases([case],groups=(False,)))['results'][0]
        self.assertFalse(r['task_success'])
        self.assertFalse(r['checks']['artifact:hello.txt'])

    async def test_skill_selection_and_irrelevant_loading(self):
        report = await self.run_cases([self.cases[4]])
        a,b = report['results']
        self.assertEqual(a['skill_selected'],[])
        self.assertEqual(b['skill_selected'],[])
        self.assertTrue(b['task_success'])
        case=deepcopy(self.cases[6]);case['offline']['actions']=[{'tool':'load_skill','args':{'name':'file-summary'}}]
        r=(await self.run_cases([case],groups=(True,)))['results'][0]
        self.assertEqual(r['skill_usage']['unexpected_skills'],['file-summary'])
        self.assertTrue(r['task_success'])

    async def test_global_request_limit_stops_calls(self):
        r=await self.run_cases(max_requests=1)
        self.assertEqual(sum(v['llm_requests'] for v in r['results']),1)
        self.assertTrue(all(v['error']=='model_request_limit' for v in r['results'][1:]))
        self.assertTrue(all(not v['task_success'] for v in r['results'][1:]))

    async def test_timeout_and_error_cleaned(self):
        paths=[]
        def factory(config,case):
            paths.append(config.workspace)
            async def create(**kwargs): await asyncio.sleep(2)
            return N(chat=N(completions=N(create=create)))
        r=(await self.run_cases([self.cases[0]],groups=(False,),timeout=0.01,client_factory=factory))['results'][0]
        self.assertEqual(r['error'],'case_timeout')
        self.assertFalse(r['task_success'])
        self.assertFalse(paths[0].exists())
        def broken(config,case):
            async def create(**kwargs): raise RuntimeError('PRIVATE_SENTINEL_ERROR_BODY')
            return N(chat=N(completions=N(create=create)))
        report=await self.run_cases([self.cases[0]],groups=(False,),client_factory=broken)
        self.assertEqual(report['results'][0]['error'],'llm_error')
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(report))

    async def test_live_explicit_mock_only_and_close(self):
        clients=[]
        class Client(OfflineClient):
            async def close(client): client.closed=True
        def factory(config):
            client=Client(self.cases[0],False);client.closed=False;clients.append(client);return client
        with patch('mybot.evaluation.runner.build_client',side_effect=AssertionError('No real API')):
            report=await self.run_cases([self.cases[0]],live=True,groups=(False,),client_factory=factory)
        self.assertEqual(report['mode'],'live')
        self.assertTrue(clients[0].closed)
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(report))

    async def test_missing_usage_null_and_usage_totals(self):
        report=await self.run_cases([self.cases[0]])
        self.assertIsNone(report['results'][0]['input_tokens'])
        self.assertIsNone(report['overall']['auto']['output_tokens'])
        class Usage(OfflineClient):
            async def create(client,**kwargs):
                r=await super(Usage,client).create(**kwargs)
                r.usage=N(prompt_tokens=11,completion_tokens=7)
                return r
        report=await self.run_cases([self.cases[9]],groups=(False,),client_factory=lambda cfg,c:Usage(c,False))
        self.assertEqual(report['results'][0]['input_tokens'],22)
        self.assertEqual(report['results'][0]['output_tokens'],14)

    async def test_incomplete_plan_and_react_limit_fail(self):
        case=deepcopy(self.cases[3]);case['offline']['actions']=case['offline']['actions'][:1]
        r=(await self.run_cases([case],groups=(False,)))['results'][0]
        self.assertFalse(r['planning_completed'])
        self.assertFalse(r['task_success'])
        self.config.max_react_steps=1
        r=(await self.run_cases([self.cases[9]],groups=(False,)))['results'][0]
        self.assertEqual(r['error'],'react_limit')
        self.assertFalse(r['task_success'])

    async def test_review_real_hits_and_false_positive(self):
        case=deepcopy(self.cases[5]);case['offline']['reply']='DEFECT: DIV_ZERO\nDEFECT: FALSE_LOOP'
        r=(await self.run_cases([case],groups=(False,)))['results'][0]
        self.assertEqual(r['review_findings'],{'true_positives':1,'false_positives':1,'false_negatives':1,'precision':0.5,'recall':0.5})
        self.assertFalse(r['task_success'])
        self.assertTrue(r['manual_review_required'])

    async def test_context_clipping_visible_in_actual_requests(self):
        r=(await self.run_cases([self.cases[8]],groups=(False,)))['results'][0]
        requests=[e for e in r['trace'] if e['event']=='llm_request']
        self.assertFalse(requests[0]['tool_result_clipped'])
        self.assertTrue(requests[1]['tool_result_clipped'])
        self.assertLess(requests[1]['request_chars'],40000)
        self.assertTrue(r['task_success'])

    async def test_json_report_recomputable_and_private(self):
        report=await self.run_cases()
        with tempfile.TemporaryDirectory() as folder:
            one=save_report(report,folder);two=save_report(report,folder)
            loaded=json.loads(one.read_text());self.assertNotEqual(one,two)
        self.assertEqual(loaded['overall'],summarize(loaded['results']))
        text=json.dumps(report)
        for private in ('PRIVATE_SENTINEL','api_key','Project Orion uses Python','Synthetic filler line.','static source','SKILL.md','Hello, evaluation!'):
            self.assertNotIn(private,text)
        again=await self.run_cases()
        self.assertEqual([r['checks'] for r in report['results']],[r['checks'] for r in again['results']])

    async def test_wrong_source_and_setup_error_recorded(self):
        case=deepcopy(self.cases[2]);case['fixtures']['other.txt']='unrelated'
        case['offline']['actions'][0]['args']['path']='other.txt'
        r=(await self.run_cases([case],groups=(False,)))['results'][0]
        self.assertFalse(r['checks']['read:fact.txt'])
        self.assertFalse(r['task_success'])
        self.config.skills_path=PROJECT_DIR/'missing-eval-skill-directory'
        r=(await self.run_cases([self.cases[0]],groups=(True,)))['results'][0]
        self.assertEqual(r['error'],'case_setup_error')
        self.assertFalse(r['task_success'])

    async def test_limits_and_fixture_validation(self):
        for args in ({'live':'true'},{'repeats':0},{'max_cases':0},{'max_requests':0},{'timeout':float('nan')},{'groups':(False,False)}):
            with self.assertRaises(ValueError): await self.run_cases(**args)
        case=deepcopy(self.cases[0]);case['fixtures']={'../escape':'bad'}
        with self.assertRaises(ValueError): await self.run_cases([case])
        self.assertEqual(len(self.cases),12)
        self.assertFalse(any('load_skill' in c['prompt'] for c in self.cases))


def check_evaluation():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EvaluationChecks))
    if not result.wasSuccessful(): raise SystemExit(1)


if __name__=='__main__': check_evaluation()
