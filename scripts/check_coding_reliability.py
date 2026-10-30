"""Phase25-R offline cancellation, evidence and resume regressions; no paid clients."""
import asyncio
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import unittest
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, patch

from mybot.config import GatewayConfig
from scripts.check_coding_campaign import CampaignChecks
from scripts.coding_benchmark_demo import DemoClient
from mybot.evaluation import coding_campaign as c
ORIGINAL_FREEZE = c.freeze
from mybot.evaluation.coding_lifecycle import Attempt, WorkspaceDirectory
from mybot.evaluation.coding_approval import AttemptApproval
from mybot.evaluation.coding_benchmark import evaluate, OfflineClient
from mybot.evaluation.coding_live import CodingClient, Limits, RequestBudget
from mybot.evaluation.coding_metrics import CodingTrace, BenchmarkAgent
from mybot.evaluation.coding_fixtures import load_benchmark, create_repository, snapshot
from mybot.tools.command_approval import inspectable_command
from mybot.mcp_client.approval import ApprovalDecision


class ReliabilityChecks(unittest.IsolatedAsyncioTestCase):
    setUp = CampaignChecks.setUp
    init = CampaignChecks.init
    report = CampaignChecks.report

    async def eval(self, **kw):
        opts=dict(base_config=GatewayConfig(context_token_budget={'input_limit':160000}), case_ids=['cache-ttl-001'],limits=Limits(max_cases=1,max_requests=12),
            offline_client_factory=lambda public:DemoClient())
        opts.update(kw)
        return await evaluate(**opts)

    async def completed(self):
        m=c.read(self.root/'manifest.json') if self.root.exists() else self.init()
        with patch.object(c,'evaluate',AsyncMock(return_value=self.report(m['slots'][0]))):
            await c.run_next(self.root,live=True,confirm_api_cost=True)
        return self.root/'runs'/m['slots'][0]['run_id']

    async def test_runtime_error_cannot_be_strict_success(self):
        r=self.report();r['results'][0]['runtime_error']='task_timeout'
        self.assertFalse(c.strict_success(r))

    async def test_cleanup_uncertain_cannot_be_strict_success(self):
        r=self.report();r['results'][0]['lifecycle']={'execution_uncertain':True}
        self.assertFalse(c.strict_success(r));self.assertTrue(c.pause_reason(r))

    async def test_controller_deadline_stops_even_without_runtime_error(self):
        r=self.report();r['results'][0]['controller']['stop_reason']='max_task_seconds'
        self.assertTrue(c.pause_reason(r));self.assertIn('task_timeout',c.classify(r))

    async def test_finished_run_id_must_match(self):
        folder=await self.completed();p=folder/'finished.json';d=c.read(p);d['run_id']='other';p.write_bytes(c.encoded(d))
        with self.assertRaises(ValueError):c.inventory(self.root)

    async def test_finished_attempt_must_match(self):
        folder=await self.completed();p=folder/'finished.json';d=c.read(p);d['attempt_id']='f'*32;p.write_bytes(c.encoded(d))
        with self.assertRaises(ValueError):c.inventory(self.root)

    async def test_cross_campaign_copy_rejected(self):
        folder=await self.completed();p=folder/'started.json';d=c.read(p);d['campaign_id']='other';p.write_bytes(c.encoded(d))
        with self.assertRaises(ValueError):c.inventory(self.root)

    async def test_terminal_evidence_tampering_rejected(self):
        folder=await self.completed();(folder/'terminal.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):c.inventory(self.root)

    async def test_frozen_plan_edit_rejected(self):
        self.init();p=self.root/'manifest.json';d=c.read(p);d['slots'].pop();p.write_bytes(c.encoded(d))
        with self.assertRaises(ValueError):c.inventory(self.root)

    async def test_blocked_marker_cannot_be_overridden_by_success(self):
        folder=await self.completed();start=c.read(folder/'started.json')
        c.write_new(folder/'blocked.json',{**start,'category':'execution_uncertain'})
        self.assertFalse(c.inventory(self.root)[1][0]['strict_success'])
        with patch.object(c,'evaluate',AsyncMock()) as e:
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True,confirm_api_cost=True)
        e.assert_not_called()

    async def test_cancelled_run_durable_and_no_next_slot(self):
        m=self.init();entered=asyncio.Event()
        async def worker(**kw):
            entered.set();await asyncio.Event().wait()
        with patch.object(c,'evaluate',worker):
            task=asyncio.create_task(c.run_next(self.root,live=True,confirm_api_cost=True))
            await asyncio.wait_for(entered.wait(), 10);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        with patch.object(c,'evaluate',AsyncMock()) as e:
            with self.assertRaises(ValueError):await c.run_next(self.root,live=True,confirm_api_cost=True)
        e.assert_not_called();self.assertEqual(c.summary(self.root)['uncertain'],1)

    async def test_completed_not_replayed_and_repeat_attempt_distinct(self):
        m=self.init();m['slots']=[s for s in m['slots'] if s['case_id']==m['slots'][0]['case_id']]
        m['plan_sha256']=c.sha(m['slots']);(self.root/'manifest.json').write_bytes(c.encoded(m))
        with patch.object(c,'evaluate',AsyncMock(side_effect=[self.report(s) for s in m['slots']])) as e:
            for _ in m['slots']:await c.run_next(self.root,live=True,confirm_api_cost=True)
            self.assertIsNone(await c.run_next(self.root,live=True,confirm_api_cost=True))
        ids=[c.read(p)['attempt_id'] for p in self.root.glob('runs/*/started.json')]
        self.assertEqual(len(set(ids)),3);self.assertEqual(e.call_count,3)

    async def test_repeated_cancel_waits_for_cleanup(self):
        a=Attempt();entered=asyncio.Event();cleaning=asyncio.Event();release=asyncio.Event()
        async def work():
            entered.set()
            try:await asyncio.Event().wait()
            finally:cleaning.set();await release.wait()
        parent=asyncio.create_task(a.run(work(),60));await asyncio.wait_for(entered.wait(), 10);parent.cancel();await cleaning.wait()
        parent.cancel();await asyncio.sleep(0);self.assertFalse(parent.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):await parent
        self.assertFalse(a.active);self.assertTrue(a.cleanup_confirmed)

    async def test_swallowed_cancel_cannot_return_success(self):
        a=Attempt();entered=asyncio.Event()
        async def work():
            entered.set()
            try:await asyncio.Event().wait()
            except asyncio.CancelledError:return 'pretend success'
        task=asyncio.create_task(a.run(work(),60));await asyncio.wait_for(entered.wait(), 10);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertNotEqual(a.reason,'completed')

    async def test_unsettled_task_retains_workspace(self):
        a=Attempt();entered=asyncio.Event();release=asyncio.Event()
        async def work():entered.set();await release.wait()
        task=asyncio.create_task(work());await asyncio.wait_for(entered.wait(), 10)
        await a.settle(task,timeout=0)
        self.assertFalse(a.cleanup_confirmed)
        with WorkspaceDirectory() as directory:
            directory.retain=True;root=directory.path
        self.assertTrue(root.exists());release.set();await task
        import shutil
        shutil.rmtree(root)

    async def test_revoked_client_cannot_start_model(self):
        a=Attempt();a.revoke('cancelled');trace=CodingTrace();trace.attempt=a
        raw=OfflineClient();raw.create=AsyncMock()
        client=CodingClient(raw,trace,RequestBudget(Limits()))
        with self.assertRaises(asyncio.CancelledError):await client.create(messages=[])
        self.assertEqual(client.budget.state['used'],0)

    async def test_late_model_response_rejected(self):
        a=Attempt();trace=CodingTrace();trace.attempt=a;entered=asyncio.Event();release=asyncio.Event()
        class Late(OfflineClient):
            async def create(self,**kw):entered.set();await release.wait();return await super().create(**kw)
        budget=RequestBudget(Limits());client=CodingClient(Late(),trace,budget)
        task=asyncio.create_task(client.create(messages=[]));await asyncio.wait_for(entered.wait(), 10);a.revoke('expired');release.set()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(budget.successes,0)

    async def test_approval_cancel_removes_reader_without_thread(self):
        master,slave=pty.openpty();a=Attempt();request=inspectable_command('macos_readonly','.',('python','-m','unittest'),10)
        try:
            with os.fdopen(os.dup(slave),'r') as stdin,os.fdopen(os.dup(slave),'w') as output,patch('sys.stdin',stdin),patch('asyncio.to_thread',side_effect=AssertionError('thread forbidden')):
                provider=AttemptApproval(a,output=output)
                task=asyncio.create_task(provider(request));await asyncio.sleep(0);task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
                self.assertFalse(provider.busy);os.write(master,b'yes\n')
                with self.assertRaises(asyncio.CancelledError):await provider(request)
        finally:os.close(master);os.close(slave)

    async def test_late_yes_or_old_nonce_cannot_approve_new_attempt(self):
        master,slave=pty.openpty();request=inspectable_command('macos_readonly','.',('python','-m','unittest'),10)
        try:
            with os.fdopen(os.dup(slave),'r') as stdin,os.fdopen(os.dup(slave),'w') as output,patch('sys.stdin',stdin):
                for answer in (b'yes\n',b'yes '+b'a'*32+b'\n'):
                    a=Attempt();task=asyncio.create_task(AttemptApproval(a,output=output)(request))
                    await asyncio.sleep(0);os.write(master,answer)
                    self.assertIs(await asyncio.wait_for(task,2),ApprovalDecision.DENY)
                    while select.select([master],[],[],0)[0]:os.read(master,65536)
        finally:os.close(master);os.close(slave)

    async def test_current_nonce_approves_only_one_command(self):
        master,slave=pty.openpty();a=Attempt();request=inspectable_command('macos_readonly','.',('python','-m','unittest'),10)
        try:
            with os.fdopen(os.dup(slave),'r') as stdin,os.fdopen(os.dup(slave),'w') as output,patch('sys.stdin',stdin),patch('mybot.evaluation.coding_approval.uuid.uuid4',return_value=N(hex='b'*32)):
                task=asyncio.create_task(AttemptApproval(a,output=output)(request));await asyncio.sleep(0)
                os.write(master,('yes '+'b'*32+'\n').encode());self.assertIs(await task,ApprovalDecision.APPROVE)
                self.assertTrue(a.command_approved)
        finally:os.close(master);os.close(slave)

    async def test_no_real_tty_denies(self):
        with patch('sys.stdin.isatty',return_value=False):
            self.assertIs(await AttemptApproval(Attempt(),output=io.StringIO())(N(mode='macos_readonly')),ApprovalDecision.DENY)

    async def test_normal_patch_real_seatbelt_test_and_judge(self):
        r=(await self.eval())['results'][0]
        self.assertEqual(r['agent_state'],'verified');self.assertTrue(r['judge']['verified_repair_success'])
        self.assertEqual(r['metrics']['real_test_runs'],1);self.assertEqual(r['judge']['journal_attribution_mismatch'],0)
        self.assertTrue(r['metrics']['tool_call_ids_paired'])
        self.assertEqual(r['lifecycle']['terminal_reason'],'completed')
        self.assertTrue(r['lifecycle']['tool_call_receipts'])
        self.assertTrue(all(e['status']=='returned' for e in r['lifecycle']['tool_call_receipts']))

    async def test_approval_cancel_preserves_committed_journal_evidence(self):
        entered=asyncio.Event()
        async def pending(request):entered.set();raise asyncio.CancelledError
        receipts=[]
        with self.assertRaises(asyncio.CancelledError):await self.eval(command_provider=pending,terminal_sink=receipts.append)
        r=receipts[0];self.assertTrue(entered.is_set());self.assertEqual(r['agent_state'],'cancelled')
        self.assertEqual(r['metrics']['committed_patches'],1);self.assertTrue(r['journal_evidence']['records'])
        self.assertEqual(r['lifecycle']['cancelled_tool_calls'][0]['name'],'run_command')
        self.assertFalse(r['agent_workflow_success']);self.assertFalse(r['judge']['verified_repair_success'])
        text=json.dumps(r);self.assertNotIn('class Cache:',text);self.assertNotIn('original_bytes',text)

    async def test_task_timeout_stops_following_repeat(self):
        calls=[]
        class Deadline(OfflineClient):
            async def create(self,**kw):calls.append(1);await asyncio.Event().wait()
        entered=asyncio.Event()
        original=Deadline.create
        async def create(client,**kw):entered.set();return await original(client,**kw)
        Deadline.create=create
        async def expire(attempt,coroutine,timeout):
            task=asyncio.create_task(coroutine);await asyncio.wait_for(entered.wait(), 10);attempt.revoke('task_timeout');task.cancel();await attempt.settle(task);raise TimeoutError
        with patch.object(Attempt,'run',expire):
            r=await self.eval(limits=Limits(max_cases=1,repeats=2),offline_client_factory=lambda public:Deadline())
        self.assertEqual(len(r['results']),1);self.assertEqual(len(calls),1)
        self.assertEqual(r['results'][0]['runtime_error'],'task_timeout')

    async def test_cancel_during_approved_command_is_uncertain(self):
        from mybot.tools import command_process
        async def interrupted(*a,**kw):raise asyncio.CancelledError
        with patch('mybot.tools.run_command.run_process',interrupted):
            receipts=[]
            with self.assertRaises(asyncio.CancelledError):await self.eval(terminal_sink=receipts.append)
        self.assertEqual(receipts[0]['agent_state'],'execution_uncertain')
        self.assertTrue(receipts[0]['lifecycle']['execution_uncertain'])

    async def test_cancel_during_patch_not_reported_completed(self):
        from mybot.tools.patch import ApplyPatchTool
        original=ApplyPatchTool.execute
        async def interrupted(tool,**kw):
            if kw.get('dry_run') is False:raise asyncio.CancelledError
            return await original(tool,**kw)
        receipts=[]
        with patch.object(ApplyPatchTool,'execute',interrupted):
            with self.assertRaises(asyncio.CancelledError):await self.eval(terminal_sink=receipts.append)
        r=receipts[0];self.assertEqual(r['agent_state'],'execution_uncertain')
        self.assertEqual(r['metrics']['committed_patches'],0)

    async def test_unknown_journal_changes_remain_mismatch(self):
        from mybot.agent.change_journal import ChangeJournal
        original=ChangeJournal.after_success
        def drop(journal,items):original(journal,items);journal.entries.clear()
        with patch.object(ChangeJournal,'after_success',drop):r=(await self.eval())['results'][0]
        self.assertGreater(r['judge']['journal_attribution_mismatch'],0)
        self.assertFalse(r['judge']['verified_repair_success'])

    async def test_historical_reports_read_only_and_all_attempts_count(self):
        from scripts.audit_phase25r import audit
        a=audit();self.assertEqual((a['denominator'],a['strict_successes'],a['judge_hidden_pass']),(36,15,31))
        self.assertEqual((a['cancelled_runs'],a['journal_mismatch_files']),(13,26))
        self.assertTrue(all(r['controller_command_attempts']==1 and r['completed_commands']==0 for r in a['cancellations']))

    async def test_model_freeze_reads_deepseek_without_editing_config(self):
        from mybot.config import GatewayConfig
        with patch.object(c,'freeze',ORIGINAL_FREEZE):
            frozen=c.freeze(GatewayConfig(provider='coco',model='deepseek-v4.1-flash',api_key=None,base_url=None))
        self.assertEqual((frozen['provider'],frozen['model']),('coco','deepseek-v4.1-flash'))

    async def test_revoked_tool_cannot_mutate_another_case(self):
        from mybot.tools import build_default_tool_registry
        from mybot.evaluation.coding_benchmark import configuration
        from mybot.agent import ContextBuilder
        from mybot.config import GatewayConfig
        case=load_benchmark().cases[0];root=create_repository(Path(self.tmp.name).resolve()/'agent',case.public)
        config=configuration(GatewayConfig(),root,Limits());tools=build_default_tool_registry(root,coding_enabled=True,patch_mode='write',command=config.coding_command)
        trace=CodingTrace();trace.attempt=Attempt();agent=BenchmarkAgent(None,config,tools,ContextBuilder(root),trace=trace)
        before=snapshot(root);trace.attempt.revoke('expired')
        with self.assertRaises(asyncio.CancelledError):await agent._execute('apply_patch','{}')
        self.assertEqual(snapshot(root),before)

    async def test_timeout_at_approval_keeps_exact_journal_ownership(self):
        entered=asyncio.Event()
        async def pending(request):entered.set();await asyncio.Event().wait()
        async def expire(attempt,coroutine,timeout):
            task=asyncio.create_task(coroutine);await asyncio.wait_for(entered.wait(), 10);attempt.revoke('task_timeout')
            task.cancel();await attempt.settle(task);raise TimeoutError
        with patch.object(Attempt,'run',expire):r=(await self.eval(command_provider=pending))['results'][0]
        self.assertEqual(r['runtime_error'],'task_timeout');self.assertEqual(r['agent_state'],'cancelled')
        self.assertEqual(r['judge']['journal_attribution_mismatch'],0)
        self.assertEqual(r['judge']['judge_state'],'hidden_pass')
        self.assertFalse(r['judge']['verified_repair_success']);self.assertFalse(r['agent_workflow_success'])
        self.assertTrue(any(e['status']=='cancelled' for e in r['lifecycle']['tool_call_receipts']))

    async def test_supervisor_repeated_interrupt_still_reaps_worker(self):
        from mybot.evaluation.coding_supervisor import supervise
        from unittest.mock import Mock
        child=Mock();child.wait.side_effect=[KeyboardInterrupt,KeyboardInterrupt,0]
        with patch('mybot.evaluation.coding_supervisor.subprocess.Popen',return_value=child):
            self.assertEqual(supervise(['worker']),124)
        child.kill.assert_called_once()

    async def test_supervisor_unconfirmed_kill_is_not_success(self):
        from mybot.evaluation.coding_supervisor import supervise
        from unittest.mock import Mock
        child=Mock();child.wait.side_effect=[subprocess.TimeoutExpired('w',1)]*3
        with patch('mybot.evaluation.coding_supervisor.subprocess.Popen',return_value=child):
            self.assertEqual(supervise(['worker']),125)

    async def test_before_fix_counterexamples_reproduced_from_source(self):
        # Only trusted repository functions, executed over disposable metadata.
        source=subprocess.check_output(['git','show','8acf9ab:mybot/evaluation/coding_campaign.py'],text=True)
        tree=ast.parse(source);ns=dict(c.__dict__)
        for name in ('strict_success','inventory'):
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            exec(compile(ast.Module(body=[node],type_ignores=[]),'<historical-function>','exec'),ns)
        r=self.report();r['results'][0]['runtime_error']='task_timeout'
        self.assertTrue(ns['strict_success'](r));self.assertFalse(c.strict_success(r))
        folder=await self.completed();p=folder/'finished.json';d=c.read(p);d['run_id']='wrong';p.write_bytes(c.encoded(d))
        self.assertEqual(ns['inventory'](self.root)[1][0]['status'],'completed')
        with self.assertRaises(ValueError):c.inventory(self.root)

    async def test_late_cleanup_cannot_mutate_published_case(self):
        from mybot.tools.patch import ApplyPatchTool
        entered=asyncio.Event();release=asyncio.Event();children=[];roots=[]
        original=ApplyPatchTool.execute
        async def delayed(tool,**kw):
            if kw.get('dry_run') is False:
                roots.append(tool.workspace);entered.set()
                try:await release.wait()
                except asyncio.CancelledError:await release.wait()
            return await original(tool,**kw)
        async def expire(attempt,coroutine,timeout):
            task=asyncio.create_task(coroutine);children.append(task)
            await asyncio.wait_for(entered.wait(), 10);attempt.revoke('task_timeout');task.cancel()
            await attempt.settle(task,timeout=0);raise TimeoutError
        with patch.object(ApplyPatchTool,'execute',delayed),patch.object(Attempt,'run',expire):
            report=await self.eval(limits=Limits(max_cases=1,repeats=2))
        saved=copy.deepcopy(report);self.assertEqual(len(report['results']),1)
        self.assertEqual(report['results'][0]['agent_state'],'execution_uncertain')
        self.assertTrue(roots[0].exists());self.assertTrue(report['results'][0]['lifecycle']['workspace_retained'])
        release.set();await asyncio.gather(*children,return_exceptions=True)
        self.assertEqual(report,saved)
        import shutil
        shutil.rmtree(roots[0].parents[1])

    async def test_provider_close_cancel_cannot_return_success(self):
        entered=asyncio.Event();release=asyncio.Event();raw=OfflineClient()
        async def close():entered.set();await release.wait()
        raw.close=close
        with patch('mybot.evaluation.coding_benchmark.live_client',AsyncMock(return_value=raw)):
            task=asyncio.create_task(self.eval(live=True,confirm_api_cost=True,offline_client_factory=None))
            await asyncio.wait_for(entered.wait(), 10);task.cancel();await asyncio.sleep(0);self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):await task

    async def test_provider_close_unknown_never_counts_success(self):
        release=asyncio.Event();raw=OfflineClient();pending=[]
        async def close():await release.wait()
        raw.close=close;original=Attempt.settle
        async def unsettled(attempt,task,timeout=5):
            pending.append(task);await original(attempt,task,timeout=0)
        roots=[]
        from mybot.evaluation import coding_benchmark as bench
        create=bench.create_repository
        def record(root,images):roots.append(root);return create(root,images)
        with patch.object(Attempt,'settle',unsettled),patch.object(bench,'create_repository',record),patch.object(bench,'live_client',AsyncMock(return_value=raw)):
            r=await self.eval(live=True,confirm_api_cost=True,offline_client_factory=None)
        self.assertEqual(r['results'][0]['agent_state'],'execution_uncertain')
        self.assertFalse(r['results'][0]['agent_workflow_success']);self.assertTrue(roots[0].exists())
        release.set();await asyncio.gather(*pending)
        import shutil
        shutil.rmtree(roots[0].parents[1])

    async def test_cancelled_provider_close_propagates_failure(self):
        from mybot.evaluation.coding_live import CodingEvaluationStop
        raw=OfflineClient()
        async def close():raise asyncio.CancelledError
        raw.close=close
        with patch('mybot.evaluation.coding_benchmark.live_client',AsyncMock(return_value=raw)):
            with self.assertRaises(CodingEvaluationStop):
                await self.eval(live=True,confirm_api_cost=True,offline_client_factory=None)

    async def test_controller_cancel_state_cannot_be_overwritten_by_verified(self):
        r=self.report();r['results'][0]['controller']['state']='cancelled'
        self.assertFalse(c.strict_success(r));self.assertTrue(c.pause_reason(r))

    async def test_blocked_completed_report_not_summarized_as_success(self):
        folder=await self.completed();c.write_new(folder/'blocked.json',{**c.read(folder/'started.json'),'category':'audit'})
        value=c.summary(self.root)
        self.assertEqual(value['strict_successes'],0)
        self.assertEqual(value['unresolved_execution_uncertain'],1)
        self.assertNotIn('success',value['rows'][0]['failure_categories'])

    async def test_controller_timeout_stops_direct_evaluation_repeat(self):
        from mybot.evaluation import coding_benchmark as bench
        r=(await self.eval())['results'][0]
        r.update(agent_state='budget_exhausted',agent_workflow_success=False)
        r['controller']['stop_reason']='max_task_seconds'
        with patch.object(bench,'run_task',AsyncMock(return_value=r)) as worker:
            report=await self.eval(limits=Limits(max_cases=1,repeats=2))
        self.assertEqual(len(report['results']),1);self.assertEqual(worker.await_count,1)

    async def test_external_cancel_never_reaches_final_verification(self):
        from scripts import evaluate_external_coding as external
        from mybot.evaluation.coding_fixtures import Image
        source=create_repository(Path(self.tmp.name).resolve()/'upstream',{'jsonpointer.py':Image(b'# public synthetic upstream\n',0o644)})
        subprocess.run(['git','remote','add','origin','https://github.com/stefankoegl/python-json-pointer.git'],cwd=source,check=True)
        before=snapshot(source);dest=Path(self.tmp.name)/'external-result';roots=[]
        create=external.create_repository
        def record(root,images):roots.append(root);return create(root,images)
        raw=OfflineClient();raw.close=AsyncMock()
        async def interrupted(agent,prompt):raise asyncio.CancelledError
        master,slave=pty.openpty()
        try:
            with os.fdopen(os.dup(slave),'r') as stdin,os.fdopen(os.dup(slave),'w') as output,patch('sys.stdin',stdin),contextlib.redirect_stdout(output),patch.object(external,'create_repository',record),patch.object(external,'load_config',return_value=GatewayConfig(context_token_budget={'input_limit':160000})),patch.object(external,'live_client',AsyncMock(return_value=raw)),patch.object(external,'verify',AsyncMock(return_value={'success':True})) as verify,patch.object(BenchmarkAgent,'handle_message',interrupted):
                with self.assertRaises(ValueError):await external.execute(source,dest)
            self.assertEqual(verify.await_count,2);raw.close.assert_awaited_once()
            self.assertTrue((dest/'terminal.json').exists());self.assertFalse((dest/'finished.json').exists())
            self.assertFalse((dest/'raw.json').exists());self.assertEqual(snapshot(source),before)
        finally:
            os.close(master);os.close(slave)
            import shutil
            for root in roots:
                if root.parent.exists():shutil.rmtree(root.parent)

    async def test_call_receipt_does_not_retain_unknown_model_text(self):
        attempt=Attempt();trace=CodingTrace();trace.attempt=attempt
        response=await OfflineClient().create()
        response.choices[0].message.tool_calls=[N(id='opaque-id',function=N(name='PRIVATE_MODEL_ARGUMENT',arguments='{}'))]
        raw=N(chat=N(completions=N(create=AsyncMock(return_value=response))))
        await CodingClient(raw,trace,RequestBudget(Limits())).create(messages=[])
        self.assertNotIn('PRIVATE_MODEL_ARGUMENT',json.dumps(attempt.metadata()))
        self.assertEqual(attempt.metadata()['tool_call_receipts'][0]['name'],'<unknown>')


def check_coding_reliability():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReliabilityChecks)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_coding_reliability()
