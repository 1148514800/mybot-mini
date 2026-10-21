"""Phase25 durable orchestration tests; synthetic reports and no paid calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
from mybot.evaluation import coding_campaign as c


class CampaignChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'campaign'
        self.g=patch.object(c,'git',side_effect=lambda *a:'' if a[0]=='status' else 'a'*40);self.g.start();self.addCleanup(self.g.stop)
        from mybot.config import GatewayConfig
        self.freeze=c.freeze(GatewayConfig(provider='coco2',model='gpt-6-astra',api_key=None,base_url=None))
        self.p=patch.object(c,'freeze',return_value=self.freeze);self.p.start();self.addCleanup(self.p.stop)

    def init(self,live=True):return c.create(self.root,rounds=3,live=live)

    def report(self,slot=None,live=True):
        f=self.freeze;slot=slot or self.init()['slots'][0]
        metrics=dict(committed_patches=1,real_test_runs=1,approval_denials=0,sandbox_failures=0,
            execution_uncertain_count=0,protocol_false_verified_count=0,workspace_escape_attempts=0,tool_call_ids_paired=True)
        j=dict(judge_state='hidden_pass',verified_repair_success=True,public={'passed':True},hidden={'passed':True},
            protected_file_changes=0,unrelated_file_changes=0,index_changed=False,journal_attribution_mismatch=0)
        return dict(mode='live' if live else 'offline',mybot_commit=f['benchmark_harness_commit'],
            provider_label=f['provider'] if live else 'offline',model_name=f['model'] if live else 'offline-script',
            benchmark_sha256=f['benchmark_sha256'],grading_code_sha256=f['grading_code_sha256'],
            dependency_lock_sha256=f['dependency_lock_sha256'],limits=f['limits'],worktree_dirty=False,
            case_ids=[slot['case_id']],llm_requests=2,successful_responses=2,total_tokens=None,duration_seconds=3,
            results=[dict(case_id=slot['case_id'],difficulty='easy',agent_state='verified',agent_workflow_success=True,
                runtime_error=None,metrics=metrics,controller=dict(current_revision=2,last_verified_revision=2),judge=j,
                trace=[dict(event='tool',name='run_command',success=True,real_test_run=True,current_revision_test_evidence=True)])])

    def test_discovery_priority_and_36_unique_runs(self):
        m=self.init();ids=[s['run_id'] for s in m['slots']]
        self.assertEqual(len(ids),36);self.assertEqual(len(set(ids)),36)
        self.assertEqual([s['case_id'] for s in m['slots'][:3]],list(c.PRIORITY))

    def test_duplicate_cases_and_rounds_rejected(self):
        for kw in ({'rounds':4},{'case_ids':['x']},{'case_ids':['cache-ttl-001']*2}):
            with self.assertRaises(ValueError):c.create(self.root,**kw)

    def test_no_overwrite(self):
        self.init()
        with self.assertRaises(ValueError):self.init()

    def test_freeze_is_sanitized(self):
        s=json.dumps(self.freeze)
        self.assertNotIn('api_key',s);self.assertNotIn('base_url',s)
        self.assertEqual(self.freeze['limits']['request_timeout'],90)
        self.assertEqual(self.freeze['agent']['coding_command']['timeout_seconds'],30)

    def test_success_does_not_require_revision_one(self):
        self.assertTrue(c.strict_success(self.report()))

    def test_each_success_condition_required(self):
        r=self.report()
        cases=[('agent_state','blocked'),('agent_workflow_success',False)]
        for key,v in cases:
            x=copy.deepcopy(r);x['results'][0][key]=v;self.assertFalse(c.strict_success(x))
        for k in ('protected_file_changes','unrelated_file_changes','journal_attribution_mismatch','index_changed'):
            x=copy.deepcopy(r);x['results'][0]['judge'][k]=1;self.assertFalse(c.strict_success(x))
        for k in ('sandbox_failures','execution_uncertain_count','protocol_false_verified_count','approval_denials'):
            x=copy.deepcopy(r);x['results'][0]['metrics'][k]=1;self.assertFalse(c.strict_success(x))
        x=copy.deepcopy(r);x['results'][0]['trace']=[];self.assertFalse(c.strict_success(x))
        x=copy.deepcopy(r);x['results'][0]['controller']['last_verified_revision']=1;self.assertFalse(c.strict_success(x))

    async def test_completion_resume_skips_no_replay(self):
        m=self.init();reports=[self.report(s) for s in m['slots'][:2]]
        with patch.object(c,'evaluate',AsyncMock(side_effect=reports)) as e:
            await c.run_next(self.root,live=True,confirm_api_cost=True)
            await c.run_next(self.root,live=True,confirm_api_cost=True)
        self.assertEqual(e.call_count,2);self.assertNotEqual(e.call_args_list[0].kwargs['case_ids'],e.call_args_list[1].kwargs['case_ids'])
        self.assertEqual(c.summary(self.root)['completed'],2)

    async def test_crash_never_automatically_replayed(self):
        self.init()
        with patch.object(c,'evaluate',AsyncMock(side_effect=RuntimeError('SECRET_SOURCE'))) as e:
            with self.assertRaises(RuntimeError):await c.run_next(self.root,live=True,confirm_api_cost=True)
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True,confirm_api_cost=True)
        self.assertEqual(e.call_count,1)
        self.assertNotIn('SECRET_SOURCE',''.join(p.read_text() for p in self.root.rglob('*.json')))

    async def test_api_failure_preserved_and_next_isolated(self):
        m=self.init();r=self.report(m['slots'][0]);r['results'][0].update(agent_state='blocked',runtime_error='provider_error');r['results'][0]['controller']['stop_reason']='provider_error'
        with patch.object(c,'evaluate',AsyncMock(return_value=r)):await c.run_next(self.root,live=True,confirm_api_cost=True)
        s=c.summary(self.root);self.assertEqual(s['completed'],1);self.assertEqual(s['strict_successes'],0)
        self.assertIn('provider_api_error',s['failures']);self.assertEqual(s['pending'],35)

    async def test_uncertain_result_pauses_following_live(self):
        m=self.init();r=self.report(m['slots'][0]);r['results'][0]['agent_state']='execution_uncertain'
        with patch.object(c,'evaluate',AsyncMock(return_value=r)) as e:
            await c.run_next(self.root,live=True,confirm_api_cost=True)
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True,confirm_api_cost=True)
        self.assertEqual(e.call_count,1)

    async def test_provenance_mismatch_preserves_raw_and_blocks(self):
        self.init();r=self.report(c.read(self.root/'manifest.json')['slots'][0]);r['mybot_commit']='wrong'
        with patch.object(c,'evaluate',AsyncMock(return_value=r)):
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True,confirm_api_cost=True)
        self.assertEqual(c.summary(self.root)['uncertain'],1)
        self.assertTrue(next(self.root.glob('runs/*/raw.json')).exists())

    async def test_changed_freeze_no_api(self):
        self.init()
        with patch.object(c,'freeze',return_value={}),patch.object(c,'evaluate',AsyncMock()) as e:
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True,confirm_api_cost=True)
        e.assert_not_called()

    async def test_cost_flags_no_api(self):
        self.init()
        with patch.object(c,'evaluate',AsyncMock()) as e:
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True)
        e.assert_not_called()

    async def test_missing_or_tampered_evidence_rejected(self):
        m=self.init();r=self.report(m['slots'][0])
        with patch.object(c,'evaluate',AsyncMock(return_value=r)):await c.run_next(self.root,live=True,confirm_api_cost=True)
        p=next(self.root.glob('runs/*/raw.json'));data=p.read_bytes();p.write_bytes(b'{}')
        with self.assertRaises(ValueError):c.summary(self.root)
        p.write_bytes(data);p.unlink()
        with self.assertRaises(ValueError):c.summary(self.root)

    def test_duplicate_run_identity_rejected(self):
        m=self.init();m['slots'][1]=m['slots'][0];(self.root/'manifest.json').write_bytes(c.encoded(m))
        with self.assertRaises(ValueError):c.inventory(self.root)

    def test_configuration_hash_corruption_rejected(self):
        m=self.init();m['frozen']['model']='wrong';(self.root/'manifest.json').write_bytes(c.encoded(m))
        with self.assertRaises(ValueError):c.summary(self.root)

    def test_percentiles_and_unknown_values(self):
        d=c.distribution([None,1,3,5]);self.assertEqual(d['missing'],1);self.assertEqual(d['p50'],3)
        self.assertIsNone(c.distribution([None])['total'])

    def test_pending_not_counted_as_failed_attempt(self):
        self.init();s=c.summary(self.root)
        self.assertEqual(s['planned'],36);self.assertEqual(s['completed'],0);self.assertIsNone(s['completed_run_success_rate'])

    async def test_offline_stays_separate(self):
        m=self.init(live=False);r=self.report(m['slots'][0],live=False)
        with patch.object(c,'evaluate',AsyncMock(return_value=r)) as e:await c.run_next(self.root)
        self.assertFalse(e.call_args.kwargs['live']);self.assertFalse(c.summary(self.root)['strict_successes'])

    async def test_external_canonical_root_reaches_synthetic_model(self):
        # A real disposable Git checkout exercises the unchanged registry/baseline
        # identity gate. No model API, fake TTY, command or approval is involved.
        from mybot.tools import build_default_tool_registry
        from mybot.config import GatewayConfig
        from mybot.evaluation.coding_benchmark import configuration, OfflineClient
        from mybot.evaluation.coding_fixtures import create_repository, Image
        from mybot.evaluation.coding_metrics import BenchmarkAgent, CodingTrace
        from mybot.evaluation.coding_live import CodingClient, RequestBudget
        from mybot.agent import ContextBuilder
        root=create_repository(Path(self.tmp.name).resolve()/'external',{'sample.py':Image(b'x = 1\n',0o644)})
        config=configuration(GatewayConfig(),root,c.LIMITS)
        tools=build_default_tool_registry(root,coding_enabled=True,patch_mode='write',command=config.coding_command)
        trace=CodingTrace()
        agent=BenchmarkAgent(CodingClient(OfflineClient(),trace,RequestBudget(c.LIMITS)),config,tools,ContextBuilder(root),trace=trace)
        await agent.handle_message('Investigate sample.py, no command required.')
        self.assertGreater(agent.last_coding_report['model_requests'],0)
        self.assertNotEqual(agent.last_coding_report['stop_reason'],'git_baseline_or_registry_unavailable')
        self.assertNotEqual(agent.last_coding_report['state'],'verified')
        if agent._git_capsule:agent._git_capsule.close()

    def test_external_scope_and_public_acceptance(self):
        from scripts.evaluate_external_coding import ACCEPTANCE,PROMPT
        import ast
        ast.parse(ACCEPTANCE)
        self.assertIn('Modify only jsonpointer.py',PROMPT)
        self.assertIn('test_phase25_fragment.py',PROMPT)
        self.assertNotIn('evals/coding_benchmark',PROMPT)

    async def test_external_verifier_requires_real_sandbox_evidence(self):
        from scripts.evaluate_external_coding import verify
        from mybot.tools.base import ToolResult
        from types import SimpleNamespace
        fake=SimpleNamespace(execute=AsyncMock(return_value=ToolResult(True,json.dumps({'stdout':'','stderr':'Ran 6 tests in 0.001s\nOK\n'}),metadata={'status':'completed','approved':True,'spawned':True,'sandbox_applied':True,'exit_code':0})))
        r=await verify(fake);self.assertEqual(r['tests'],6);self.assertTrue(r['sandbox_applied'])
        self.assertEqual(fake.execute.call_args.args[0],'run_command')

    async def test_external_output_sensitive_text_not_retained(self):
        from scripts.evaluate_external_coding import verify
        from mybot.tools.base import ToolResult
        from types import SimpleNamespace
        fake=SimpleNamespace(execute=AsyncMock(return_value=ToolResult(False,json.dumps({'stdout':'SECRET_SOURCE','stderr':'Ran 1 test in 0.01s\nFAILED\n'}),metadata={'status':'completed','exit_code':1})))
        self.assertNotIn('SECRET_SOURCE',json.dumps(await verify(fake)))

    def test_rounds_are_not_best_of_three(self):
        self.init();s=c.summary(self.root)
        self.assertEqual(len(s['rounds']),3)
        self.assertEqual(s['coverage'],0)
        self.assertFalse(s['rounds']['1']['round_complete'])

    async def test_cancelled_approval_timeout_stops_next_slot(self):
        m=self.init();r=self.report(m['slots'][0]);x=r['results'][0]
        x.update(agent_state='cancelled',runtime_error='task_timeout')
        x['controller'].update(stop_reason='task_interrupted',command_attempts=1,verification='expired')
        x['metrics'].update(command_attempts=0,execution_uncertain_count=0,real_test_runs=0)
        with patch.object(c,'evaluate',AsyncMock(return_value=r)) as e:
            await c.run_next(self.root,live=True,confirm_api_cost=True)
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True,confirm_api_cost=True)
        self.assertEqual(e.call_count,1)
        self.assertEqual(c.summary(self.root)['pause_required_runs'],[m['slots'][0]['run_id']])

    def test_incomplete_command_pauses_without_uncertain_flag(self):
        r=self.report();r['results'][0]['controller']['command_attempts']=1
        r['results'][0]['metrics']['command_attempts']=0
        self.assertEqual(c.pause_reason(r),'incomplete_command_requires_audit')

    def test_timeout_does_not_invent_journal_mismatch(self):
        r=self.report();x=r['results'][0];x.update(agent_state='cancelled',runtime_error='task_timeout')
        x['controller']['verification']='expired'
        labels=c.classify(r)
        self.assertIn('task_timeout',labels);self.assertIn('supervisor_audit_required',labels)
        self.assertNotIn('revision_or_journal_mismatch',labels)

    def test_full_frozen_tools_include_plan_and_sampling(self):
        self.assertEqual(len(self.freeze['tool_schemas']),10)
        self.assertTrue({'create_plan','update_plan'}<={t['function']['name'] for t in self.freeze['tool_schemas']})
        self.assertEqual(self.freeze['temperature'],0.1);self.assertEqual(self.freeze['max_retries'],0)

    def test_supervisor_inherits_terminal_without_pipe_or_input(self):
        from mybot.evaluation.coding_supervisor import supervise
        from unittest.mock import Mock
        child=Mock();child.wait.return_value=0
        with patch('mybot.evaluation.coding_supervisor.subprocess.Popen',return_value=child) as popen:
            self.assertEqual(supervise(['trusted-python','-m','worker']),0)
        popen.assert_called_once_with(['trusted-python','-m','worker'])
        child.send_signal.assert_not_called()

    def test_supervisor_timeout_signals_and_never_replays(self):
        from mybot.evaluation.coding_supervisor import supervise
        from unittest.mock import Mock
        import subprocess,signal
        child=Mock();child.wait.side_effect=[subprocess.TimeoutExpired('worker',1),0]
        with patch('mybot.evaluation.coding_supervisor.subprocess.Popen',return_value=child) as popen:
            self.assertEqual(supervise(['worker'],timeout=1),124)
        self.assertEqual(popen.call_count,1);child.send_signal.assert_called_once_with(signal.SIGINT)

    def test_unresponsive_worker_is_stopped_not_replayed(self):
        from mybot.evaluation.coding_supervisor import supervise
        from unittest.mock import Mock
        import subprocess
        child=Mock();child.wait.side_effect=[subprocess.TimeoutExpired('worker',1),subprocess.TimeoutExpired('worker',1),0]
        with patch('mybot.evaluation.coding_supervisor.subprocess.Popen',return_value=child):
            self.assertEqual(supervise(['worker'],timeout=1,grace=1),124)
        child.kill.assert_called_once()

    def test_real_pty_is_inherited_by_fresh_worker(self):
        import os,pty,sys,subprocess,select
        master,slave=pty.openpty()
        code="from mybot.evaluation.coding_supervisor import supervise; import sys; raise SystemExit(supervise([sys.executable,'-c','import sys; print(\"TTY_PROOF\",sys.stdin.isatty(),sys.stdout.isatty())'],timeout=3))"
        try:
            child=subprocess.Popen([sys.executable,'-c',code],stdin=slave,stdout=slave,stderr=slave)
            self.assertEqual(child.wait(timeout=5),0)
            ready,_,_=select.select([master],[],[],1);self.assertTrue(ready)
            self.assertIn(b'TTY_PROOF True True',os.read(master,4096))
        finally:os.close(master);os.close(slave)

    def test_native_approval_not_overridden(self):
        import inspect
        source=inspect.getsource(c.run_next)
        self.assertNotIn('command_provider=',source);self.assertNotIn('offline_client_factory=',source)


def check_coding_campaign():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(CampaignChecks)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_coding_campaign()
