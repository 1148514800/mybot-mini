"""Phase 9 scoring experiments: synthetic scripts only, never real API calls."""
import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

from mybot.agent.planning import Plan
from mybot.config import GatewayConfig, PROJECT_DIR
from mybot.evaluation.runner import evaluate, load_cases, OfflineClient, select_cases, task_prompt
from mybot.evaluation.trace import Trace, TracedAgent, error_category, PLAN_ERRORS
from mybot.evaluation.grader import grade, summarize
from mybot.evaluation.history import analyze_report
from mybot.agent.context import ContextBuilder
from mybot.tools import build_default_tool_registry, ToolResult
from scripts.eval_agent import parser


class EvaluationV2Checks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cases={c['id']:c for c in load_cases()}
        self.config=GatewayConfig(skills_enabled=False,context_enabled=True,
                                 skills_path=PROJECT_DIR/'skills',context_max_chars=40000,
                                 context_tool_result_max_chars=1000,debug=False,max_react_steps=16,
                                 api_key='PRIVATE_TEST_SENTINEL')

    async def run_case(self,id='file-summary',group='auto',case=None,**kwargs):
        r=await evaluate([case or self.cases[id]],base_config=self.config,groups=(group,),**kwargs)
        return r['results'][0]

    async def test_auto_simple_and_complex_do_not_need_skill(self):
        for id in ('file-summary','code-review','complex-code-review','complex-document-summary'):
            r=await self.run_case(id)
            retired = any(a.get('tool') == 'write_file' for a in self.cases[id]['offline']['actions'])
            self.assertEqual(r['task_success'], not retired); self.assertEqual(r['strict_pass'], not retired)
            if retired: self.assertGreater(r['tool_failures'], 0)
            self.assertEqual(r['skill_selected'],[])
            self.assertEqual(r['skill_usage']['load_calls'],0)

    async def test_recovered_error_outcome_true_process_false(self):
        case=deepcopy(self.cases['multi-step'])
        # Attempt completion before activation, then execute the valid script.
        case['offline']['actions'].insert(1,{'tool':'update_plan','args':{'step':1,'status':'completed'}})
        r=await self.run_case(case=case)
        self.assertFalse(r['task_success']);self.assertFalse(r['instruction_followed'])
        self.assertFalse(r['process_clean']);self.assertFalse(r['strict_pass'])
        self.assertEqual(r['planning_failure_categories'],{'plan_not_in_progress':1})
        self.assertFalse(r['planning_completed'])

    async def test_wrong_artifact_does_not_pass(self):
        case=deepcopy(self.cases['file-summary']);case['offline']['actions'][1]['args']['content']='wrong'
        r=await self.run_case(case=case)
        self.assertFalse(r['task_success']);self.assertFalse(r['strict_pass'])
        self.assertFalse(r['process_clean'])

    async def test_guided_instruction_independent_and_wrong_skill(self):
        case=deepcopy(self.cases['file-summary']);case['offline']['guided_actions']=case['offline']['actions']
        r=await self.run_case(case=case,group='guided')
        self.assertFalse(r['task_success']);self.assertFalse(r['instruction_followed'])
        self.assertFalse(r['strict_pass'])
        case['offline']['guided_actions']=[{'tool':'load_skill','args':{'name':'code-review'}}]+case['offline']['actions']
        r=await self.run_case(case=case,group='guided')
        self.assertEqual(r['skill_selected'],['code-review']);self.assertFalse(r['instruction_followed'])
        self.assertEqual(r['skill_usage']['unexpected_skills'],['code-review'])
        r=await self.run_case(group='guided')
        self.assertTrue(r['instruction_followed']);self.assertEqual(r['skill_usage']['successful_loads'],1)
        self.assertEqual(r['skill_usage']['successful_references'],1)
        self.assertGreater(r['skill_usage']['requests_with_skill_content'],0)
        self.assertIsNone(r['skill_usage']['extra_tokens'])
        self.assertIsNone(r['skill_usage']['input_tokens_with_skill_content'])

    async def test_late_guided_load_and_unfinished_plan_separate(self):
        case=deepcopy(self.cases['file-summary'])
        case['offline']['guided_actions']=case['offline']['actions']+[{'tool':'load_skill','args':{'name':'file-summary'}}]
        r=await self.run_case(case=case,group='guided')
        self.assertFalse(r['task_success']);self.assertFalse(r['instruction_followed'])
        self.assertFalse(r['instruction_checks']['requested_skill'])
        self.assertFalse(r['instruction_checks']['requested_skill_first'])
        case=deepcopy(self.cases['multi-step']);case['offline']['actions'].pop()
        r=await self.run_case(case=case)
        self.assertFalse(r['task_success']);self.assertFalse(r['process_clean'])
        self.assertFalse(r['instruction_followed']);self.assertFalse(r['strict_pass'])

    async def test_explicit_skill_requirement_in_auto(self):
        case=deepcopy(self.cases['code-review']);case['required_skill']='code-review'
        case['prompt']+=' 请明确使用 code-review Skill。'
        r=await self.run_case(case=case)
        self.assertTrue(r['task_success']);self.assertFalse(r['instruction_followed'])

    async def test_complex_review_joint_evidence_and_miss_false(self):
        case=deepcopy(self.cases['complex-code-review'])
        output=json.loads(case['offline']['reply']);output['findings'].pop()
        output['findings'].append({'file':'utils.py','function':'greeting','evidence':'limit + 1 extra item','trigger':'any','impact':'bad','fix':'change'})
        case['offline']['reply']=json.dumps(output)
        r=await self.run_case(case=case)
        self.assertFalse(r['task_success'])
        self.assertEqual(r['review_findings'],{'true_positives':3,'false_positives':1,'false_negatives':1,'precision':.75,'recall':.75})
        output['findings'][0]['evidence']='unsafe'  # file/function alone is insufficient
        case['offline']['reply']=json.dumps(output)
        r=await self.run_case(case=case)
        self.assertEqual(r['review_findings']['true_positives'],2)
        self.assertTrue(r['manual_review_required'])

    async def test_complex_docs_latest_omission_unsupported_and_order(self):
        base=deepcopy(self.cases['complex-document-summary'])
        for key,value in (('release_date','September 30'),('owner','Leo'),('constraints',[]),('unsupported','invented')):
            case=deepcopy(base)
            artifact=json.loads(case['offline']['actions'][-1]['args']['content']);artifact[key]=value
            case['offline']['actions'][-1]['args']['content']=json.dumps(artifact)
            r=await self.run_case(case=case)
            self.assertFalse(r['task_success'])
        artifact=json.loads(base['offline']['actions'][-1]['args']['content'])
        artifact['superseded'].reverse()
        base['offline']['actions'][-1]['args']['content']=json.dumps(artifact)
        self.assertFalse((await self.run_case(case=base))['task_success'])
        from mybot.evaluation.diagnostics import document_diagnostic, json_diagnostic
        parsed, detail = json_diagnostic(json.dumps(artifact))
        self.assertTrue(all(field['status'] == 'matched' for field in document_diagnostic(parsed, detail, base['expect']['document']['values'])['fields'].values()))
        base['offline']['actions']=base['offline']['actions'][1:]
        self.assertFalse((await self.run_case(case=base))['task_success'])

    async def test_actual_planning_errors_are_classified(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace=Path(folder).resolve()
            trace=Trace();agent=TracedAgent(N(),replace(self.config,workspace=workspace),build_default_tool_registry(workspace),ContextBuilder(workspace),trace=trace)
            async def execute(name,params):
                import contextlib,io
                with contextlib.redirect_stdout(io.StringIO()):
                    await agent._execute(name,json.dumps(params))
                return trace.events[-1]['error']
            self.assertEqual(await execute('update_plan',{'step':1,'status':'completed'}),'plan_missing')
            await execute('create_plan',{'steps':['first','second']})
            self.assertEqual(await execute('create_plan',{'steps':['first','second']}),'plan_recreation')
            self.assertEqual(await execute('update_plan',{'step':5,'status':'in_progress'}),'plan_invalid_step')
            self.assertEqual(await execute('update_plan',{'step':1,'status':'bad'}),'plan_invalid_status')
            self.assertEqual(await execute('update_plan',{'step':2,'status':'in_progress'}),'plan_step_order')
            self.assertEqual(await execute('update_plan',{'step':1,'status':'completed'}),'plan_not_in_progress')
            await execute('update_plan',{'step':1,'status':'in_progress'})
            self.assertEqual(await execute('update_plan',{'step':1,'status':'completed'}),'plan_unverified')
            self.assertEqual(error_category('update_plan',ToolResult(success=False,error='PRIVATE_ERROR_TEXT')),'other_tool_error')
            self.assertNotIn('PRIVATE_ERROR_TEXT',json.dumps(trace.events))

    async def test_duplicate_reads_are_efficiency_not_failure(self):
        case=deepcopy(self.cases['read-fact']);case['offline']['actions']+=case['offline']['actions']
        case['offline']['actions'][1]=deepcopy(case['offline']['actions'][1])
        case['offline']['actions'][1]['args']['path']='./fact.txt'
        r=await self.run_case(case=case)
        self.assertTrue(r['task_success']);self.assertTrue(r['process_clean'])
        self.assertEqual(r['duplicate_reads'],1);self.assertEqual(r['file_tools_before_plan'],2)

    async def test_three_group_isolation_prompts_and_guided_skip(self):
        paths,sessions,tools=[],[],[]
        class Capture(TracedAgent):
            def __init__(agent,*args,**kwargs):
                super().__init__(*args,**kwargs)
                paths.append(agent.config.workspace);sessions.append(agent.session);tools.append(agent.tools)
                self.assertEqual(agent.session.history(),[])
                self.assertFalse((agent.config.workspace/'summary.txt').exists())
        with patch('mybot.evaluation.runner.TracedAgent',Capture):
            r=await evaluate([self.cases['file-summary'],self.cases['greeting']],groups=('off','auto','guided'),base_config=self.config)
        self.assertEqual(len(r['results']),5)
        self.assertEqual(len(set(paths)),5);self.assertEqual(len({id(s) for s in sessions}),5)
        self.assertEqual(len({id(t) for t in tools}),5)
        self.assertTrue(all(not p.exists() for p in paths))
        a,b,c=r['results'][:3]
        self.assertEqual(a['prompt_sha256'],b['prompt_sha256']);self.assertNotEqual(a['prompt_sha256'],c['prompt_sha256'])

    async def test_case_selection_cli_and_errors(self):
        args=parser().parse_args(['--case-ids','multi-step,complex-code-review','--groups','off,auto,guided'])
        self.assertFalse(args.live)
        selected=select_cases(list(self.cases.values()),args.case_ids,10)
        self.assertEqual([c['id'] for c in selected],['multi-step','complex-code-review'])
        for kwargs in ({'case_ids':'bad'},{'case_ids':'greeting,greeting'},{'groups':'auto,auto'},{'groups':'unknown'}):
            with self.assertRaises(ValueError):await evaluate(base_config=self.config,**kwargs)

    async def test_hidden_annotations_never_in_initial_request(self):
        initial=[]
        class Capture(OfflineClient):
            async def create(client,**kwargs):
                if client.step==0:initial.append(kwargs['messages'])
                return await super(Capture,client).create(**kwargs)
        await evaluate([self.cases['complex-code-review'],self.cases['complex-document-summary']],base_config=self.config,
                       client_factory=lambda config,c:Capture(c,'off'))
        text=json.dumps(initial,ensure_ascii=False)
        for secret in ('path-escape','dict-state','October 20','500 USD','review_annotations','expected_skill'):
            self.assertNotIn(secret,text)

    async def test_legacy_readonly_unknown_and_recovered(self):
        old={'version':1,'mode':'live','results':[{'case_id':'multi-step','skills_enabled':True,'checks':{'no_runtime_error':True,'finished':True,'plan_complete':True,'planned':True,'tool_results':False,'artifact:result.txt':True,'skill_selection':False},
            'skill_selected':[],'tool_calls':1,'tool_failures':1,'llm_requests':2,'input_tokens':None,'output_tokens':None,'duration_seconds':1,
            'trace':[{'event':'tool','name':'update_plan','success':False,'error':'tool_failed','fixture_path':None}]}]}
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'v1.json';p.write_text(json.dumps(old));before=p.read_bytes()
            r=analyze_report(p);self.assertEqual(p.read_bytes(),before)
            custom=deepcopy(old);custom['results'][0]['case_id']='custom-v1'
            p.write_text(json.dumps(custom));self.assertIsNone(analyze_report(p)['results'][0]['instruction_followed'])
        v=r['results'][0]
        self.assertTrue(v['task_success']);self.assertFalse(v['process_clean'])
        self.assertEqual(v['planning_failure_categories'],{'unknown':1})
        self.assertIsNone(v['skill_usage']['extra_tokens'])
        self.assertTrue(r['analysis_only'])
        self.assertEqual(r['overall'],summarize(r['results']))

    async def test_limits_timeout_privacy_and_v2_report(self):
        with patch('mybot.evaluation.runner.build_client',side_effect=AssertionError('No API')):
            r=await evaluate(case_ids='complex-code-review,complex-document-summary',groups='off,auto,guided',max_requests=1,base_config=self.config)
        self.assertEqual(r['version'],2)
        self.assertEqual(sum(v['llm_requests'] for v in r['results']),1)
        self.assertTrue(all(not v['task_success'] for v in r['results']))
        self.assertNotIn('PRIVATE_TEST_SENTINEL',json.dumps(r))
        self.assertEqual(r['overall'],summarize(r['results']))


def check_evaluation_v2():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EvaluationV2Checks))
    if not r.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_evaluation_v2()
