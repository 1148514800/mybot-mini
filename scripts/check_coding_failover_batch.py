"""Offline batch durability, accounting, injection and SDK MockTransport checks."""
import asyncio
import contextlib
import copy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import AsyncMock,patch
import httpx
from openai import AsyncOpenAI
from mybot.config import GatewayConfig
from mybot.evaluation import coding_failover_batch as batch
from mybot.evaluation import coding_failover_campaign as v4
from mybot.evaluation import coding_campaign as meta
from mybot.evaluation.coding_failover import FailoverCodingClient
from mybot.evaluation.coding_live import Limits,RequestBudget
from mybot.evaluation.coding_metrics import CodingTrace
from mybot.evaluation.coding_lifecycle import Attempt
from mybot.agent.coding_controller import CodingTaskController,AutonomySettings
from mybot.tools import build_default_tool_registry
from scripts.coding_benchmark_demo import DemoClient


class BatchChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.project=Path(self.tmp.name)
        self.root=self.project/'runs/coding_failover/batch'
        self.guard=patch.object(batch,'PROJECT_DIR',self.project);self.guard.start();self.addCleanup(self.guard.stop)
    async def fake(self,folder,**kw):
        folder=Path(folder);folder.mkdir();m=batch.read_manifest(self.root);row=next(x for x in m['plan'] if x['slot']==folder.name)
        ident=dict(campaign_id=__import__('uuid').uuid4().hex,run_id=row['case_id'],attempt_id=__import__('uuid').uuid4().hex,config_sha256=meta.sha(m['frozen'][row['slot']]))
        f=m['frozen'][row['slot']]
        meta.write_new(folder/'manifest.json',dict(version=4,kind='provider_failover_harness',**ident,frozen=f))
        meta.write_new(folder/'started.json',ident)
        q=dict(attempt_id=ident['attempt_id'],case_id=row['case_id'],physical_request=1,provider='coco',model=f['providers'][0]['model'],status='started',http_dispatch_count=0,
               synthetic_injected=row['fault_mode']!='none',phase='injected_connection' if row['fault_mode']!='none' else 'sdk_create',error_category=None)
        kw['request_audit'].before(q);q['status']='error' if q['synthetic_injected'] else 'returned';kw['request_audit'].after(q)
        r=dict(case_id=row['case_id'],agent_state='budget_exhausted',agent_workflow_success=False,runtime_error=None,failure='model_request_budget',
            metrics=dict(tool_call_ids_paired=True,**{k:0 for k in ('sandbox_failures','execution_uncertain_count','approval_denials','workspace_escape_attempts','protocol_false_verified_count','command_attempts')}),
            controller=dict(stop_reason='max_model_requests',command_attempts=0),journal_evidence={'uncertain':False},
            lifecycle=dict(**ident,cleanup_confirmed=True,execution_uncertain=False,approval_cancelled=False,terminal_reason='completed'),
            judge=dict(index_changed=False,protected_file_changes=0,unrelated_file_changes=0,journal_attribution_mismatch=0,judge_state='hidden_fail'),
            provider_execution={'requests':[q]})
        raw=dict(results=[r],execution_identity=ident,mybot_commit=f['benchmark_harness_commit'],benchmark_sha256=f['benchmark_sha256'],grading_code_sha256=f['grading_code_sha256'],dependency_lock_sha256=f['dependency_lock_sha256'],limits=f['limits'],mode='offline',provider_mode='failover',provider_label='mixed',case_ids=[row['case_id']],physical_model_requests=1,fault_mode=row['fault_mode'])
        meta.write_new(folder/'terminal.json',dict(**ident,evidence=r));meta.write_new(folder/'raw.json',raw)
        meta.write_new(folder/'finished.json',dict(**ident,report_sha256=meta.file_sha(folder/'raw.json'),terminal_sha256=meta.file_sha(folder/'terminal.json')))
        meta.write_new(folder/'blocked.json',dict(**ident,category='not_strictly_verified'))
        return v4.inventory(folder),raw
    async def complete(self):
        with patch.object(v4,'run',self.fake),contextlib.redirect_stdout(io.StringIO()):return await batch.run(self.root)
    def test_plan_fixed_13_and_caps(self):
        rows=batch.plan();self.assertEqual(len(rows),13);self.assertEqual(sum(x['limits']['max_requests'] for x in rows),204)
        self.assertEqual(sum(x['limits']['max_requests'] for x in rows[:12]),192);self.assertEqual(len(set(x['slot'] for x in rows)),13)
    def test_plan_timeouts_not_enlarged(self):
        for x in batch.plan():self.assertEqual([x['limits'][k] for k in ('request_timeout','task_timeout','total_timeout','max_output_tokens')],[90,480,600,2048])
    def test_atomic_no_overwrite(self):
        p=self.project/'a';batch.atomic_new(p,{'x':1})
        with self.assertRaises(FileExistsError):batch.atomic_new(p,{'x':2})
        self.assertEqual(meta.read(p),{'x':1})
    def test_atomic_publish_failure_no_partial(self):
        with patch.object(batch.os,'link',side_effect=OSError):
            with self.assertRaises(OSError):batch.atomic_new(self.project/'x',{'safe':1})
        self.assertFalse((self.project/'x').exists());self.assertFalse(list(self.project.glob('.pending-*')))
    async def test_complete_normal_task_fails_continue_all13(self):
        s=await self.complete();self.assertEqual((s['completed'],s['strict_successes'],s['physical_requests']),(13,0,13));self.assertEqual(s['status'],'completed')
        self.assertEqual(len(set(x['attempt_id'] for x in s['rows'])),13)
    async def test_no_resume_completed(self):
        await self.complete()
        with self.assertRaises(ValueError):await batch.run(self.root)
    async def test_crash_after_intent_no_replay(self):
        with patch.object(v4,'run',AsyncMock(side_effect=RuntimeError)),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):await batch.run(self.root)
        s=batch.status(self.root);self.assertEqual(s['rows'][0]['status'],'uncertain');self.assertEqual(s['completed'],0)
        with self.assertRaises(ValueError):await batch.run(self.root)
    async def test_cancel_persists_stop(self):
        with patch.object(v4,'run',AsyncMock(side_effect=asyncio.CancelledError)),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(asyncio.CancelledError):await batch.run(self.root)
        self.assertTrue((self.root/'stopped.json').exists());self.assertFalse((self.root/'finished.json').exists())
    async def test_changed_plan_detected(self):
        await self.complete();p=self.root/'batch.json';m=meta.read(p);m['plan'][0]['limits']['max_requests']=13;p.write_text(json.dumps(m))
        with self.assertRaises(ValueError):batch.status(self.root)
    async def test_damaged_raw_detected(self):
        await self.complete();p=next((self.root/'attempts').glob('*/raw.json'));p.write_text('{}')
        with self.assertRaises(ValueError):batch.status(self.root)
    async def test_request_identity_tamper_detected(self):
        await self.complete();p=next((self.root/'requests').glob('*-started.json'));x=meta.read(p);x['attempt_id']='other';p.write_text(json.dumps(x))
        with self.assertRaises(ValueError):batch.status(self.root)
    async def test_unfinished_physical_request_stops(self):
        await self.complete();next((self.root/'requests').glob('*-finished.json')).unlink()
        with self.assertRaises(ValueError):batch.status(self.root)
    async def test_orphan_outcome_rejected(self):
        await self.complete();meta.write_new(self.root/'requests/9999-finished.json',{})
        with self.assertRaises(ValueError):batch.status(self.root)
    async def test_strict_failure_not_counted_hidden_pass(self):
        s=await self.complete();self.assertEqual(s['strict_successes'],0);self.assertTrue(all(x['task']=='FAIL' and x['infra']=='PASS' for x in s['rows']))
    async def test_unsafe_cleanup_stops_next_case(self):
        real=batch.audit_case
        def unsafe(*a):return dict(real(*a),infra='BLOCKED')
        with patch.object(v4,'run',self.fake),patch.object(batch,'audit_case',unsafe),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):await batch.run(self.root)
        self.assertEqual(len(list((self.root/'attempts').iterdir())),1)
    async def test_before_dispatch_cap_prevents_extra_attempt(self):
        await self.complete();m=batch.read_manifest(self.root);row=m['plan'][0];identity=meta.read(self.root/'attempts'/row['slot']/'manifest.json')
        q=dict(attempt_id=identity['attempt_id'],physical_request=13,case_id=row['case_id'])
        with self.assertRaises(ValueError):batch.RequestLedger(self.root,m,row).before(q)
        self.assertEqual(batch.status(self.root)['physical_requests'],13)
    async def test_global_204_precheck_no_reservation(self):
        await self.complete();m=batch.read_manifest(self.root);row=m['plan'][0]
        before=len(list((self.root/'requests').iterdir()))
        with patch.object(batch,'ledger',return_value=[{}]*204):
            with self.assertRaisesRegex(ValueError,'batch_budget_exhausted'):
                batch.RequestLedger(self.root,m,row).before({})
        self.assertEqual(len(list((self.root/'requests').iterdir())),before)
    async def test_request_ledger_refuses_second_unsettled_dispatch(self):
        await self.complete();m=batch.read_manifest(self.root);r=m['plan'][0]
        ledger=batch.RequestLedger(self.root,m,r);ledger.pending=Path('unsettled')
        with self.assertRaisesRegex(ValueError,'concurrent_model_dispatch'):ledger.before({})
    async def test_fault_mode_invalid_rejected_before_attempt(self):
        folder=self.root/'bad'
        with self.assertRaises(ValueError):await v4.run(folder,provider_mode='failover',fault_mode='all_requests')
        self.assertFalse(folder.exists())
    async def test_ledger_failure_prevents_sdk_and_counter(self):
        raw=N(chat=N(completions=N(create=AsyncMock())),close=AsyncMock())
        c=GatewayConfig(provider='coco',model='deepseek-v4.1-flash',workspace=self.project,skills_enabled=False,session_persist=False)
        budget=RequestBudget(Limits(max_requests=2));audit=N(before=lambda r:(_ for _ in ()).throw(OSError('synthetic ledger IO')),after=lambda r:None)
        adapter=FailoverCodingClient((c,replace(c,provider='coco2',model='glm-5.3-flash')),CodingTrace(),budget,Attempt(),'synthetic',lambda c:raw,request_audit=audit)
        try:
            with self.assertRaises(Exception):await adapter.create(model=c.model,messages=[{'role':'user','content':'synthetic'}])
            raw.chat.completions.create.assert_not_awaited();self.assertEqual(budget.state['used'],0)
        finally:await adapter.close()
    async def test_bad_global_cap_no_directory(self):
        with self.assertRaises(ValueError):await batch.run(self.root,max_physical_requests=205)
        self.assertFalse(self.root.exists())
    async def test_history_namespace_rejected(self):
        with self.assertRaises(ValueError):await batch.run(self.project/'runs/coding_campaign/old')
    async def test_credentials_not_in_evidence(self):
        await self.complete()
        for p in self.root.rglob('*.json'):
            self.assertNotIn('api_key',p.read_text());self.assertNotIn('Authorization',p.read_text())
    async def test_controlled_sdk_mocktransport_no_primary_http_sticky_own_key(self):
        seen=[];clients=[]
        def factory(cfg):
            async def handler(request):
                seen.append((cfg.provider,str(request.headers.get('authorization')),json.loads(request.content)['model']))
                return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':0,'model':cfg.model,'choices':[{'index':0,'message':{'role':'assistant','content':'done'},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
            raw=AsyncOpenAI(api_key=cfg.api_key,base_url=cfg.base_url,max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)));clients.append(raw);return raw
        c=GatewayConfig(provider='coco',model='deepseek-v4.1-flash',api_key='synthetic-primary',base_url='https://offline.invalid/v1',workspace=self.project,skills_enabled=False,session_persist=False)
        backup=replace(c,provider='coco2',model='glm-5.3-flash',api_key='synthetic-backup');b=RequestBudget(Limits(max_requests=3));attempt=Attempt();controller=CodingTaskController(AutonomySettings(max_model_requests=3),build_default_tool_registry(self.project))
        a=FailoverCodingClient((c,backup),CodingTrace(),b,attempt,'case',factory,fault_mode='primary_connection_once');a.controller=lambda:controller
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(controller.before_request(None));await a.create(model=c.model,messages=[{'role':'user','content':'synthetic'}])
                self.assertTrue(controller.before_request(None));await a.create(model=c.model,messages=[{'role':'user','content':'synthetic'}])
            self.assertEqual([x[0] for x in seen],['coco2','coco2']);self.assertTrue(all(x[1]=='Bearer synthetic-backup' and x[2]=='glm-5.3-flash' for x in seen))
            self.assertEqual((a.summary()['physical_model_requests'],a.summary()['http_model_requests'],controller.model_requests,b.state['used']),(3,2,3,3))
            self.assertEqual(a.summary()['synthetic_injected_attempts'],1);self.assertFalse(controller.before_request(None))
        finally:await a.close()
    async def test_controlled_mocktransport_original_loop_patch_test_judge(self):
        # Actual OpenAI SDK over in-memory HTTP. Real original tools, no external model.
        from mybot.evaluation.coding_failover import evaluate
        sent=[];demo=DemoClient()
        def build(cfg):
            async def handler(request):
                sent.append(cfg.provider);kw=json.loads(request.content);msg=(await demo.create(**kw)).choices[0].message
                calls=[{'id':x.id,'type':'function','function':{'name':x.function.name,'arguments':x.function.arguments}} for x in (msg.tool_calls or [])]
                message={'role':'assistant','content':msg.content}
                if calls:message['tool_calls']=calls
                return httpx.Response(200,json={'id':'synthetic','object':'chat.completion','created':0,'model':kw['model'],'choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if calls else 'stop'}]})
            return AsyncOpenAI(api_key='synthetic',base_url='https://offline.invalid/v1',http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),max_retries=0)
        with patch('mybot.evaluation.coding_failover.build_client',build),contextlib.redirect_stdout(io.StringIO()):
            # live=False forbids real model usage, while supplied SDK factory remains MockTransport.
            r=await evaluate(provider_mode='failover',fault_mode='primary_connection_once',limits=Limits(max_cases=1,max_requests=8,max_model_requests_per_case=8),case_ids=['cache-ttl-001'],offline_provider_factory=lambda runtime,p:build(N(provider=p)))
        x=r['results'][0];self.assertEqual(x['agent_state'],'verified',json.dumps(x));self.assertEqual(x['judge']['judge_state'],'hidden_pass')
        self.assertEqual(x['metrics']['committed_patches'],1);self.assertEqual(x['metrics']['real_test_runs'],1);self.assertTrue(x['metrics']['tool_call_ids_paired']);self.assertTrue(all(p=='coco2' for p in sent))
        self.assertEqual(r['physical_model_requests'],r['http_model_requests']+1);self.assertFalse(r['ability_score'])


def check_coding_failover_batch():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(BatchChecks))
    if not result.wasSuccessful():raise SystemExit(1)
if __name__=='__main__':check_coding_failover_batch()
