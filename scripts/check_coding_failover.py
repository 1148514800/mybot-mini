"""Offline strict Harness integration, SDK MockTransport and original agent tests."""
import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import AsyncMock,Mock,patch

import httpx
from openai import AsyncOpenAI,APIConnectionError,APITimeoutError,APIStatusError
from mybot.config import GatewayConfig
from mybot.evaluation.coding_live import Limits,RequestBudget,CodingEvaluationStop
from mybot.evaluation.coding_lifecycle import Attempt
from mybot.evaluation.coding_metrics import CodingTrace
from mybot.evaluation.coding_failover import FailoverCodingClient,evaluate,settings,recoverable
from mybot.evaluation.coding_failover_campaign import run,inventory
from mybot.agent.coding_controller import CodingTaskController,AutonomySettings
from mybot.tools import build_default_tool_registry
from mybot.provider_failover import FallbackBudgetExceeded
from scripts.check_session import response,call
from scripts.coding_benchmark_demo import DemoClient


def connection():return APIConnectionError(request=httpx.Request('POST','https://offline.invalid'))
def status(code):return APIStatusError('PRIVATE_SERVER_ERROR',response=httpx.Response(code,request=httpx.Request('POST','https://offline.invalid')),body=None)
def client(effects):return N(chat=N(completions=N(create=AsyncMock(side_effect=effects))),close=AsyncMock())


class CodingFailoverChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.config=GatewayConfig(provider='coco',model='deepseek-v4.1-flash',api_key='PRIVATE_PRIMARY_KEY',
            base_url='https://offline.invalid/v1',
            workspace=self.root,skills_enabled=False,mcp_enabled=False,context_enabled=False,session_persist=False,
            request_timeout_seconds=2)
        self.secondary=replace(self.config,provider='coco2',model='glm-5.3-flash',api_key='PRIVATE_BACKUP_KEY')
        self.limits=Limits(max_cases=1,max_requests=12,max_model_requests_per_case=12)

    def adapter(self,primary=None,backup=None,*,global_max=12,controller_max=12):
        self.primary=primary or client([connection()]);self.backup=backup or client([response('ok')])
        self.budget=RequestBudget(replace(self.limits,max_requests=global_max))
        self.attempt=Attempt();self.trace=CodingTrace()
        self.controller=CodingTaskController(AutonomySettings(max_model_requests=controller_max),build_default_tool_registry(self.root))
        self.factory=Mock(side_effect=lambda cfg:self.primary if cfg.provider=='coco' else self.backup)
        self.a=FailoverCodingClient((self.config,self.secondary),self.trace,self.budget,self.attempt,'synthetic-case',self.factory)
        self.a.controller=lambda:self.controller
        self.addAsyncCleanup(self.a.close)
        return self.a

    async def request(self,a=None):
        a=a or self.a
        self.assertTrue(self.controller.before_request(None))
        with contextlib.redirect_stdout(io.StringIO()):
            return await a.create(model=self.config.model,messages=[{'role':'user','content':'offline task'}],tools=None)

    async def test_single_does_not_build_backup_or_change_report_schema(self):
        with patch('mybot.evaluation.coding_failover.settings',side_effect=AssertionError('single parsed backup')),patch('mybot.evaluation.coding_failover.build_client',side_effect=AssertionError('network')):
            r=await evaluate(limits=self.limits,case_ids=['cache-ttl-001'])
        self.assertEqual(r['report_type'],'coding_benchmark');self.assertNotIn('provider_mode',r)
        self.assertNotIn('provider_execution',r['results'][0]);self.assertEqual(r['model_name'],'offline-script')

    async def test_primary_success_never_creates_backup(self):
        self.adapter(client([response('ok')]));await self.request()
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.summary()['physical_model_requests'],1)

    async def test_connection_fallback_and_physical_counts(self):
        self.adapter();await self.request();s=self.a.summary()
        self.assertEqual((s['logical_model_requests'],s['physical_model_requests']),(1,2))
        self.assertEqual(s['physical_requests_by_provider'],{'coco':1,'coco2':1})
        self.assertEqual(self.controller.model_requests,2);self.assertEqual(self.budget.state['used'],2)
        self.assertEqual((s['fallback_attempts'],s['fallback_successes'],s['fallback_failures']),(1,1,0))

    async def test_timeout_can_recover(self):
        self.adapter(client([APITimeoutError(request=httpx.Request('POST','https://offline.invalid'))]))
        await self.request();self.assertEqual(self.a.records[0]['error_category'],'request_timeout')
        self.assertEqual(self.backup.chat.completions.create.await_count,1)

    async def test_429_recovers(self):
        self.adapter(client([status(429)]));await self.request()
        self.assertEqual(self.a.records[0]['http_status'],429)

    async def test_recoverable_5xx(self):
        for code in (500,502,503,504):
            self.adapter(client([status(code)]));await self.request()
            self.assertEqual(self.a.records[0]['error_category'],'server_error')
            self.assertEqual(self.backup.chat.completions.create.await_count,1)

    async def test_400_401_403_422_501_not_hidden_by_fallback(self):
        for code,category in [(400,'parameter_error'),(401,'authentication_error'),(403,'permission_error'),(422,'http_error'),(501,'server_error')]:
            self.adapter(client([status(code)]))
            with self.assertRaises(CodingEvaluationStop):await self.request()
            self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.records[0]['error_category'],category)

    async def test_local_exception_not_recoverable(self):
        self.adapter(client([ValueError('PRIVATE_EXCEPTION_AND_KEY')]))
        with self.assertRaises(CodingEvaluationStop):await self.request()
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.records[0]['error_category'],'local_programming_error')

    async def test_sdk_wrapped_local_exception_not_masked(self):
        error=connection();error.__cause__=ValueError('PRIVATE_LOCAL_CAUSE')
        self.adapter(client([error]))
        with self.assertRaises(CodingEvaluationStop):await self.request()
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.records[0]['error_category'],'local_programming_error')

    async def test_bad_tool_protocol_does_not_fallback(self):
        invalid=response(calls=[call('same'),call('same')])
        self.adapter(client([invalid]))
        with self.assertRaises(CodingEvaluationStop):await self.request()
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.records[-1]['status'],'protocol_rejected')

    async def test_bad_backup_protocol_is_not_recovery_success(self):
        self.adapter(backup=client([response(calls=[call('same'),call('same')])]))
        with self.assertRaises(CodingEvaluationStop):await self.request()
        s=self.a.summary();self.assertEqual((s['fallback_successes'],s['fallback_failures']),(0,1))

    async def test_transport_contract_error_not_masked_as_network_recovery(self):
        async def handler(request):return httpx.Response(307,headers={'location':'https://offline.invalid/other'})
        raw=AsyncOpenAI(api_key='synthetic',base_url='https://offline.invalid/v1',max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler),follow_redirects=True))
        self.adapter(raw)
        with self.assertRaises(CodingEvaluationStop):await self.request()
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.records[0]['http_dispatch_count'],1)
        self.assertEqual(self.a.records[0]['error_category'],'protocol_error')

    async def test_global_budget_gate_precedes_backup_sdk(self):
        self.adapter(global_max=1)
        with self.assertRaises(FallbackBudgetExceeded):await self.request()
        self.assertEqual(self.budget.state['used'],1);self.assertEqual(self.controller.model_requests,1)
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.stops[0]['reason'],'model_request_budget')

    async def test_controller_budget_gate_precedes_backup_sdk(self):
        self.adapter(controller_max=1)
        with self.assertRaises(FallbackBudgetExceeded):await self.request()
        self.assertEqual(self.controller.state,'budget_exhausted');self.assertEqual(self.factory.call_count,1)
        self.assertEqual(self.budget.state['used'],1)

    async def test_sticky_same_attempt(self):
        self.adapter(backup=client([response('ok'),response('next')]))
        await self.request();await self.request()
        self.assertEqual(self.primary.chat.completions.create.await_count,1)
        self.assertEqual(self.a.summary()['fallback_attempts'],1)
        self.assertEqual(self.controller.model_requests,3)

    async def test_new_attempt_starts_primary_with_unique_identity(self):
        self.adapter();await self.request();old=self.attempt.identity['attempt_id']
        self.adapter(client([response('primary')]));await self.request()
        self.assertNotEqual(old,self.attempt.identity['attempt_id']);self.assertEqual(self.a.gateway.active_provider,'coco')

    async def test_cancelled_error_never_falls_back(self):
        self.adapter(client([asyncio.CancelledError()]))
        with self.assertRaises(asyncio.CancelledError):await self.request()
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.a.records[0]['status'],'cancelled')

    async def test_cancel_waiting_request_no_late_backup(self):
        started=asyncio.Event();hold=asyncio.Event()
        async def pending(**kwargs):started.set();await hold.wait()
        raw=client([]);raw.chat.completions.create.side_effect=pending;self.adapter(raw)
        task=asyncio.create_task(self.request());await started.wait();self.attempt.revoke('task_cancelled');task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(self.factory.call_count,1)

    async def test_revoked_before_create_does_not_dispatch(self):
        self.adapter();self.attempt.revoke('task_timeout')
        with self.assertRaises(asyncio.CancelledError):await self.a.create(messages=[],model=self.config.model)
        self.assertEqual(self.budget.state['used'],0);self.primary.chat.completions.create.assert_not_awaited()

    async def test_task_deadline_blocks_fallback(self):
        self.adapter()
        async def expire(**kwargs):self.controller.started-=1000;raise connection()
        self.primary.chat.completions.create.side_effect=expire
        with self.assertRaises(FallbackBudgetExceeded):await self.request()
        self.assertEqual(self.factory.call_count,1);self.assertEqual(self.controller.stop_reason,'max_task_seconds')

    async def test_global_deadline_blocks_fallback(self):
        self.adapter()
        async def expire(**kwargs):self.budget.deadline=0;raise connection()
        self.primary.chat.completions.create.side_effect=expire
        with self.assertRaises(CodingEvaluationStop):await self.request()
        self.assertEqual(self.factory.call_count,1)

    async def test_late_response_after_revoke_is_not_success(self):
        self.adapter()
        async def late(**kwargs):self.attempt.revoke('task_cancelled');return response('late')
        self.primary.chat.completions.create.side_effect=late
        with self.assertRaises(asyncio.CancelledError):await self.request()
        self.assertNotEqual(self.a.records[0]['status'],'returned');self.assertEqual(self.factory.call_count,1)

    async def test_backup_fails_once(self):
        self.adapter(backup=client([connection()]))
        with self.assertRaises(CodingEvaluationStop):await self.request()
        self.assertEqual(self.a.summary()['fallback_failures'],1)
        self.assertEqual(self.backup.chat.completions.create.await_count,1)

    async def test_cleanup_attempts_both_clients(self):
        self.adapter();await self.request();self.primary.close.side_effect=RuntimeError('PRIVATE_CLOSE')
        with self.assertRaises(RuntimeError):await self.a.close()
        self.assertEqual(self.backup.close.await_count,1)
        self.primary.close.side_effect=None

    async def test_usage_unknown_and_no_credential_or_error_body_in_evidence(self):
        self.adapter(client([ValueError('PRIVATE_PRIMARY_KEY PRIVATE_EXCEPTION')]))
        with self.assertRaises(CodingEvaluationStop):await self.request()
        text=json.dumps(self.a.summary())
        for value in ('PRIVATE_PRIMARY_KEY','PRIVATE_BACKUP_KEY','PRIVATE_EXCEPTION','offline.invalid','offline task'):
            self.assertNotIn(value,text)
        self.assertIsNone(self.a.records[0]['usage']['total_tokens']);self.assertIsNone(self.a.summary()['http_model_requests'])

    async def test_known_usage_is_per_physical_and_missing_not_zero(self):
        good=response('ok');good.usage=N(prompt_tokens=3,completion_tokens=2,total_tokens=5,prompt_tokens_details=None)
        self.adapter(client([good]));await self.request()
        self.assertEqual(self.a.metric_fields()['total_tokens'],5)

    async def test_real_sdk_mock_transport_own_model_key_context_and_no_retries(self):
        seen=[]
        async def handler(request):
            body=json.loads(request.content);seen.append((request.headers['authorization'],body))
            if len(seen)==1:return httpx.Response(503,json={'error':{'message':'synthetic','type':'server_error'}})
            return httpx.Response(200,json={'id':'x','object':'chat.completion','created':1,'model':'glm-5.3-flash',
                'choices':[{'index':0,'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}]})
        def sdk(key):return AsyncOpenAI(api_key=key,base_url='https://offline.invalid/v1',max_retries=2,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        self.adapter(sdk('synthetic-primary'),sdk('synthetic-backup'));await self.request()
        self.assertEqual(len(seen),2);self.assertEqual([r[0] for r in seen],['Bearer synthetic-primary','Bearer synthetic-backup'])
        self.assertEqual([r[1]['model'] for r in seen],['deepseek-v4.1-flash','glm-5.3-flash'])
        self.assertEqual(seen[0][1]['messages'],seen[1][1]['messages']);self.assertEqual(seen[0][1]['tools'],seen[1][1]['tools'])
        self.assertEqual(self.a.summary()['http_model_requests'],2)

    async def test_mixed_unscoped_prices_rejected(self):
        with self.assertRaises(ValueError):await evaluate(provider_mode='failover',prices={'currency':'USD'})

    async def test_live_overrides_block_before_client_creation(self):
        with patch('mybot.evaluation.coding_failover.build_client') as build:
            with self.assertRaises(ValueError):await evaluate(provider_mode='failover',live=True,confirm_api_cost=True,offline_provider_factory=lambda *x:None)
            build.assert_not_called()

    async def test_single_live_requires_cost_and_tty(self):
        with patch('mybot.evaluation.coding_live.build_client') as build:
            with self.assertRaises(ValueError):await evaluate(provider_mode='single',live=True)
            build.assert_not_called()

    async def full_task(self,primary_reads=False,global_max=12,controller_max=12,close_error=False):
        created=[]
        class Script(DemoClient):
            def __init__(self,p):super().__init__();self.p=p;self.close=AsyncMock(side_effect=RuntimeError('PRIVATE_CLOSE') if close_error and p=='coco' else None)
            async def create(self,**kwargs):
                if self.p=='coco' and (not primary_reads or self.step):raise connection()
                reply=await super().create(**kwargs)
                for tc in reply.choices[0].message.tool_calls or []:tc.id=self.p+'-'+tc.id
                return reply
        def factory(runtime,p):
            raw=Script(p);created.append((p,raw));return raw
        with patch('mybot.evaluation.coding_failover.build_client',side_effect=AssertionError('No paid API')):
            r=await evaluate(provider_mode='failover',limits=replace(self.limits,max_requests=global_max,max_model_requests_per_case=controller_max),
                case_ids=['cache-ttl-001'],offline_provider_factory=factory)
        return r,created

    async def test_original_agent_patch_real_test_judge_complete_after_fallback(self):
        r,clients=await self.full_task();v=r['results'][0]
        self.assertEqual((v['agent_state'],v['judge']['judge_state']),('verified','hidden_pass'))
        self.assertTrue(v['agent_workflow_success']);self.assertTrue(v['judge']['verified_repair_success'])
        self.assertEqual((r['logical_model_requests'],r['physical_model_requests']),(5,6))
        self.assertEqual(v['controller']['model_requests'],6)
        self.assertEqual((v['metrics']['committed_patches'],v['metrics']['real_test_runs']),(1,1))
        self.assertEqual(v['controller']['current_revision'],v['controller']['last_verified_revision'])
        self.assertTrue(v['metrics']['tool_call_ids_paired']);self.assertFalse(v['journal_evidence']['uncertain'])
        self.assertEqual(v['judge']['journal_attribution_mismatch'],0)
        self.assertTrue(all(raw.close.await_count==1 for _,raw in clients))

    async def test_completed_read_not_replayed_and_ids_pair(self):
        r,_=await self.full_task(primary_reads=True);v=r['results'][0]
        self.assertEqual(v['metrics']['read_calls'],1);self.assertEqual(v['metrics']['committed_patches'],1)
        self.assertTrue(v['metrics']['tool_call_ids_paired']);self.assertEqual(v['agent_state'],'verified')

    async def test_original_loop_global_limit_no_false_verified(self):
        r,created=await self.full_task(global_max=1)
        self.assertEqual(r['physical_model_requests'],1);self.assertEqual(len(created),1)
        self.assertNotEqual(r['results'][0]['agent_state'],'verified')
        self.assertEqual(r['results'][0]['controller']['model_requests'],1)

    async def test_original_loop_controller_limit_no_false_verified(self):
        r,created=await self.full_task(controller_max=1)
        self.assertEqual(r['physical_model_requests'],1);self.assertEqual(len(created),1)
        self.assertEqual(r['results'][0]['agent_state'],'budget_exhausted')

    async def test_provider_close_failure_marks_uncertain(self):
        r,_=await self.full_task(close_error=True);v=r['results'][0]
        self.assertEqual(v['agent_state'],'execution_uncertain');self.assertFalse(v['agent_workflow_success'])
        self.assertTrue(v['lifecycle']['execution_uncertain'])

    async def test_patch_without_current_revision_test_never_verified(self):
        from mybot.evaluation.coding_agent import decode_result
        class Untested(DemoClient):
            async def create(self,**kwargs):
                previous=next((m for m in reversed(kwargs['messages']) if m['role']=='tool'),None)
                if previous and decode_result(previous['content'])[1].get('applied'):return response('done')
                return await super().create(**kwargs)
        r=await evaluate(provider_mode='failover',limits=self.limits,case_ids=['cache-ttl-001'],
            offline_provider_factory=lambda runtime,p:client([connection()]) if p=='coco' else Untested())
        v=r['results'][0];self.assertEqual(v['controller']['current_revision'],1)
        self.assertEqual(v['metrics']['real_test_runs'],0);self.assertNotEqual(v['agent_state'],'verified')

    async def test_cancelled_campaign_preserves_terminal_and_does_not_replay(self):
        started=asyncio.Event();hold=asyncio.Event();created=[]
        async def wait(**kwargs):started.set();await hold.wait()
        def factory(runtime,p):
            raw=client([]);raw.chat.completions.create.side_effect=wait;created.append((p,raw));return raw
        root=self.root/'cancelled'
        task=asyncio.create_task(run(root,provider_mode='failover',limits=self.limits,offline_provider_factory=factory))
        await started.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual([p for p,_ in created],['coco'])
        self.assertEqual(created[0][1].close.await_count,1)
        self.assertTrue((root/'terminal.json').exists());self.assertTrue((root/'blocked.json').exists())
        self.assertFalse((root/'finished.json').exists())
        self.assertEqual(inventory(root)['status'],'blocked')
        with self.assertRaises(ValueError):await run(root,provider_mode='failover')

    async def test_finished_without_terminal_rejected(self):
        root=self.root/'missing';await run(root,provider_mode='failover',limits=self.limits)
        (root/'terminal.json').unlink()
        with self.assertRaises(ValueError):inventory(root)

    async def test_report_frozen_provenance_checked_beyond_file_hash(self):
        from mybot.evaluation.coding_campaign import file_sha
        root=self.root/'provenance';await run(root,provider_mode='failover',limits=self.limits)
        p=root/'raw.json';raw=json.loads(p.read_text());raw['dependency_lock_sha256']='wrong';p.write_text(json.dumps(raw))
        p=root/'finished.json';end=json.loads(p.read_text());end['report_sha256']=file_sha(root/'raw.json');p.write_text(json.dumps(end))
        with self.assertRaises(ValueError):inventory(root)

    async def test_physical_request_model_checked_against_frozen_profile(self):
        from mybot.evaluation.coding_campaign import file_sha
        root=self.root/'profile';await run(root,provider_mode='failover',limits=self.limits)
        p=root/'raw.json';raw=json.loads(p.read_text());raw['results'][0]['provider_execution']['requests'][0]['model']='other-model';p.write_text(json.dumps(raw))
        p=root/'terminal.json';t=json.loads(p.read_text());t['evidence']=raw['results'][0];p.write_text(json.dumps(t))
        p=root/'finished.json';end=json.loads(p.read_text());end.update(report_sha256=file_sha(root/'raw.json'),terminal_sha256=file_sha(root/'terminal.json'));p.write_text(json.dumps(end))
        with self.assertRaises(ValueError):inventory(root)

    async def test_v3_evidence_never_interpreted_as_new_campaign(self):
        root=self.root/'v3';root.mkdir();(root/'manifest.json').write_text(json.dumps({'version':3,'campaign_id':'old'}))
        with self.assertRaises(ValueError):inventory(root)

    async def test_private_provider_key_cannot_be_model_label(self):
        with self.assertRaises(ValueError):settings(self.config,live=True,
            backup={'model':'PRIVATE_PRIMARY_KEY','api_key':'PRIVATE_BACKUP_KEY','base_url':'https://offline.invalid'})

    async def test_offline_dropping_credentials_still_rejects_secret_model_label(self):
        with self.assertRaises(ValueError):settings(self.config,live=False,
            backup={'model':'PRIVATE_BACKUP_KEY','api_key':'PRIVATE_BACKUP_KEY'})

    async def test_attempt_cleanup_failure_persists_blocked_evidence(self):
        def factory(runtime,p):return client([response('claim')]) if p=='coco' else client([response('no')])
        root=self.root/'close-failure';raw=factory(None,'coco');raw.close.side_effect=RuntimeError('PRIVATE_CLOSE')
        state,r=await run(root,provider_mode='failover',limits=self.limits,offline_provider_factory=lambda *args:raw)
        self.assertEqual(state['status'],'blocked');self.assertTrue(r['results'][0]['lifecycle']['execution_uncertain'])

    async def test_multiple_case_attempts_reset_sticky(self):
        created=[]
        def factory(runtime,p):created.append(p);return client([connection()]) if p=='coco' else client([response('no patch')])
        r=await evaluate(provider_mode='failover',limits=replace(self.limits,max_cases=2),case_ids=['cache-ttl-001','pagination-001'],offline_provider_factory=factory)
        self.assertEqual(created,['coco','coco2','coco','coco2'])
        self.assertNotEqual(*[x['lifecycle']['attempt_id'] for x in r['results']])

    async def test_manifest_v4_and_historical_namespace_isolation(self):
        root=self.root/'new'
        state,r=await run(root,provider_mode='failover',limits=self.limits)
        self.assertEqual(json.loads((root/'manifest.json').read_text())['version'],4)
        self.assertEqual(state['status'],'blocked');self.assertFalse(state['strict_success'])
        self.assertEqual(r['results'][0]['lifecycle']['attempt_id'],state['attempt_id'])
        with self.assertRaises(ValueError):await run(self.root/'coding_campaign'/'old',provider_mode='failover')

    async def test_manifest_freezes_actual_limits_not_phase25_defaults(self):
        root=self.root/'limits';limits=replace(self.limits,max_requests=1,request_timeout=2,task_timeout=30)
        await run(root,provider_mode='failover',limits=limits)
        f=json.loads((root/'manifest.json').read_text())['frozen']
        self.assertEqual(f['agent']['request_timeout_seconds'],2)
        self.assertEqual(f['agent']['coding_autonomy']['max_task_seconds'],30)
        self.assertEqual(f['agent']['coding_autonomy']['max_model_requests'],1)
        self.assertEqual(f['campaign_version'],4)

    async def test_finished_or_started_attempt_never_replayed(self):
        root=self.root/'once';await run(root,provider_mode='failover',limits=self.limits)
        before={p.name:p.read_bytes() for p in root.iterdir()}
        with self.assertRaises(ValueError):await run(root,provider_mode='failover',limits=self.limits)
        self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})

    async def test_manifest_and_report_hash_tampering_rejected(self):
        for target in ('manifest.json','raw.json','terminal.json','started.json'):
            root=self.root/target;await run(root,provider_mode='failover',limits=self.limits)
            p=root/target;d=json.loads(p.read_text())
            if target=='manifest.json':d['frozen']['policy']='tampered'
            elif target=='started.json':d['attempt_id']='0'*32
            else:d['tampered']=True
            p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):inventory(root)

    async def test_cleanup_failure_campaign_blocked(self):
        root=self.root/'interrupted'
        async def broken(**kwargs):raise asyncio.CancelledError()
        with patch('mybot.evaluation.coding_failover_campaign.evaluate',side_effect=broken):
            with self.assertRaises(asyncio.CancelledError):await run(root,provider_mode='failover')
        self.assertTrue((root/'started.json').exists());self.assertTrue((root/'blocked.json').exists())
        self.assertFalse((root/'finished.json').exists());self.assertEqual(inventory(root)['status'],'blocked')


def check_coding_failover():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CodingFailoverChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_coding_failover()
