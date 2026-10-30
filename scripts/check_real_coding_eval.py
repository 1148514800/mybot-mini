"""Offline Benchmark/Gold/real sandbox/SDK-boundary regression; never paid API."""
import asyncio
import contextlib
from dataclasses import replace
import hashlib
import io
import json
import math
import os
import pty
from pathlib import Path
import shutil
import select
import sys
import tempfile
import unittest
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, patch

from mybot.agent import AgentLoop
from mybot.agent.coding_controller import CodingTaskController, AutonomySettings
from mybot.config import GatewayConfig
from mybot.evaluation.coding_fixtures import load_benchmark, snapshot, write_images, create_repository, Image, RuntimeCase
from mybot.evaluation.coding_judge import judge, validate_case, validate_benchmark, run_suite, judge_images, trusted_seal
from mybot.evaluation.coding_live import Limits, RequestBudget, CodingClient, CodingEvaluationStop, live_client
from mybot.evaluation.coding_benchmark import evaluate, configuration, OfflineClient, save_report, run_task
from mybot.evaluation.coding_metrics import CodingTrace, BenchmarkAgent, case_metrics, summarize
from mybot.evaluation.tool_agent import usage_values, token_totals, validate_prices, estimated_cost
from mybot.tools import build_default_tool_registry
from mybot.tools.base import ToolResult
from mybot.tools.patch import ApplyPatchTool
from mybot.tools.run_command import RunCommandTool
from mybot.tools.command_approval import cli_command_approval, inspectable_command
from mybot.tools.read_file_range import ReadFileRangeTool
from mybot.mcp_client.approval import ApprovalDecision
from scripts.coding_benchmark_demo import DemoClient, demonstrate


class CodingEvaluationChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.benchmark=load_benchmark();self.case=next(c for c in self.benchmark.cases if c.runtime.id=='cache-ttl-001')
        self.fixed={**self.case.public,**self.case.reference}

    async def asyncSetUp(self):
        values=await validate_benchmark(self.benchmark)
        self.validation=next(v for v in values if v['case_id']==self.case.runtime.id)

    def clone_assets(self):
        dest=self.root/'assets';shutil.copytree(self.benchmark.root,dest);return dest

    def change_manifest(self, function):
        root=self.clone_assets();p=root/'manifest.json';doc=json.loads(p.read_text());function(doc);p.write_text(json.dumps(doc));return root

    async def score(self,candidate=None,**kw):
        candidate=self.fixed if candidate is None else candidate
        changed={p for p in candidate.keys()|self.case.public.keys() if candidate.get(p)!=self.case.public.get(p)}
        options=dict(benchmark=self.benchmark,seal=trusted_seal(),index_unchanged=True,journal_paths=changed,agent_state='edited_unverified')
        options.update(kw)
        return await judge(self.case,candidate,self.validation,**options)

    async def evaluation(self,**kw):
        options=dict(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=1,max_requests=12),case_ids=['cache-ttl-001'])
        options.update(kw);return await evaluate(**options)

    async def demo_run(self,policy='correct',**kw):
        return await self.evaluation(offline_client_factory=lambda public:DemoClient(policy),**kw)

    async def request(self,raw,budget=None,trace=None):
        trace=trace or CodingTrace();budget=budget or RequestBudget(Limits())
        client=CodingClient(raw,trace,budget)
        response=await client.create(messages=[{'role':'user','content':'synthetic'}],tools=[])
        return response,trace,budget

    def test_twelve_tasks_difficulties(self):
        self.assertEqual(len(self.benchmark.cases),12)
        for level in ('easy','medium','hard'):self.assertEqual(sum(c.runtime.difficulty==level for c in self.benchmark.cases),4)

    def test_module_complexity(self):
        for c in self.benchmark.cases:
            count=sum(p.startswith('app/') and p.endswith('.py') for p in c.public)
            bounds={'easy':(1,2),'medium':(2,4),'hard':(3,6)}[c.runtime.difficulty]
            self.assertTrue(bounds[0]<=count<=bounds[1])

    def test_public_and_hidden_counts(self):
        self.assertTrue(all(c.public_count==2 and c.hidden_count==4 for c in self.benchmark.cases))

    async def test_all_baselines_and_references(self):
        values=await validate_benchmark(self.benchmark)
        self.assertEqual(len(values),12)
        self.assertTrue(all(v['status']=='valid' and v['baseline_hidden']['status']=='fail' and v['reference_hidden']['passed'] and v['reference_public']['passed'] for v in values))

    def test_duplicate_case_rejected(self):
        r=self.change_manifest(lambda d:d['cases'][1].update(id=d['cases'][0]['id']))
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_illegal_fixture_path(self):
        for bad in ('/tmp/private','../private','fixtures/../private'):
            r=self.change_manifest(lambda d:d['cases'][0].update(fixture=bad))
            with self.assertRaises(ValueError):load_benchmark(r)
            shutil.rmtree(r)

    def test_unknown_manifest_fields(self):
        r=self.change_manifest(lambda d:d.update(secret='synthetic'))
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_unknown_case_fields(self):
        r=self.change_manifest(lambda d:d['cases'][0].update(expected_source='private'))
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_private_reference_cannot_change_tests(self):
        r=self.change_manifest(lambda d:d['cases'][0]['allowed_paths'].append('tests/test_public.py'))
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_custom_public_command_refused(self):
        r=self.change_manifest(lambda d:d['cases'][0].update(public_test=['python','-c','print(0)']))
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_duplicate_case_paths(self):
        r=self.change_manifest(lambda d:d['cases'][0]['allowed_paths'].append(d['cases'][0]['allowed_paths'][0]))
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_missing_assets_refused(self):
        r=self.clone_assets();(r/'hidden/config-default-001/test_hidden.py').unlink()
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_symlink_asset_refused(self):
        r=self.clone_assets();p=r/'hidden/config-default-001/test_hidden.py';p.unlink();p.symlink_to(r/'manifest.json')
        with self.assertRaises((ValueError,OSError)):load_benchmark(r)

    def test_symlink_root_refused(self):
        p=self.root/'alias';p.symlink_to(self.benchmark.root)
        with self.assertRaises(ValueError):load_benchmark(p)

    def test_zero_tests_refused(self):
        r=self.clone_assets();(r/'hidden/config-default-001/test_hidden.py').write_text('import unittest\n')
        with self.assertRaises(ValueError):load_benchmark(r)

    def test_hash_stable_and_asset_sensitive(self):
        self.assertEqual(self.benchmark.sha256,load_benchmark().sha256)
        r=self.clone_assets();p=r/'fixtures/cache-ttl-001/app/cache.py';p.write_bytes(p.read_bytes()+b'\n')
        self.assertNotEqual(self.benchmark.sha256,load_benchmark(r).sha256)

    def test_hidden_not_in_public_images(self):
        for c in self.benchmark.cases:
            self.assertFalse(any('hidden' in p or 'reference' in p for p in c.public))
            self.assertIsInstance(c.runtime,RuntimeCase)
            self.assertFalse(hasattr(c.runtime,'hidden') or hasattr(c.runtime,'reference'))
            self.assertIn('不增删文件',c.runtime.prompt);self.assertIn('非__init__.py',c.runtime.prompt)

    async def test_invalid_reference_marked_invalid(self):
        bad=replace(self.case,reference={'app/cache.py':self.case.public['app/cache.py']})
        self.assertEqual((await validate_case(bad))['status'],'invalid_benchmark_case')

    async def test_already_fixed_baseline_invalid(self):
        bad=replace(self.case,public=self.fixed)
        self.assertEqual((await validate_case(bad))['status'],'invalid_benchmark_case')

    def test_independent_git_repositories(self):
        a=create_repository(self.root/'a',self.case.public);b=create_repository(self.root/'b',self.case.public)
        self.assertNotEqual((a/'.git/index').stat().st_ino,(b/'.git/index').stat().st_ino)
        (a/'notes.txt').write_text('change');self.assertNotEqual((a/'notes.txt').read_bytes(),(b/'notes.txt').read_bytes())

    def test_no_private_files_copied(self):
        r=create_repository(self.root/'agent',self.case.public)
        self.assertEqual(set(snapshot(r)),set(self.case.public))
        self.assertFalse((r/'hidden').exists() or (r/'reference').exists())

    def test_snapshot_rejects_hardlink(self):
        r=write_images(self.root/'agent',self.case.public);os.link(r/'notes.txt',r/'alias')
        with self.assertRaises((ValueError,OSError)):snapshot(r)

    def test_snapshot_rejects_symlink(self):
        r=write_images(self.root/'agent',self.case.public);(r/'alias').symlink_to('/etc/passwd')
        with self.assertRaises((ValueError,OSError)):snapshot(r)

    def test_snapshot_rejects_big_file(self):
        r=write_images(self.root/'agent',self.case.public);(r/'huge').write_bytes(b'x'*131073)
        with self.assertRaises((ValueError,OSError)):snapshot(r)

    async def test_fresh_repeat_and_cleanup(self):
        roots=[]
        original=create_repository
        def capture(root,images):roots.append(root);return original(root,images)
        with patch('mybot.evaluation.coding_benchmark.create_repository',capture):
            report=await self.evaluation(limits=Limits(max_cases=1,repeats=2))
        self.assertEqual([r['repeat'] for r in report['results']],[1,2]);self.assertEqual(len(set(roots)),2)
        self.assertTrue(all(not p.exists() for p in roots))
        self.assertTrue(all(r['agent_state']=='completed_without_changes' for r in report['results']))

    def test_configuration_closes_mcp_skills_session_undo(self):
        cfg=configuration(GatewayConfig(context_token_budget={'input_limit':160000}, ),self.root,Limits())
        self.assertFalse(cfg.mcp_enabled or cfg.skills_enabled or cfg.storage_backend != 'memory' or cfg.debug or cfg.coding_git_workflow['undo_enabled'])
        self.assertTrue(cfg.coding_git_workflow['enabled'] and cfg.coding_autonomy['enabled'])
        self.assertEqual(cfg.coding_command['mode'],'macos_readonly')

    def test_native_registry_and_schemas_unchanged(self):
        cfg=configuration(GatewayConfig(context_token_budget={'input_limit':160000}, ),self.root,Limits())
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command=cfg.coding_command)
        self.assertIs(type(tools.get_tool('apply_patch')),ApplyPatchTool);self.assertIs(type(tools.get_tool('run_command')),RunCommandTool)
        self.assertFalse(tools.has_tool('write_file') or tools.has_tool('undo'))
        self.assertEqual(tools.get_parameters('apply_patch'),ApplyPatchTool.parameters)
        parameters=json.loads(json.dumps(tools.get_parameters('run_command')))
        timeout=parameters['properties']['timeout_seconds']
        self.assertEqual(timeout['maximum'],cfg.coding_command['timeout_seconds'])
        self.assertEqual(timeout.pop('default'),cfg.coding_command['timeout_seconds'])
        self.assertIn('omit',timeout.pop('description'))
        timeout['maximum']=RunCommandTool.parameters['properties']['timeout_seconds']['maximum']
        self.assertEqual(parameters,RunCommandTool.parameters)  # All other structure stays native.
        self.assertTrue(issubclass(BenchmarkAgent,AgentLoop));self.assertTrue(CodingTaskController)

    async def test_offline_never_constructs_sdk(self):
        with patch('mybot.evaluation.coding_live.build_client',side_effect=AssertionError('must not call')):
            report=await self.evaluation()
        self.assertFalse(report['ability_score']);self.assertIsNone(report['real_model_repair_rate'])

    async def test_live_double_gate(self):
        for live,confirm in [(True,False),(False,True),(1,True)]:
            with self.assertRaises(ValueError):await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), live=live,confirm_api_cost=confirm)

    async def test_live_synthetic_override_refused(self):
        with self.assertRaises(ValueError):await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), live=True,confirm_api_cost=True,offline_client_factory=lambda c:OfflineClient())
        with self.assertRaises(ValueError):await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), live=True,confirm_api_cost=True,command_provider=lambda r:True)

    async def test_missing_credentials_before_sdk(self):
        cfg=configuration(GatewayConfig(context_token_budget={'input_limit':160000}, api_key=None),self.root,Limits())
        with patch('mybot.evaluation.coding_live.build_client') as build,self.assertRaises(ValueError):
            await live_client(cfg,Limits(),live=True,confirm_api_cost=True,cases=1,prices=None)
        build.assert_not_called()

    async def test_live_non_tty_refused(self):
        cfg=configuration(GatewayConfig(context_token_budget={'input_limit':160000}, api_key='fixture-only'),self.root,Limits())
        with patch('sys.stdin.isatty',return_value=False),patch('mybot.evaluation.coding_live.build_client') as build,self.assertRaises(ValueError):
            await live_client(cfg,Limits(),live=True,confirm_api_cost=True,cases=1,prices=None)
        build.assert_not_called()

    async def test_live_requires_verified_sandbox(self):
        cfg=configuration(GatewayConfig(context_token_budget={'input_limit':160000}, api_key='fixture-only'),self.root,Limits())
        with patch('sys.stdin.isatty',return_value=True),patch('sys.stdout.isatty',return_value=True),patch('mybot.tools.macos_sandbox.verify_sandbox',return_value=False),patch('mybot.evaluation.coding_live.build_client') as build,self.assertRaises(ValueError):
            await live_client(cfg,Limits(),live=True,confirm_api_cost=True,cases=1,prices=None)
        build.assert_not_called()

    async def test_live_pins_retries_no_real_api(self):
        cfg=configuration(GatewayConfig(context_token_budget={'input_limit':160000}, api_key='fixture-only'),self.root,Limits())
        sdk=N(with_options=lambda **kw:kw)
        with contextlib.redirect_stdout(io.StringIO()),patch('sys.stdin.isatty',return_value=True),patch('sys.stdout.isatty',return_value=True),patch('mybot.tools.macos_sandbox.verify_sandbox',return_value=True),patch('mybot.evaluation.coding_live.build_client',return_value=sdk):
            result=await live_client(cfg,Limits(),live=True,confirm_api_cost=True,cases=1,prices=None)
        self.assertEqual(result['max_retries'],0)

    async def test_provider_exception_sanitized(self):
        async def create(**kw):raise RuntimeError('PRIVATE_KEY /Users/private secret-url')
        trace=CodingTrace();budget=RequestBudget(Limits())
        with self.assertRaises(CodingEvaluationStop) as got:await self.request(N(chat=N(completions=N(create=create))),budget,trace)
        self.assertEqual(str(got.exception),'provider_error');self.assertNotIn('PRIVATE_KEY',json.dumps(trace.events))
        self.assertEqual(budget.state['used'],1);self.assertEqual(budget.api_failures,1)

    async def test_provider_unsupported_structured(self):
        class Unsupported(Exception):status_code=400;code='function_calling_not_supported'
        async def create(**kw):raise Unsupported('private')
        with self.assertRaises(CodingEvaluationStop) as got:await self.request(N(chat=N(completions=N(create=create))))
        self.assertEqual(got.exception.category,'provider_unsupported')

    async def test_bad_response_not_fallback(self):
        raw=N(chat=N(completions=N(create=AsyncMock(return_value=N(choices=[],usage=None)))))
        with self.assertRaises(CodingEvaluationStop) as got:await self.request(raw)
        self.assertEqual(got.exception.category,'provider_unsupported')

    async def test_duplicate_call_ids_rejected_before_execution(self):
        call=N(id='same',function=N(name='read_file',arguments='{}'))
        reply=N(choices=[N(message=N(content=None,tool_calls=[call,call]))],usage=None)
        with self.assertRaises(CodingEvaluationStop):await self.request(N(chat=N(completions=N(create=AsyncMock(return_value=reply)))))

    async def test_provider_timeout(self):
        async def create(**kw):raise TimeoutError()
        with self.assertRaises(CodingEvaluationStop) as got:await self.request(N(chat=N(completions=N(create=create))))
        self.assertEqual(got.exception.category,'provider_timeout')

    async def test_request_budget_before_call(self):
        budget=RequestBudget(Limits(max_requests=1));budget.state['used']=1
        raw=N(chat=N(completions=N(create=AsyncMock())))
        with self.assertRaises(CodingEvaluationStop):await self.request(raw,budget)
        raw.chat.completions.create.assert_not_called()

    async def test_total_deadline_before_call(self):
        budget=RequestBudget(Limits());budget.deadline=0
        raw=N(chat=N(completions=N(create=AsyncMock())))
        with self.assertRaises(CodingEvaluationStop) as got:await self.request(raw,budget)
        self.assertEqual(got.exception.category,'total_timeout');raw.chat.completions.create.assert_not_called()

    def test_strict_limits(self):
        for field,value in [('max_cases',True),('max_cases',13),('repeats',0),('repeats',6),('max_requests',0),('max_output_tokens',8193),('task_timeout',float('nan')),('total_timeout',float('inf')),('seed',-1)]:
            with self.assertRaises(ValueError):Limits(**{field:value})

    def test_usage_missing_is_null(self):
        self.assertTrue(all(v is None for v in token_totals([usage_values(None)],1).values()))

    async def test_usage_aggregates_actual_server_fields(self):
        response=await OfflineClient().create()
        response.usage=N(prompt_tokens=10,completion_tokens=4,total_tokens=14,prompt_tokens_details=N(cached_tokens=2))
        raw=N(chat=N(completions=N(create=AsyncMock(return_value=response))))
        _,trace,budget=await self.request(raw)
        self.assertEqual(budget.tokens,{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14,'cached_input_tokens':2})
        self.assertEqual(trace.events[-1]['output_sha256'],__import__('hashlib').sha256(response.choices[0].message.content.encode()).hexdigest())

    def test_prices_explicit_and_cost(self):
        prices=validate_prices({'currency':'USD','input_price_per_million':1,'output_price_per_million':4,'cached_input_price_per_million':.1})
        tokens={'prompt_tokens':10,'completion_tokens':4,'cached_input_tokens':2}
        self.assertAlmostEqual(estimated_cost(tokens,prices)['amount'],24.2/1000000)
        self.assertIsNone(estimated_cost(tokens,None))
        for value in ({},{'currency':'usd','input_price_per_million':1,'output_price_per_million':4},{'currency':'USD','input_price_per_million':float('nan'),'output_price_per_million':4}):
            with self.assertRaises(ValueError):validate_prices(value)

    def test_cost_limit_without_prices_refused(self):
        with self.assertRaises(ValueError):RequestBudget(Limits(),max_cost=1)

    def test_cost_unknown_usage_stops(self):
        budget=RequestBudget(Limits(),prices={'currency':'USD','input_price_per_million':1,'output_price_per_million':4},max_cost=1)
        budget.state['used']=1
        with self.assertRaises(CodingEvaluationStop) as got:budget.check()
        self.assertEqual(got.exception.category,'unknown_estimated_cost')

    def test_estimated_cost_stops_after_response(self):
        budget=RequestBudget(Limits(),prices={'currency':'USD','input_price_per_million':1,'output_price_per_million':4},max_cost=.000001)
        budget.state['used']=1;budget.usages=[{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14,'cached_input_tokens':0}]
        with self.assertRaises(CodingEvaluationStop) as got:budget.check()
        self.assertEqual(got.exception.category,'estimated_cost_budget')

    async def test_correct_fix_independent_of_controller_verified(self):
        r=await self.score(agent_state='edited_unverified')
        self.assertEqual(r['judge_state'],'hidden_pass');self.assertTrue(r['verified_repair_success'])

    async def test_no_change_no_repair(self):
        r=await self.score(self.case.public)
        self.assertFalse(r['verified_repair_success']);self.assertFalse(r['modified_code'])

    async def test_test_tampering_cannot_win(self):
        candidate={**self.fixed,'tests/test_public.py':Image(b'',0o644)}
        r=await self.score(candidate);self.assertEqual(r['protected_file_changes'],1)
        self.assertFalse(r['verified_repair_success']);self.assertEqual(r['public']['tests'],2)

    async def test_protected_initializer_not_executed(self):
        candidate={**self.fixed,'app/__init__.py':Image(b'raise RuntimeError("tampered")',0o644)}
        r=await self.score(candidate);self.assertEqual(r['judge_state'],'hidden_pass');self.assertFalse(r['verified_repair_success'])

    async def test_hardcoded_public_input_fails(self):
        body=b'class Cache:\n def put(self,*args): pass\n def get(self,key,now): return 3 if key=="a" else None\n'
        r=await self.score({**self.case.public,'app/cache.py':Image(body,0o644)})
        self.assertEqual(r['judge_state'],'hidden_fail')

    async def test_public_only_hidden_fail(self):
        report=await self.demo_run('partial');r=report['results'][0]
        self.assertEqual(r['agent_state'],'verified');self.assertEqual(r['judge']['judge_state'],'hidden_fail')
        self.assertEqual(report['hidden_failure_after_agent_verified'],1);self.assertEqual(report['protocol_false_verified_count'],0)

    async def test_identical_preview_changes_commit_and_verify_in_original_loop(self):
        seen = []
        class Client(DemoClient):
            preview = None
            async def create(self, **kwargs):
                seen.append('reuse the same changes structure' in kwargs['messages'][0]['content'])
                result = await super().create(**kwargs)
                for call in result.choices[0].message.tool_calls or []:
                    if call.function.name=='apply_patch':
                        args = json.loads(call.function.arguments)
                        if args['dry_run']: self.preview = args
                        else: seen.append(args=={**self.preview,'dry_run':False})
                return result
        with patch('mybot.evaluation.coding_live.build_client', side_effect=AssertionError('offline only')) as sdk:
            report = await self.evaluation(offline_client_factory=lambda public:Client())
        sdk.assert_not_called(); self.assertTrue(seen and all(seen))
        r = report['results'][0]
        self.assertEqual(r['agent_state'], 'verified')
        self.assertTrue(r['agent_workflow_success'])
        self.assertTrue(r['judge']['verified_repair_success'])
        self.assertEqual(r['metrics']['patch_preview_calls'], 1)
        self.assertEqual(r['metrics']['committed_patches'], 1)
        self.assertEqual(r['metrics']['real_test_runs'], 1)
        self.assertEqual(r['controller']['current_revision'], r['controller']['last_verified_revision'])
        self.assertFalse(r['judge']['index_changed'])
        self.assertEqual(r['judge']['journal_attribution_mismatch'], 0)
        self.assertEqual(r['metrics']['protocol_false_verified_count'], 0)
        self.assertTrue(r['metrics']['tool_call_ids_paired'])

    async def test_extra_write_field_after_good_preview_stops_without_sensitive_trace(self):
        class Client(DemoClient):
            async def create(self, **kwargs):
                result = await super().create(**kwargs)
                for call in result.choices[0].message.tool_calls or []:
                    if call.function.name=='apply_patch':
                        args = json.loads(call.function.arguments)
                        if args['dry_run'] is False:
                            args['PRIVATE_PATCH_ARGUMENT'] = 'PRIVATE_SOURCE_CREDENTIAL_SENTINEL'
                            call.function.arguments = json.dumps(args)
                return result
        with patch('mybot.evaluation.coding_live.build_client', side_effect=AssertionError('offline only')) as sdk:
            report = await self.evaluation(offline_client_factory=lambda public:Client())
        sdk.assert_not_called()
        r = report['results'][0]
        self.assertEqual(r['agent_state'], 'blocked')
        self.assertFalse(r['agent_workflow_success'])
        self.assertEqual(r['controller']['stop_reason'], 'patch_failed_without_safe_recovery')
        self.assertEqual(r['metrics']['patch_preview_calls'], 1)
        self.assertEqual(r['metrics']['patch_write_attempts'], 1)
        self.assertEqual(r['metrics']['committed_patches'], 0)
        self.assertEqual(r['metrics']['real_test_runs'], 0)
        self.assertEqual(r['controller']['current_revision'], 0)
        event = next(e for e in r['trace'] if e['event']=='tool' and not e['success'])
        self.assertEqual(event['error'], 'invalid_arguments')
        self.assertEqual(event['patch_failure_phase'], 'validation')
        self.assertEqual(event['patch_failure_state'], 'preflight_failed')
        self.assertFalse(event['patch_safe_to_retry'])
        self.assertFalse(r['judge']['modified_code'] or r['judge']['index_changed'])
        self.assertEqual(r['judge']['journal_attribution_mismatch'], 0)
        self.assertTrue(r['metrics']['tool_call_ids_paired'])
        self.assertNotIn('PRIVATE_', json.dumps(report))

    async def test_cwd_omitted_guidance_reaches_original_loop_and_real_tests(self):
        check = self
        class Client(DemoClient):
            async def create(self, **kwargs):
                check.assertIn('prefer omitting cwd', kwargs['messages'][0]['content'])
                spec = next(t['function']['parameters'] for t in kwargs['tools']
                            if t['function']['name']=='run_command')
                check.assertEqual(spec['properties']['cwd']['default'], '.')
                check.assertIn('workspace-relative', spec['properties']['cwd']['description'])
                result = await super().create(**kwargs)
                for call in result.choices[0].message.tool_calls or []:
                    if call.function.name=='run_command':
                        check.assertNotIn('cwd', json.loads(call.function.arguments))
                return result
        approval = AsyncMock(return_value=ApprovalDecision.APPROVE)
        with patch('mybot.evaluation.coding_live.build_client', side_effect=AssertionError('offline only')) as sdk:
            report = await self.evaluation(offline_client_factory=lambda public:Client(), command_provider=approval)
        sdk.assert_not_called(); approval.assert_awaited_once()
        self.assertEqual(approval.call_args.args[0].cwd, '.')
        self.assertTrue(approval.call_args.args[0].os_sandbox)
        r = report['results'][0]
        self.assertEqual(r['agent_state'], 'verified')
        self.assertTrue(r['agent_workflow_success'])
        self.assertTrue(r['judge']['verified_repair_success'])
        self.assertEqual(r['metrics']['real_test_runs'], 1)
        self.assertEqual(r['controller']['current_revision'], r['controller']['last_verified_revision'])
        self.assertTrue(r['metrics']['tool_call_ids_paired'])
        self.assertEqual(r['metrics']['protocol_false_verified_count'], 0)
        self.assertEqual(r['judge']['journal_attribution_mismatch'], 0)
        self.assertFalse(r['judge']['index_changed'])

    async def test_invalid_cwd_judge_pass_is_not_workflow_success_or_parameter_leak(self):
        illegal = str(self.root/'PRIVATE_CWD_SENTINEL')
        class Client(DemoClient):
            async def create(self, **kwargs):
                result = await super().create(**kwargs)
                for call in result.choices[0].message.tool_calls or []:
                    if call.function.name=='run_command':
                        args = json.loads(call.function.arguments); args['cwd'] = illegal
                        call.function.arguments = json.dumps(args)
                return result
        approval = AsyncMock(return_value=ApprovalDecision.APPROVE)
        with patch('mybot.evaluation.coding_live.build_client', side_effect=AssertionError('offline only')) as sdk, \
                patch('mybot.tools.run_command.run_process') as process:
            report = await self.evaluation(offline_client_factory=lambda public:Client(), command_provider=approval)
        sdk.assert_not_called(); approval.assert_not_awaited(); process.assert_not_called()
        r = report['results'][0]
        self.assertEqual(r['agent_state'], 'blocked')
        self.assertFalse(r['agent_workflow_success'])
        self.assertEqual(r['controller']['stop_reason'], 'invalid_cwd')
        self.assertEqual(r['metrics']['real_test_runs'], 0)
        self.assertIsNone(r['controller']['last_verified_revision'])
        self.assertEqual(r['judge']['judge_state'], 'hidden_pass')
        self.assertTrue(r['judge']['verified_repair_success'])
        self.assertEqual(r['metrics']['approval_denials'], 0)
        self.assertTrue(r['metrics']['tool_call_ids_paired'])
        self.assertEqual(r['metrics']['protocol_false_verified_count'], 0)
        self.assertNotIn('PRIVATE_CWD_SENTINEL', json.dumps(report))
        self.assertNotIn(illegal, json.dumps(report))
        self.assertIsNone(report['actual_tokens'])
        self.assertIsNone(report['estimated_cost'])

    async def test_completed_plan_cannot_mask_independent_hidden_failure(self):
        class PlannedClient(DemoClient):
            async def create(self, **kwargs):
                if self.step == 5:
                    return N(choices=[N(message=N(content='Reviewed public test results.', tool_calls=None),
                                        finish_reason='stop')], usage=None)
                result = await super().create(**kwargs)
                message = result.choices[0].message
                def plan_call(name, args, identifier):
                    return N(id=identifier, function=N(name=name, arguments=json.dumps(args)))
                if self.step == 1:
                    message.tool_calls[:0] = [
                        plan_call('create_plan', {'steps':['PRIVATE_PLAN_SENTINEL repair','execute tests']}, 'plan-create'),
                        plan_call('update_plan', {'step':1,'status':'in_progress'}, 'plan-start')]
                elif self.step == 4:
                    message.tool_calls[:0] = [
                        plan_call('update_plan', {'step':1,'status':'completed'}, 'plan-repaired'),
                        plan_call('update_plan', {'step':2,'status':'in_progress'}, 'plan-test')]
                elif self.step == 5:
                    message.tool_calls = [plan_call('update_plan', {'step':2,'status':'completed'}, 'plan-finish')]
                    message.content = None
                    result.choices[0].finish_reason = 'tool_calls'
                return result
        report = await self.evaluation(offline_client_factory=lambda public:PlannedClient('partial'))
        r = report['results'][0]
        self.assertEqual(r['agent_state'], 'verified')
        self.assertTrue(r['agent_workflow_success'])
        self.assertEqual(r['judge']['judge_state'], 'hidden_fail')
        self.assertFalse(r['judge']['verified_repair_success'])
        self.assertEqual(r['metrics']['real_test_runs'], 1)
        self.assertEqual(r['metrics']['committed_patches'], 1)
        self.assertTrue(r['metrics']['tool_call_ids_paired'])
        self.assertEqual(r['judge']['journal_attribution_mismatch'], 0)
        self.assertFalse(r['judge']['index_changed'])
        self.assertEqual(sum(e['event']=='tool' and e['name']=='update_plan' and e['success'] for e in r['trace']), 4)
        self.assertNotIn('PRIVATE_PLAN_SENTINEL', json.dumps(report))
        self.assertIsNone(report['actual_tokens'])
        self.assertIsNone(report['estimated_cost'])

    async def test_real_patch_and_journal(self):
        report=await self.demo_run();r=report['results'][0]
        self.assertTrue(r['judge']['verified_repair_success']);self.assertEqual(r['judge']['journal_attribution_mismatch'],0)
        self.assertEqual(r['metrics']['committed_patches'],1);self.assertTrue(r['metrics']['tool_call_ids_paired'])

    async def test_fake_success_text_does_not_score(self):
        r=(await self.demo_run('fake'))['results'][0]
        self.assertEqual(r['agent_state'],'completed_without_changes');self.assertFalse(r['judge']['verified_repair_success'])
        from mybot.evaluation.coding_metrics import failure_reason
        observed={**r,'metrics':{**r['metrics'],'tool_calls':1,'read_calls':1}}
        self.assertEqual(failure_reason(observed),'no_code_change')

    async def test_incomplete_multifile_fix(self):
        c=next(c for c in self.benchmark.cases if c.runtime.id=='error-retry-001')
        validation=next(r for r in await validate_benchmark(self.benchmark) if r['case_id']==c.runtime.id)
        candidate={**c.public,'app/policy.py':c.reference['app/policy.py']}
        r=await judge(c,candidate,validation,benchmark=self.benchmark,seal=trusted_seal(),index_unchanged=True,journal_paths={'app/policy.py'},agent_state='edited_unverified')
        self.assertEqual(r['judge_state'],'hidden_fail')

    async def test_extra_file_detected(self):
        r=await self.score({**self.fixed,'rogue.txt':Image(b'unexpected',0o644)})
        self.assertEqual(r['unrelated_file_changes'],1);self.assertFalse(r['verified_repair_success'])

    async def test_unlisted_file_names_not_raw_metadata(self):
        secret_name='PRIVATE_MODEL_CHOSEN_FILENAME.txt'
        r=await self.score({**self.fixed,secret_name:Image(b'unexpected',0o644)})
        self.assertNotIn(secret_name,json.dumps(r))
        self.assertEqual(r['unrelated_file_changes'],1)
        self.assertTrue(any(p.startswith('<unlisted-file:') for p in r['changed_files']))

    async def test_index_changed_detected(self):
        r=await self.score(index_unchanged=False)
        self.assertTrue(r['index_changed']);self.assertFalse(r['verified_repair_success'])

    async def test_attribution_mismatch_detected(self):
        r=await self.score(journal_paths=set())
        self.assertEqual(r['journal_attribution_mismatch'],1);self.assertFalse(r['verified_repair_success'])

    async def test_uncertain_execution_never_wins(self):
        self.assertFalse((await self.score(agent_state='execution_uncertain'))['verified_repair_success'])

    async def test_private_asset_change_detected(self):
        root=self.clone_assets();benchmark=load_benchmark(root)
        (root/'hidden/cache-ttl-001/test_hidden.py').write_text('changed')
        r=await self.score(benchmark=benchmark)
        self.assertEqual(r['judge_state'],'grader_error');self.assertEqual(r['failure'],'trusted_assets_changed')

    async def test_grader_code_seal_change_detected(self):
        r=await self.score(seal=('different',))
        self.assertEqual(r['judge_state'],'grader_error')

    async def test_grader_timeout_not_hidden_fail(self):
        candidate={**self.case.public,'app/cache.py':Image(b'import time;time.sleep(4)\n',0o644)}
        r=await run_suite(judge_images(self.case,candidate),4,hidden=True,timeout=.05)
        self.assertEqual(r['status'],'grader_error');self.assertEqual(r['category'],'timed_out')

    async def test_grader_exception_sanitized(self):
        with patch('mybot.evaluation.coding_judge.run_process',side_effect=RuntimeError('private grader source')):
            r=await run_suite(judge_images(self.case,self.fixed),4,hidden=True)
        self.assertEqual(r['status'],'grader_error');self.assertNotIn('private',json.dumps(r))

    async def test_candidate_syntax_error_is_test_failure(self):
        candidate={**self.case.public,'app/cache.py':Image(b'def broken(\n',0o644)}
        r=await self.score(candidate)
        self.assertEqual(r['judge_state'],'hidden_fail');self.assertEqual(r['hidden']['category'],'candidate_import_error')

    async def test_zero_tests_not_success(self):
        images=judge_images(self.case,self.fixed);images['hidden/test_hidden.py']=Image(b'import unittest\n',0o644)
        r=await run_suite(images,4,hidden=True)
        self.assertEqual(r['status'],'grader_error')

    async def test_forged_test_output_not_success(self):
        im=self.case.public['app/cache.py']
        candidate={**self.case.public,'app/cache.py':Image(b'print("Ran 999 tests in 0.0s\\nOK")\n'+im.data,im.mode)}
        r=await self.score(candidate)
        self.assertEqual(r['judge_state'],'hidden_fail')

    async def test_exit_zero_without_receipt_not_success(self):
        candidate={**self.case.public,'app/cache.py':Image(b'import os;os._exit(0)\n',0o644)}
        r=await self.score(candidate)
        self.assertEqual(r['judge_state'],'grader_error')

    async def test_output_limit_not_success(self):
        candidate={**self.case.public,'app/cache.py':Image(b'import os;os.write(1,b"x"*65536)\n',0o644)}
        r=await run_suite(judge_images(self.case,candidate),4,hidden=True,output_limit=512)
        self.assertEqual(r['status'],'grader_error');self.assertEqual(r['category'],'output_limit_exceeded')

    async def test_sandbox_failure_never_host_fallback(self):
        with patch('mybot.tools.macos_sandbox.verify_sandbox',return_value=False),patch('mybot.evaluation.coding_judge.run_process') as run:
            r=await run_suite(judge_images(self.case,self.fixed),4,hidden=True)
        self.assertEqual(r['category'],'sandbox_unavailable');run.assert_not_called()

    async def test_native_approval_denial_effective(self):
        async def deny(request):return ApprovalDecision.DENY
        report=await self.demo_run(command_provider=deny);r=report['results'][0]
        self.assertEqual(r['failure'],'approval_denied');self.assertEqual(r['metrics']['real_test_runs'],0)

    async def test_global_budget_across_tasks(self):
        report=await evaluate(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), limits=Limits(max_cases=2,max_requests=1))
        self.assertEqual(report['llm_requests'],1);self.assertEqual(report['attempted_cases'],1)
        self.assertEqual(report['unscored_cases'],1);self.assertEqual(report['total_cases'],2)

    async def test_per_case_controller_budget(self):
        report=await self.demo_run(limits=Limits(max_cases=1,max_model_requests_per_case=1))
        self.assertEqual(report['llm_requests'],1);self.assertEqual(report['results'][0]['failure'],'model_request_budget')

    async def test_protocol_false_verified_audit(self):
        trace=CodingTrace()
        self.assertEqual(case_metrics(trace,{'state':'verified'},[],False)['protocol_false_verified_count'],1)

    async def test_hidden_not_returned_to_client_session_or_tools(self):
        requests=[]
        class Inspect(DemoClient):
            async def create(inner,**kw):requests.append(kw);return await super(Inspect,inner).create(**kw)
        seen=[]
        def factory(public):seen.append(public);return Inspect()
        report=await self.evaluation(offline_client_factory=factory)
        serialized=json.dumps(requests)
        for marker in ('class Hidden','negative ttl test hidden','hidden_suite','reference_public','expected_source'):
            self.assertNotIn(marker,serialized)
        self.assertTrue(all(isinstance(p,RuntimeCase) for p in seen));self.assertNotIn('original_bytes',json.dumps(report))

    async def test_metadata_report_no_source_or_private_paths(self):
        report=await self.demo_run();text=json.dumps(report)
        self.assertNotIn('class Cache:',text);self.assertNotIn('class Hidden',text)
        self.assertNotIn(str(Path.home()),text);self.assertNotIn('expected_sha256',text)
        self.assertIsNone(report['actual_tokens']);self.assertIsNone(report['estimated_cost']);self.assertFalse(report['ability_score'])
        self.assertIn(report['worktree_dirty'],(None,True,False));self.assertIn('prices',report);self.assertIn('max_estimated_cost',report)

    async def test_no_rate_for_offline(self):
        r=await self.demo_run()
        for key in ('verified_repair_rate','real_model_repair_rate','public_test_pass_rate','hidden_test_pass_rate','multi_file_repair_rate'):
            self.assertIsNone(r[key])

    def test_report_exclusive_and_old_reader_compatibility(self):
        report={'mode':'offline','version':1,'ability_score':False}
        a=save_report(report,self.root/'reports');b=save_report(report,self.root/'reports')
        self.assertNotEqual(a,b);self.assertEqual(json.loads(a.read_text()),report)
        from mybot.evaluation.history import analyze_report
        old={'version':2,'results':[],'overall':{}}
        p=self.root/'old-report.json';p.write_text(json.dumps(old));before=p.read_bytes()
        self.assertEqual(analyze_report(p),old);self.assertEqual(p.read_bytes(),before)

    async def test_demo_four_paths(self):
        r=await demonstrate();pairs=[(v['judge_state'],v['repair_success']) for v in r['cases']]
        self.assertEqual(pairs,[('hidden_pass',True),('hidden_fail',False),('hidden_fail',False),('grader_error',False)])
        self.assertTrue(all(v['real_model_repair_rate'] is None for v in r['cases']))

    async def test_agent_command_cannot_read_actual_private_gold(self):
        agent=create_repository(self.root/'agent',self.case.public)
        async def approve(request):return ApprovalDecision.APPROVE
        tool=RunCommandTool(agent,command={'mode':'macos_readonly'},patch_mode='write',approval_provider=approve)
        path=self.benchmark.root/'hidden/cache-ttl-001/test_hidden.py'
        command=['python','-c','from pathlib import Path;print(Path('+repr(str(path))+').read_text())']
        r=await tool.execute(argv=command)
        self.assertFalse(r.success);self.assertTrue(r.metadata['sandbox_applied']);self.assertEqual(r.metadata['exit_code'],1)
        self.assertNotIn('class Hidden',r.output)
        read=build_default_tool_registry(agent,coding_enabled=True,patch_mode='write').get_tool('read_file')
        self.assertFalse((await read.execute(path=str(path))).success)

    async def test_agent_command_cannot_write_outside(self):
        agent=create_repository(self.root/'agent',self.case.public);outside=self.root/'outside';outside.write_text('sentinel')
        async def approve(request):return ApprovalDecision.APPROVE
        tool=RunCommandTool(agent,command={'mode':'macos_readonly'},patch_mode='write',approval_provider=approve)
        r=await tool.execute(argv=['python','-c','from pathlib import Path;Path('+repr(str(outside))+').write_text("BAD")'])
        self.assertFalse(r.success);self.assertEqual(outside.read_text(),'sentinel')

    async def test_judge_cannot_write_hidden_copy(self):
        source=self.fixed['app/cache.py']
        prefix=b'from pathlib import Path\ntry: (Path(__file__).parent.parent/"hidden/test_hidden.py").write_text("BAD")\nexcept PermissionError: pass\n'
        candidate={**self.fixed,'app/cache.py':Image(prefix+source.data,source.mode)}
        r=await self.score(candidate);self.assertTrue(r['verified_repair_success']);self.assertTrue(self.benchmark.unchanged())

    async def test_task_timeout_and_cleanup(self):
        class Slow(OfflineClient):
            async def create(self,**kw):await asyncio.sleep(2)
        roots=[];original=create_repository
        def capture(root,images):roots.append(root);return original(root,images)
        with patch('mybot.evaluation.coding_benchmark.create_repository',capture):
            r=await self.evaluation(limits=Limits(max_cases=1,task_timeout=.02),offline_client_factory=lambda public:Slow())
        self.assertEqual(r['results'][0]['failure'],'task_timeout');self.assertTrue(all(not p.exists() for p in roots))
        self.assertEqual(r['api_failures'],r['llm_requests']);self.assertEqual(r['cancelled_requests'],r['llm_requests'])

    async def test_repeated_action_budget_preserved(self):
        class Repeated(OfflineClient):
            def __init__(self):super().__init__();self.n=0
            async def create(self,**kw):
                self.n+=1
                call=N(id='repeat-'+str(self.n),function=N(name='read_file_range',arguments=json.dumps({'path':'app/cache.py','start_line':1,'end_line':80})))
                return N(choices=[N(message=N(content=None,tool_calls=[call]))],usage=None)
        r=await self.evaluation(offline_client_factory=lambda public:Repeated())
        self.assertEqual(r['results'][0]['failure'],'repeated_action_loop');self.assertGreater(r['repeated_actions'],0)

    async def test_original_loop_controller_and_isolated_sessions(self):
        original=AgentLoop._finish_turn;seen=[]
        def capture(agent,*args,**kwargs):
            seen.append((type(agent.coding_controller),agent.session,agent.tools,agent._git_capsule))
            return original(agent,*args,**kwargs)
        with patch.object(AgentLoop,'_finish_turn',capture):
            r=await self.evaluation(limits=Limits(max_cases=1,repeats=2))
        self.assertTrue(all(t[0] is CodingTaskController and t[3] is None for t in seen))
        self.assertIsNot(seen[0][1],seen[1][1]);self.assertIsNot(seen[0][2],seen[1][2])
        self.assertIs(BenchmarkAgent._handle_message,AgentLoop._handle_message)

    async def test_no_hidden_grading_after_total_deadline(self):
        with patch('mybot.evaluation.coding_benchmark.judge',AsyncMock()) as grader:
            r=await self.evaluation(limits=Limits(max_cases=1,total_timeout=.01))
        grader.assert_not_called();self.assertEqual(r['llm_requests'],0)

    async def test_case_selection_rejects_unknown_and_duplicates(self):
        for ids in (['no-such-case'],['cache-ttl-001','cache-ttl-001']):
            with self.assertRaises(ValueError):await self.evaluation(case_ids=ids)

    async def test_missing_usage_mixed_responses_stays_null(self):
        known={'prompt_tokens':10,'completion_tokens':4,'total_tokens':14,'cached_input_tokens':0}
        self.assertIsNone(token_totals([known,usage_values(None)],2)['total_tokens'])
        self.assertIsNone(token_totals([known],2)['prompt_tokens'])

    async def test_no_raw_live_response_in_metadata(self):
        response=await OfflineClient().create();response.choices[0].message.content='PRIVATE_OUTPUT_BODY'
        raw=N(chat=N(completions=N(create=AsyncMock(return_value=response))))
        _,trace,budget=await self.request(raw)
        self.assertNotIn('PRIVATE_OUTPUT_BODY',json.dumps(trace.events));self.assertIn('output_sha256',trace.events[-1])

    async def test_synthetic_live_sdk_cleanup_without_network(self):
        client=OfflineClient();client.close=AsyncMock()
        cfg=GatewayConfig(context_token_budget={'input_limit':160000}, api_key='fixture-only',provider='fixture',model='mock')
        with patch('mybot.evaluation.coding_benchmark.live_client',AsyncMock(return_value=client)):
            r=await self.evaluation(live=True,confirm_api_cost=True,base_config=cfg)
        client.close.assert_awaited_once();self.assertEqual(r['llm_requests'],1)
        self.assertIsNone(r['actual_tokens']);self.assertIsNone(r['estimated_cost'])

    async def test_inferrable_failure_not_api_error_text(self):
        class Broken(OfflineClient):
            async def create(self,**kw):raise RuntimeError('PRIVATE /Users/secret api-body')
        r=await self.evaluation(offline_client_factory=lambda public:Broken())
        self.assertEqual(r['results'][0]['failure'],'provider_error');self.assertNotIn('api-body',json.dumps(r))

    async def test_request_timeout_is_aggregate_bounded(self):
        class Slow(OfflineClient):
            async def create(self,**kw):await asyncio.sleep(2)
        r=await self.evaluation(limits=Limits(max_cases=1,request_timeout=.01),offline_client_factory=lambda public:Slow())
        self.assertEqual(r['results'][0]['controller']['stop_reason'],'model_request_timeout')
        self.assertEqual(r['llm_requests'],1);self.assertEqual(r['api_failures'],1);self.assertEqual(r['cancelled_requests'],1)

    async def test_zero_effect_patch_cannot_gain_repair(self):
        body=self.case.public['app/cache.py'].data
        r=await self.score({**self.case.public,'app/cache.py':Image(body,0o644)})
        self.assertFalse(r['verified_repair_success'])

    async def test_public_tests_regraded_from_final_code(self):
        candidate={**self.fixed,'app/cache.py':Image(self.fixed['app/cache.py'].data.replace(b'now >= expires',b'now > expires'),0o644)}
        r=await self.score(candidate)
        self.assertTrue(r['public']['passed']);self.assertFalse(r['hidden']['passed']);self.assertFalse(r['verified_repair_success'])

    def test_ability_denominators_include_attempt_failures(self):
        from mybot.evaluation.coding_metrics import summarize
        budget=RequestBudget(Limits());budget.successes=1
        common={'attempted':True,'difficulty':'easy','agent_state':'verified','metrics':{},'controller':{},'failure':None}
        passed={**common,'judge':{'judge_state':'hidden_pass','verified_repair_success':True,'public':{'passed':True}}}
        error={**common,'judge':{'judge_state':'grader_error','verified_repair_success':False}}
        r=summarize([passed,error],live=True,budget=budget)
        self.assertEqual(r['attempted_cases'],2);self.assertEqual(r['eligible_cases'],1)
        self.assertEqual(r['verified_repair_rate'],.5);self.assertEqual(r['eligible_repair_rate'],1)


    async def test_unittest_tampering_rejected(self):
        original=self.fixed['app/cache.py']
        body=b'import unittest\nunittest.TestCase.assertEqual=lambda *a,**k:None\n'+original.data
        r=await self.score({**self.fixed,'app/cache.py':Image(body,original.mode)})
        self.assertEqual(r['judge_state'],'grader_error');self.assertFalse(r['verified_repair_success'])

    def test_manifest_boolean_version_invalid(self):
        root=self.change_manifest(lambda d:d.update(version=True))
        with self.assertRaises(ValueError):load_benchmark(root)

    def test_snapshot_deep_directories_bounded(self):
        root=write_images(self.root/'agent',self.case.public);path=root
        for _ in range(18):path=path/'deep';path.mkdir()
        with self.assertRaises(ValueError):snapshot(root)

    def test_seed_orders_tasks_deterministically(self):
        from mybot.evaluation.coding_benchmark import selected_cases
        first=[c.runtime.id for c in selected_cases(self.benchmark,None,12,24)]
        self.assertEqual(first,[c.runtime.id for c in selected_cases(self.benchmark,None,12,24)])
        self.assertNotEqual(first,[c.runtime.id for c in selected_cases(self.benchmark,None,12,25)])
        self.assertEqual([c.runtime.id for c in selected_cases(self.benchmark,['cache-ttl-001'],1,25)],['cache-ttl-001'])

    def test_sensitive_provider_labels_hidden(self):
        from mybot.evaluation.coding_live import labels
        cfg=GatewayConfig(context_token_budget={'input_limit':160000}, model='fixture-private-key',api_key='fixture-private-key',provider='/Users/private/provider')
        self.assertEqual(labels(cfg),{'model':'<unavailable>','provider':'<unavailable>'})

    async def test_legacy_function_call_not_silent_completion(self):
        reply=N(choices=[N(message=N(content=None,tool_calls=None,function_call=N(name='read_file',arguments='{}')))],usage=None)
        raw=N(chat=N(completions=N(create=AsyncMock(return_value=reply))))
        with self.assertRaises(CodingEvaluationStop) as got:await self.request(raw)
        self.assertEqual(got.exception.category,'provider_unsupported')

    async def test_empty_call_ids_rejected(self):
        call=N(id='',function=N(name='read_file',arguments='{}'))
        reply=N(choices=[N(message=N(content=None,tool_calls=[call]))],usage=None)
        raw=N(chat=N(completions=N(create=AsyncMock(return_value=reply))))
        with self.assertRaises(CodingEvaluationStop):await self.request(raw)

    async def test_hidden_results_do_not_trigger_new_requests(self):
        class Count(DemoClient):
            calls=0
            async def create(self,**kw):type(self).calls+=1;return await super().create(**kw)
        r=await self.evaluation(offline_client_factory=lambda public:Count('partial'))
        self.assertEqual(Count.calls,r['llm_requests']);self.assertEqual(Count.calls,5)
        self.assertEqual(r['results'][0]['judge']['judge_state'],'hidden_fail')

    async def test_report_save_cannot_overwrite_same_generated_name(self):
        report={'mode':'offline','report_type':'coding_benchmark','version':1}
        import uuid
        from datetime import datetime,timezone
        fake=N(hex='aaaaaaaa1234567890')
        with patch('uuid.uuid4',return_value=fake):
            first=save_report(report,self.root/'reports')
            with patch('mybot.evaluation.runner.datetime') as clock:
                clock.now.return_value=datetime.strptime(first.name.split('-')[1],'%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
                with self.assertRaises(FileExistsError):save_report(report,self.root/'reports')
        self.assertEqual(json.loads(first.read_text()),report)

    async def test_failed_request_keeps_token_totals_unknown(self):
        budget=RequestBudget(Limits());trace=CodingTrace()
        async def fail(**kw):raise RuntimeError('private')
        with self.assertRaises(CodingEvaluationStop):await self.request(N(chat=N(completions=N(create=fail))),budget,trace)
        self.assertTrue(all(v is None for v in budget.tokens.values()))


    async def test_test_then_modify_expires_verification(self):
        from mybot.evaluation.coding_agent import decode_result
        class Repatch(DemoClient):
            def __init__(self):super().__init__('correct');self.phase='initial'
            async def create(inner,**kw):
                prior=next((m for m in reversed(kw['messages']) if m['role']=='tool'),None)
                body,meta=decode_result(prior['content']) if prior else ('',{})
                if inner.phase=='initial' and meta.get('completed') and meta.get('exit_code')==0:
                    inner.phase='read';name='read_file_range';args={'path':'app/cache.py','start_line':1,'end_line':80}
                elif inner.phase=='read':
                    inner.phase='done';name='apply_patch';args={'dry_run':False,'changes':[{'op':'update','path':'app/cache.py','expected_sha256':meta['file_sha256'],'edits':[{'old_text':'now >= expires','new_text':'now > expires'}]}]}
                elif inner.phase=='done':
                    return N(choices=[N(message=N(content='All tests passed.',tool_calls=None))],usage=None)
                else:return await super(Repatch,inner).create(**kw)
                call=N(id='repatch-'+inner.phase,function=N(name=name,arguments=json.dumps(args)))
                return N(choices=[N(message=N(content=None,tool_calls=[call]))],usage=None)
        r=await self.evaluation(offline_client_factory=lambda public:Repatch())
        self.assertEqual(r['results'][0]['agent_state'],'edited_unverified')
        self.assertEqual(r['verification_expired_count'],1);self.assertEqual(r['protocol_false_verified_count'],0)
        self.assertFalse(r['results'][0]['judge']['verified_repair_success'])

    async def test_final_source_change_during_grading_not_success(self):
        from mybot.evaluation.coding_judge import judge as original_judge
        roots=[];original_create=create_repository
        def capture(root,images):roots.append(root);return original_create(root,images)
        async def mutate(*args,**kwargs):
            r=await original_judge(*args,**kwargs)
            p=roots[-1]/'app/cache.py';p.write_bytes(p.read_bytes()+b'\n# external change\n')
            return r
        with patch('mybot.evaluation.coding_benchmark.create_repository',capture),patch('mybot.evaluation.coding_benchmark.judge',mutate):
            r=await self.demo_run()
        self.assertFalse(r['results'][0]['judge']['verified_repair_success'])
        self.assertTrue(r['results'][0]['judge']['stale_final_version'])

    async def terminal_task(self, answer, *, command_timeout=None):
        # Real PTY only in offline regression: synthetic model, no SDK/network.
        # Production Live still requires the human's own per-command response.
        class NoisyDemo(DemoClient):
            async def create(inner, **kwargs):
                self.assertFalse(sys.stdout.isatty())  # Agent output is still captured.
                print('PRIVATE_RAW_AGENT_OUTPUT')
                definition=next(d for d in kwargs['tools'] if d['function']['name']=='run_command')
                timeout=definition['function']['parameters']['properties']['timeout_seconds']
                self.assertEqual(timeout['maximum'],30);self.assertEqual(timeout['default'],30)
                self.assertIn('"command_timeout_seconds": 30',kwargs['messages'][0]['content'])
                response=await super().create(**kwargs)
                calls=response.choices[0].message.tool_calls
                if calls and calls[0].function.name=='run_command':
                    args=json.loads(calls[0].function.arguments)
                    self.assertNotIn('timeout_seconds',args)
                    if command_timeout is not None:
                        args['timeout_seconds']=command_timeout
                        calls[0].function.arguments=json.dumps(args)
                return response
        master, slave = pty.openpty()
        try:
            with os.fdopen(os.dup(slave), 'r') as stdin, os.fdopen(os.dup(slave), 'w') as stdout:
                self.assertTrue(stdin.isatty() and stdout.isatty())
                os.write(master, (answer+'\n').encode())
                limits=Limits(max_cases=1,max_requests=12)
                with patch('sys.stdin',stdin), contextlib.redirect_stdout(stdout), \
                        patch('mybot.evaluation.coding_live.build_client') as build:
                    result=await run_task(self.case,self.validation,self.benchmark,trusted_seal(),self.root,
                        repeat=1,limits=limits,budget=RequestBudget(limits),
                        base=GatewayConfig(context_token_budget={'input_limit':160000}, api_key='SYNTHETIC_CREDENTIAL'),raw=NoisyDemo(),live=True)
                build.assert_not_called()
            chunks=[]
            while select.select([master],[],[],0)[0]:chunks.append(os.read(master,65536))
            terminal=b''.join(chunks).decode()
        finally:
            os.close(master);os.close(slave)
        self.assertIn('[NATIVE COMMAND APPROVAL]',terminal)
        self.assertIn('仅批准此命令一次',terminal)
        self.assertIn('macOS Seatbelt',terminal)
        self.assertIn('"timeout_seconds": 30',terminal)
        for private in ('PRIVATE_RAW_AGENT_OUTPUT','SYNTHETIC_CREDENTIAL','negative ttl'):
            self.assertNotIn(private,terminal)
            self.assertNotIn(private,json.dumps(result))
        self.assertFalse(result['judge']['index_changed'])
        self.assertEqual(result['judge']['journal_attribution_mismatch'],0)
        return result

    async def test_live_approval_reaches_real_terminal_under_capture(self):
        result=await self.terminal_task('yes')
        self.assertEqual(result['agent_state'],'verified')
        self.assertTrue(result['judge']['verified_repair_success'])
        self.assertEqual(result['metrics']['real_test_runs'],1)
        self.assertEqual(result['metrics']['committed_patches'],1)
        self.assertEqual(result['metrics']['patch_preview_calls'],1)
        self.assertEqual(result['metrics']['protocol_false_verified_count'],0)

    async def test_live_terminal_rejection_still_stops_command(self):
        result=await self.terminal_task('no')
        self.assertEqual(result['agent_state'],'blocked')
        self.assertEqual(result['metrics']['approval_denials'],1)
        self.assertEqual(result['metrics']['real_test_runs'],0)

    async def test_dedicated_approval_requires_exact_yes_for_each_call(self):
        class Terminal(io.StringIO):
            def isatty(self):return True
        terminal=Terminal();captured=io.StringIO()
        request=inspectable_command('macos_readonly','.',('python','-m','unittest'),10)
        answers=iter(['yes','no','YES','yes all'])
        def respond():
            self.assertTrue(terminal.isatty())
            self.assertFalse(sys.stdout.isatty())
            self.assertTrue(terminal.getvalue().endswith('其他输入拒绝: '))
            return next(answers)
        with patch('sys.stdin.isatty',return_value=True), contextlib.redirect_stdout(captured), \
                patch('builtins.input',side_effect=respond) as prompt:
            decisions=[await cli_command_approval(request,output=terminal) for _ in range(4)]
        self.assertEqual(decisions,[ApprovalDecision.APPROVE]+[ApprovalDecision.DENY]*3)
        self.assertEqual(prompt.call_count,4)
        self.assertEqual(terminal.getvalue().count(request.display_json),4)
        self.assertEqual(captured.getvalue(),'')

    async def test_dedicated_approval_does_not_bypass_noninteractive_channels(self):
        request=inspectable_command('macos_readonly','.',('python','-m','unittest'),10)
        for stdin,stdout in ((False,True),(True,False),(False,False)):
            output=io.StringIO();output.isatty=lambda:stdout
            with patch('sys.stdin.isatty',return_value=stdin),patch('builtins.input') as prompt:
                self.assertIs(await cli_command_approval(request,output=output),ApprovalDecision.DENY)
            prompt.assert_not_called();self.assertEqual(output.getvalue(),'')

    async def test_offline_keeps_capture_and_never_builds_live_client(self):
        class NoisyOffline(OfflineClient):
            async def create(inner,**kwargs):
                print('PRIVATE_OFFLINE_OUTPUT')
                return await super().create(**kwargs)
        with contextlib.redirect_stdout(io.StringIO()) as terminal, \
                patch('mybot.evaluation.coding_live.build_client') as build, \
                patch('mybot.evaluation.coding_benchmark.live_client') as live:
            result=await self.evaluation(offline_client_factory=lambda public:NoisyOffline())
        build.assert_not_called();live.assert_not_called()
        self.assertEqual(terminal.getvalue(),'')
        self.assertNotIn('PRIVATE_OFFLINE_OUTPUT',json.dumps(result))
        self.assertFalse(result['ability_score']);self.assertIsNone(result['actual_tokens'])

    async def test_range_hash_is_entire_file_and_legacy_mode_unchanged(self):
        root=create_repository(self.root/'hash',self.case.public)
        args=dict(path='app/cache.py',start_line=1,end_line=1)
        result=await ReadFileRangeTool(root,include_version=True).execute(**args)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata['file_sha256'],hashlib.sha256((root/'app/cache.py').read_bytes()).hexdigest())
        legacy=await ReadFileRangeTool(root).execute(**args)
        self.assertEqual(legacy.output,result.output)
        self.assertNotIn('file_sha256',legacy.metadata)

    async def test_wrong_patch_hash_reread_preview_and_retry_in_original_loop(self):
        class RetryDemo(DemoClient):
            rejected=False
            retried=False
            async def create(inner,**kwargs):
                instruction=kwargs['messages'][0]['content']
                for text in ('metadata.file_sha256','expected_sha256','Never guess','dry_run=true','stale_file_hash'):
                    self.assertIn(text,instruction)
                previous=next((m for m in reversed(kwargs['messages']) if m['role']=='tool'),None)
                if previous and 'stale_file_hash' in previous['content'] and not inner.retried:
                    inner.retried=True
                    call=N(id='fresh-read-after-stale',function=N(name='read_file_range',arguments=json.dumps(
                        {'path':'app/cache.py','start_line':1,'end_line':80})))
                    return N(choices=[N(message=N(content=None,tool_calls=[call]),finish_reason='tool_calls')],usage=None)
                response=await super().create(**kwargs)
                calls=response.choices[0].message.tool_calls
                if calls and calls[0].function.name=='apply_patch' and not inner.rejected:
                    inner.rejected=True
                    args=json.loads(calls[0].function.arguments)
                    args['dry_run']=False;args['changes'][0]['expected_sha256']='0'*64
                    calls[0].function.arguments=json.dumps(args)
                return response
        client=RetryDemo()
        report=await self.evaluation(offline_client_factory=lambda public:client)
        result=report['results'][0];metrics=result['metrics']
        self.assertTrue(client.rejected and client.retried)
        self.assertEqual(metrics['stale_patch_conflicts'],1)
        self.assertEqual(metrics['read_calls'],2)
        self.assertEqual(metrics['patch_write_attempts'],2)
        self.assertEqual(metrics['patch_preview_calls'],1)
        self.assertEqual(metrics['committed_patches'],1)
        self.assertEqual(metrics['real_test_runs'],1)
        self.assertEqual(result['agent_state'],'verified')
        self.assertTrue(result['judge']['verified_repair_success'])
        self.assertFalse(result['judge']['index_changed'])
        self.assertEqual(result['judge']['journal_attribution_mismatch'],0)
        self.assertEqual(metrics['protocol_false_verified_count'],0)

    def test_timeout_schema_and_hint_match_each_command_configuration(self):
        base=GatewayConfig(context_token_budget={'input_limit':160000}, )
        evaluation=configuration(base,self.root,Limits(task_timeout=600,request_timeout=120))
        self.assertEqual(evaluation.coding_command['timeout_seconds'],30)
        for seconds in (1,7,30,60):
            tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',
                command={'mode':'macos_readonly','timeout_seconds':seconds})
            controller=CodingTaskController(AutonomySettings(enabled=True),tools)
            hint=controller.instruction()
            state=json.loads(hint[hint.index('{'):])
            self.assertEqual(state['command_timeout_seconds'],seconds)
            self.assertIn('prefer omitting timeout_seconds',hint)
            spec=tools.get_tool('run_command').to_schema()['function']['parameters']
            self.assertEqual(spec['properties']['timeout_seconds']['maximum'],seconds)
            self.assertEqual(spec['properties']['timeout_seconds']['default'],seconds)
            self.assertEqual(spec['required'],['argv'])
        self.assertEqual(RunCommandTool.parameters['properties']['timeout_seconds']['maximum'],60)
        self.assertNotIn('default',RunCommandTool.parameters['properties']['timeout_seconds'])

    async def test_timeout_above_configuration_rejected_before_approval(self):
        approval=AsyncMock(side_effect=AssertionError('must not ask approval for excess timeout'))
        tool=RunCommandTool(self.root,command={'mode':'macos_readonly','timeout_seconds':30},
            patch_mode='write',approval_provider=approval)
        with patch('mybot.tools.run_command.run_process') as process:
            for seconds in (31,60):
                args={'argv':['python','-m','unittest'],'timeout_seconds':seconds}
                result=await tool.execute(**args)
                self.assertEqual(result.error,'timeout_exceeds_configuration')
                self.assertFalse(result.metadata['approved'] or result.metadata['spawned'])
                self.assertEqual(args['timeout_seconds'],seconds)
            for invalid in (0,True,61):
                result=await tool.execute(argv=['python'],timeout_seconds=invalid)
                self.assertEqual(result.error,'invalid_arguments')
        approval.assert_not_awaited();process.assert_not_called()

    async def test_live_legal_explicit_timeout_uses_terminal_sandbox_and_tests(self):
        result=await self.terminal_task('yes',command_timeout=30)
        self.assertEqual(result['agent_state'],'verified')
        self.assertTrue(result['agent_workflow_success'])
        self.assertTrue(result['judge']['verified_repair_success'])
        self.assertEqual(result['metrics']['real_test_runs'],1)
        self.assertEqual(result['metrics']['protocol_false_verified_count'],0)

    async def test_judge_pass_remains_distinct_from_timeout_blocked_workflow(self):
        class ExcessTimeout(DemoClient):
            async def create(inner,**kwargs):
                response=await super().create(**kwargs)
                calls=response.choices[0].message.tool_calls
                if calls and calls[0].function.name=='run_command':
                    args=json.loads(calls[0].function.arguments);args['timeout_seconds']=60
                    calls[0].function.arguments=json.dumps(args)
                return response
        approval=AsyncMock(side_effect=AssertionError('excess timeout must not reach approval'))
        with patch('mybot.tools.run_command.run_process') as process:
            report=await self.evaluation(offline_client_factory=lambda public:ExcessTimeout(),command_provider=approval)
        approval.assert_not_awaited();process.assert_not_called()
        result=report['results'][0]
        self.assertEqual(result['agent_state'],'blocked')
        self.assertFalse(result['agent_workflow_success'])
        self.assertEqual(result['controller']['stop_reason'],'timeout_exceeds_configuration')
        self.assertEqual(result['failure'],'timeout_exceeds_configuration')
        self.assertEqual(result['metrics']['real_test_runs'],0)
        self.assertEqual(result['metrics']['committed_patches'],1)
        self.assertEqual(result['metrics']['patch_preview_calls'],1)
        self.assertEqual(result['judge']['judge_state'],'hidden_pass')
        self.assertTrue(result['judge']['public']['passed'] and result['judge']['hidden']['passed'])
        self.assertTrue(result['judge']['verified_repair_success'])
        self.assertEqual(report['verified_repair_cases'],1)
        self.assertEqual(report['agent_workflow_success_cases'],0)
        self.assertEqual(report['agent_blocked_count'],1)
        self.assertEqual(report['failures'],{'timeout_exceeds_configuration':1})
        saved=save_report(report,self.root/'reports')
        self.assertEqual(json.loads(saved.read_text())['results'][0]['failure'],'timeout_exceeds_configuration')

    def preview_arguments(self, error, version):
        change={'op':'update','path':'app/cache.py','expected_sha256':version,
            'edits':[{'old_text':'now > expires','new_text':'now >= expires'}]}
        if error=='invalid_arguments':change['unknown_field']='PRIVATE_PATCH_ARGUMENT'
        elif error=='overlapping_edits':change['edits']*=2
        elif error=='no_effective_changes':change['edits'][0]['new_text']='now > expires'
        elif error=='stale_file_hash':change['expected_sha256']='0'*64
        elif error=='anchor_not_found':change['edits'][0]['old_text']='ABSENT_ANCHOR'
        elif error=='ambiguous_context':change['edits'][0]['old_text']='self'
        return {'dry_run':True,'changes':[change]}

    async def patch_context(self, name):
        root=create_repository(self.root/name,self.case.public)
        tools=build_default_tool_registry(root,coding_enabled=True,patch_mode='write')
        read=await tools.execute('read_file_range',dict(path='app/cache.py',start_line=1,end_line=80))
        self.assertTrue(read.success)
        return root,tools,CodingTaskController(AutonomySettings(enabled=True),tools),read.metadata['file_sha256']

    async def test_preview_input_failures_allow_regeneration_before_writes(self):
        from mybot.tools.patch import _RETRY
        self.assertEqual(_RETRY,{'stale_file_hash','anchor_not_found','ambiguous_context'})
        for error in ('invalid_arguments','overlapping_edits','no_effective_changes',
                      'stale_file_hash','anchor_not_found','ambiguous_context'):
            with self.subTest(error=error):
                root,tools,controller,version=await self.patch_context(error)
                before=snapshot(root);index=(root/'.git/index').read_bytes();tool=tools.get_tool('apply_patch')
                args=self.preview_arguments(error,version)
                with patch.object(tool,'_stage') as stage,patch.object(tool,'_publish') as publish:
                    result=await tools.execute('apply_patch',args)
                stage.assert_not_called();publish.assert_not_called()
                controller.observe('apply_patch',args,result)
                self.assertEqual(result.error,error)
                self.assertTrue(result.metadata['safe_to_retry'])
                self.assertIn(result.metadata['failure_phase'],('validation','preflight'))
                self.assertFalse(result.metadata['applied'] or result.metadata['execution_evidence'])
                self.assertEqual(controller.state,'running')
                self.assertEqual(snapshot(root),before);self.assertEqual((root/'.git/index').read_bytes(),index)
                self.assertEqual(list(root.rglob('.mybot-patch-*')),[])

    async def test_preview_recovery_never_applies_to_write_or_later_phases(self):
        for error in ('invalid_arguments','overlapping_edits','no_effective_changes'):
            root,tools,controller,version=await self.patch_context('write-'+error)
            args=self.preview_arguments(error,version);args['dry_run']=False
            result=await tools.execute('apply_patch',args)
            controller.observe('apply_patch',args,result)
            self.assertEqual(result.error,error);self.assertFalse(result.metadata['safe_to_retry'])
            self.assertEqual(controller.state,'blocked')
        root,tools,controller,version=await self.patch_context('late-preview')
        tool=tools.get_tool('apply_patch');args=self.preview_arguments('',version)
        with patch.object(tool,'_diff',side_effect=ValueError('no_effective_changes')):
            result=await tool.execute(**args)
        self.assertEqual(result.metadata['failure_phase'],'preview')
        self.assertFalse(result.metadata['safe_to_retry'])
        for dry_run in ('yes',1):
            args['dry_run']=dry_run
            result=await tool.execute(**args)
            self.assertEqual(result.error,'invalid_arguments');self.assertFalse(result.metadata['safe_to_retry'])

    async def corrected_preview(self, error):
        owner=self
        class CorrectPreview(DemoClient):
            injected=False
            reread=False
            async def create(inner,**kwargs):
                self.assertIn('Before any apply_patch preview or write',kwargs['messages'][0]['content'])
                previous=next((m for m in reversed(kwargs['messages']) if m['role']=='tool'),None)
                if previous and previous['content'].startswith('Error: '+error) and not inner.reread:
                    inner.reread=True
                    call=N(id='reread-after-preview',function=N(name='read_file_range',arguments=json.dumps(
                        {'path':'app/cache.py','start_line':1,'end_line':80})))
                    return N(choices=[N(message=N(content=None,tool_calls=[call]),finish_reason='tool_calls')],usage=None)
                response=await super().create(**kwargs)
                calls=response.choices[0].message.tool_calls
                if calls and calls[0].function.name=='apply_patch' and not inner.injected:
                    inner.injected=True
                    version=json.loads(calls[0].function.arguments)['changes'][0]['expected_sha256']
                    calls[0].function.arguments=json.dumps(owner.preview_arguments(error,version))
                return response
        client=CorrectPreview()
        report=await self.evaluation(offline_client_factory=lambda public:client)
        result=report['results'][0]
        self.assertTrue(client.injected and client.reread)
        self.assertEqual(result['agent_state'],'verified');self.assertTrue(result['agent_workflow_success'])
        self.assertTrue(result['judge']['verified_repair_success'])
        self.assertEqual(result['metrics']['read_calls'],2)
        self.assertEqual(result['metrics']['patch_preview_calls'],2)
        self.assertEqual(result['metrics']['committed_patches'],1)
        self.assertEqual(result['metrics']['real_test_runs'],1)
        failure=next(e for e in result['trace'] if e['event']=='tool' and not e['success'])
        self.assertEqual(failure['error'],error);self.assertTrue(failure['patch_safe_to_retry'])
        self.assertEqual(failure['patch_failure_state'],'preflight_failed')
        self.assertFalse(result['judge']['index_changed'])
        self.assertEqual(result['judge']['journal_attribution_mismatch'],0)
        self.assertEqual(result['metrics']['protocol_false_verified_count'],0)
        self.assertNotIn('PRIVATE_PATCH_ARGUMENT',json.dumps(report))

    async def test_schema_preview_correction_in_original_loop(self):await self.corrected_preview('invalid_arguments')

    async def test_overlapping_preview_correction_in_original_loop(self):await self.corrected_preview('overlapping_edits')

    async def test_noop_preview_correction_in_original_loop(self):await self.corrected_preview('no_effective_changes')

    async def test_repeated_preview_errors_stay_within_original_budget(self):
        class RepeatPreview(OfflineClient):
            count=0
            async def create(inner,**kwargs):
                inner.count+=1
                name='read_file_range' if inner.count==1 else 'apply_patch'
                args={'path':'app/cache.py','start_line':1,'end_line':80} if inner.count==1 else {'dry_run':True,'changes':[]}
                call=N(id='repeat-preview-'+str(inner.count),function=N(name=name,arguments=json.dumps(args)))
                return N(choices=[N(message=N(content=None,tool_calls=[call]),finish_reason='tool_calls')],usage=None)
        report=await self.evaluation(offline_client_factory=lambda public:RepeatPreview())
        result=report['results'][0]
        self.assertEqual(result['agent_state'],'budget_exhausted')
        self.assertEqual(result['controller']['stop_reason'],'max_no_progress')
        self.assertEqual(result['controller']['repeated_actions'],3)
        self.assertLessEqual(report['llm_requests'],12)
        self.assertEqual(result['metrics']['patch_preview_calls'],4)
        self.assertEqual(result['metrics']['patch_write_attempts'],0)
        self.assertEqual(result['metrics']['real_test_runs'],0)
        self.assertFalse(result['judge']['modified_code'])

    async def test_unsafe_patch_paths_still_block(self):
        for index,path in enumerate(('../escape.py','.env','.git/config','credentials.json','config/config.json')):
            root,tools,controller,version=await self.patch_context('unsafe-'+str(index))
            before=snapshot(root);args=self.preview_arguments('',version);args['changes'][0]['path']=path
            result=await tools.execute('apply_patch',args)
            controller.observe('apply_patch',args,result)
            self.assertIn(result.error,('path_outside_workspace','sensitive_path_denied'))
            self.assertFalse(result.metadata['safe_to_retry']);self.assertEqual(controller.state,'blocked')
            self.assertEqual(snapshot(root),before)

    async def test_permission_failure_still_blocks_preview(self):
        root,tools,controller,version=await self.patch_context('permission')
        args=self.preview_arguments('',version);tool=tools.get_tool('apply_patch')
        with patch.object(tool,'_read',side_effect=PermissionError('PRIVATE_PERMISSION_BODY')):
            result=await tools.execute('apply_patch',args)
        controller.observe('apply_patch',args,result)
        self.assertEqual(result.error,'permission_denied');self.assertFalse(result.metadata['safe_to_retry'])
        self.assertEqual(controller.state,'blocked');self.assertNotIn('PRIVATE_PERMISSION_BODY',result.to_text())

    async def test_write_rollback_and_uncertain_failures_still_stop(self):
        for kind in ('stage','publish','rollback_conflict','rollback_failure'):
            root,tools,controller,version=await self.patch_context(kind)
            tool=tools.get_tool('apply_patch');args=self.preview_arguments('',version);args['dry_run']=False
            publish=tool._publish;replace_file=os.replace;calls=0
            def fail_publish(item):
                if kind=='publish':raise OSError('PRIVATE_PUBLISH_FAILURE')
                publish(item)
                if kind=='rollback_conflict':(root/'app/cache.py').write_bytes(b'external user content')
                raise OSError('PRIVATE_PUBLISH_FAILURE')
            def fail_replace(*a,**kw):
                nonlocal calls
                calls+=1
                if calls==2:raise OSError('PRIVATE_ROLLBACK_FAILURE')
                return replace_file(*a,**kw)
            with contextlib.ExitStack() as stack:
                if kind=='stage':stack.enter_context(patch.object(tool,'_stage',side_effect=ValueError('invalid_arguments')))
                else:stack.enter_context(patch.object(tool,'_publish',side_effect=fail_publish))
                if kind=='rollback_failure':stack.enter_context(patch('mybot.tools.patch.os.replace',side_effect=fail_replace))
                result=await tools.execute('apply_patch',args)
            controller.observe('apply_patch',args,result)
            self.assertFalse(result.metadata['safe_to_retry'])
            status={'stage':'preflight_failed','publish':'commit_failed_rolled_back',
                'rollback_conflict':'rollback_conflict','rollback_failure':'partial_failure_possible'}[kind]
            self.assertEqual(result.metadata['status'],status)
            self.assertEqual(controller.state,'execution_uncertain' if kind.startswith('rollback') else 'blocked')
            if kind=='rollback_conflict':self.assertEqual((root/'app/cache.py').read_bytes(),b'external user content')
            self.assertNotIn('PRIVATE_',result.to_text())

    async def test_malformed_patch_json_remains_conservative(self):
        class Malformed(OfflineClient):
            async def create(inner,**kwargs):
                call=N(id='malformed-patch',function=N(name='apply_patch',arguments='{PRIVATE_MALFORMED_JSON'))
                return N(choices=[N(message=N(content=None,tool_calls=[call]),finish_reason='tool_calls')],usage=None)
        report=await self.evaluation(offline_client_factory=lambda public:Malformed())
        result=report['results'][0];event=next(e for e in result['trace'] if e.get('name')=='apply_patch')
        self.assertEqual(result['agent_state'],'blocked')
        self.assertEqual(event['error'],'invalid_arguments')
        self.assertEqual(event['patch_failure_phase'],'argument_parsing')
        self.assertFalse(event['patch_safe_to_retry'])
        self.assertNotIn('PRIVATE_MALFORMED_JSON',json.dumps(report))

    def test_patch_trace_allowlist_never_retains_arbitrary_text(self):
        from mybot.evaluation.coding_metrics import PATCH_ERROR_CODES
        for error in (*sorted(PATCH_ERROR_CODES),'PRIVATE_EXCEPTION_BODY',['PRIVATE_EXCEPTION_BODY']):
            trace=CodingTrace();trace.names={'apply_patch'};trace.workspace=self.root
            result=ToolResult(False,'PRIVATE_SOURCE_BODY',error=error,
                metadata={'status':'PRIVATE_STATUS','failure_phase':{'PRIVATE_PHASE':1},'safe_to_retry':'PRIVATE_BOOLEAN'})
            trace.tool('apply_patch',{'dry_run':True,'changes':['PRIVATE_PATCH_BODY']},result,0)
            event=trace.events[-1]
            expected=error if isinstance(error,str) and error in PATCH_ERROR_CODES else 'other_patch_error'
            self.assertEqual(event['error'],expected)
            self.assertEqual(event['patch_failure_state'],'unknown_patch_failure')
            self.assertEqual(event['patch_failure_phase'],'unknown_patch_phase')
            self.assertFalse(event['patch_safe_to_retry'])
            self.assertNotIn('PRIVATE_',json.dumps(trace.events))


def check_real_coding_eval():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CodingEvaluationChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_real_coding_eval()
