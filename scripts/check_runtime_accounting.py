"""CLI/Web/trace accounting, real SDK MockTransport and synthetic end-to-end cases."""
import asyncio
import contextlib
from copy import deepcopy
from dataclasses import replace
import io
import json
from types import SimpleNamespace as N
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI, APIStatusError
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.context_compactor import PROMPT
from mybot.agent.context_manager import ContextManager
from mybot.agent.token_counter import TokenCounter
from mybot.runtime_accounting import RuntimeAccounting, usage_values
from mybot.provider_failover import ProviderFailoverClient
from mybot.evaluation.trace import Trace, TracedAgent, TracedClient, RequestLimitError
from mybot.tools import build_default_tool_registry
from mybot.web.runtime import ChatRuntime
from mybot.web.server import create_app
from scripts.modernization_fixtures import Base, Client, run, response, call
from scripts.check_provider_failover import failed

SCENARIO_RESULTS = {}


def used_response():
    reply=response('offline reply');reply.usage=N(prompt_tokens=7,completion_tokens=3,total_tokens=10);return reply


class AccountingChecks(Base):
    async def test_local_git_command_does_not_reuse_previous_usage(self):
        from unittest.mock import AsyncMock
        self.client.effects=[used_response()];await self.agent.handle_message('hello')
        self.config.coding_git_workflow['enabled']=True
        with patch.object(self.agent,'_git_cli',new=AsyncMock(return_value='no changes')):
            await self.agent.handle_message('/changes')
        self.assertEqual(self.agent.last_runtime_report['physical_requests'],0)
        self.assertIsNone(self.agent.last_runtime_report['provider_reported_total_tokens'])
        self.assertEqual(self.agent.last_runtime_report['outcome'],'completed')
    async def test_missing_usage_is_null_not_zero(self):
        await self.agent.handle_message('hello');r=self.agent.last_runtime_report
        self.assertEqual((r['logical_requests'],r['physical_requests']),(1,1));self.assertIsNone(r['provider_reported_total_tokens']);self.assertEqual(r['missing_usage_requests'],1);self.assertIsNone(r['http_dispatch_attempts'])
    async def test_provider_usage_and_estimate_separate(self):
        self.client.effects=[used_response()];await self.agent.handle_message('hello');r=self.agent.last_runtime_report
        self.assertEqual((r['provider_reported_input_tokens'],r['provider_reported_output_tokens'],r['provider_reported_total_tokens']),(7,3,10));self.assertNotEqual(r['context']['estimated_input_tokens'],10);self.assertIsNone(r['estimated_cost'])
    async def test_mixed_usage_preserves_subtotal_and_unknown(self):
        (self.root/'a').write_text('hello');self.client.effects=[response(calls=[call('r','read_file','{"path":"a"}')]),used_response()]
        await self.agent.handle_message('read');r=self.agent.last_runtime_report
        self.assertIsNone(r['provider_reported_total_tokens']);self.assertEqual(r['reported_token_subtotal'],10);self.assertEqual(r['missing_usage_requests'],1)
    async def test_failover_physical_vs_logical(self):
        cfg=replace(self.config,provider='coco');secondary=replace(cfg,provider='coco2',model='backup',context_token_budget={'mode':'estimate','input_limit':6500})
        gateway=ProviderFailoverClient(Client([failed()]),cfg,secondary,lambda c:Client([used_response()]))
        agent=self.build(gateway,cfg);await agent.handle_message('hello');r=agent.last_runtime_report
        self.assertEqual((r['logical_requests'],r['physical_requests']),(1,2));self.assertTrue(r['fallback_used']);self.assertIsNone(r['provider_reported_total_tokens']);self.assertEqual(r['reported_token_subtotal'],10)
        self.assertEqual(r['context']['input_token_limit'],6500)
        direct=self.build(Client(),secondary);await direct.handle_message('hello')
        self.assertFalse(direct.last_runtime_report['fallback_used'])
    async def test_http_dispatch_observed_with_mocktransport(self):
        calls=[]
        async def transport(request):
            calls.append(request)
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'synthetic','choices':[{'index':0,'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}],'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}})
        http=httpx.AsyncClient(transport=httpx.MockTransport(transport));sdk=AsyncOpenAI(api_key='synthetic',base_url='https://offline.invalid/v1',http_client=http,max_retries=0);self.addAsyncCleanup(sdk.close)
        agent=self.build(sdk);await agent.handle_message('hello')
        self.assertEqual(agent.last_runtime_report['http_dispatch_attempts'],1);self.assertEqual(len(calls),1)
    async def test_transient_only_default_failover(self):
        for code in (400,422):
            error=APIStatusError('synthetic',response=httpx.Response(code,request=httpx.Request('POST','https://offline.invalid')),body=None)
            backup=Client();cfg=replace(self.config,provider='coco');gateway=ProviderFailoverClient(Client([error]),cfg,replace(cfg,provider='coco2'),lambda c:backup)
            with self.assertRaises(APIStatusError):await self.build(gateway,cfg).handle_message('hello')
            self.assertEqual(backup.requests,[])
    async def test_trace_same_resources_without_legacy_metric_change(self):
        trace=Trace();budget={'used':0,'maximum':2};traced=TracedClient(self.client,trace,budget)
        agent=TracedAgent(traced,self.config,build_default_tool_registry(self.root),ContextBuilder(self.root),trace=trace)
        await agent.handle_message('hello');self.assertEqual(trace.runtime_accounting,agent.last_runtime_report)
        self.assertEqual(trace.metrics()['llm_requests'],1);self.assertEqual(trace.runtime_accounting['physical_requests'],1)
    async def test_trace_denied_does_not_count_physical(self):
        trace=Trace();client=TracedClient(self.client,trace,{'used':0,'maximum':0});agent=self.build(client)
        with self.assertRaises(RequestLimitError):await agent.handle_message('hello')
        self.assertEqual(agent.last_runtime_report['physical_requests'],0);self.assertEqual(self.client.requests,[])
    async def test_observer_failure_is_counted_and_nonfatal(self):
        def broken(e):raise RuntimeError('synthetic observer error')
        agent=self.build(event_callback=broken);self.assertEqual(await agent.handle_message('hello'),'offline complete');self.assertGreater(agent.resources.observation_errors,0)
    async def test_web_matches_agent_resources_and_redacts(self):
        runtime=ChatRuntime(self.config,client_factory=lambda c:Client([used_response()]));self.addAsyncCleanup(runtime.close)
        conv=runtime.new();await runtime.start(conv,'hello');await conv.task;state=conv.state()
        self.assertEqual(state['tokens'],10);self.assertEqual(state['resources']['physical_requests'],1);self.assertIn('estimated_input_tokens',state['resources']['context']);self.assertNotIn('synthetic-private-key',json.dumps(state))
    async def test_web_semantic_real_http_projection(self):
        self.semantic();app=create_app(self.config,client_factory=lambda c:self.client);self.addAsyncCleanup(app.runtime.close)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8765') as http:
            await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'Origin':'http://127.0.0.1:8765','X-Mybot-CSRF':boot['csrf']}
            conv=app.runtime.new();conv.session.restore(self.history())
            result=await http.post(f'/api/conversations/{conv.id}/messages',json={'message':'继续'},headers=headers);self.assertEqual(result.status_code,202)
            await conv.task;state=(await http.get(f'/api/conversations/{conv.id}')).json()
            self.assertEqual(state['resources']['compaction_requests'],1);self.assertEqual(state['resources']['context']['context_compaction_status'],'semantic_applied');self.assertEqual(state['status'],'completed')
    async def test_failed_plan_web_is_not_completed(self):
        client=Client([response(calls=[call('p','create_plan','{"steps":["read","finish"]}'),call('s','update_plan','{"step":1,"status":"in_progress"}'),call('r','read_file','{"path":"missing"}')]),response('done')])
        runtime=ChatRuntime(self.config,client_factory=lambda c:client);self.addAsyncCleanup(runtime.close);conv=runtime.new();await runtime.start(conv,'read missing');await conv.task
        self.assertEqual(conv.status,'failed');self.assertEqual(conv.resources['outcome'],'failed')
    async def test_cli_does_not_echo_sdk_error_secret(self):
        self.client.effects=[RuntimeError('PRIVATE_SDK_PAYLOAD')]
        with patch('builtins.input',side_effect=['hello','exit']),contextlib.redirect_stdout(io.StringIO()) as out:await self.agent.run()
        self.assertNotIn('PRIVATE_SDK_PAYLOAD',out.getvalue());self.assertIn('RuntimeError',out.getvalue())
    async def test_basic_file_bounded_read_and_utf8_write(self):
        from scripts.legacy_write_fixture import legacy_registry
        tools=legacy_registry(self.root);(self.root/'large').write_text('a'*60000)
        read=await tools.execute('read_file',{'path':'large'});self.assertTrue(read.metadata['truncated']);self.assertIn('不能据此声称完整读取',read.output)
        write=await tools.execute('write_file',{'path':'utf8','content':'中文'});self.assertIn('6 bytes',write.output)
    async def test_usage_invalid_values_unknown(self):
        self.assertEqual(usage_values(N(prompt_tokens=True,completion_tokens=-1,total_tokens='3')),dict(prompt_tokens=None,completion_tokens=None,total_tokens=None))
    async def test_workspace_lease_process_collision_and_crash_release(self):
        import subprocess, sys
        from mybot.workspace_lease import WorkspaceLease, WorkspaceBusy
        code="from mybot.workspace_lease import WorkspaceLease; import sys,time; lease=WorkspaceLease(sys.argv[1]).acquire(); print('held',flush=True); time.sleep(30)"
        child=subprocess.Popen([sys.executable,'-c',code,str(self.root)],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(await asyncio.to_thread(child.stdout.readline),'held\n')
            with self.assertRaises(WorkspaceBusy):WorkspaceLease(self.root).acquire()
            other=WorkspaceLease(self.root/'other').acquire();other.release()
        finally:
            child.kill();await asyncio.to_thread(child.wait);child.stdout.close()
        lease=WorkspaceLease(self.root).acquire();lease.release()
    async def test_workspace_lease_uncertain_retains_and_symlink_rejected(self):
        import hashlib,os
        from mybot.workspace_lease import WorkspaceLease,WorkspaceBusy
        lease=WorkspaceLease(self.root).acquire();lease.release(confirmed=False)
        try:
            with self.assertRaises(WorkspaceBusy):WorkspaceLease(self.root).acquire()
        finally:
            lease.release();WorkspaceLease.uncertain.remove(lease)
        directory=self.root/'locks';directory.mkdir(mode=0o700)
        name=hashlib.sha256(os.fsencode(self.root.resolve())).hexdigest()+'.lock'
        (directory/name).symlink_to(self.root/'target')
        with patch.object(WorkspaceLease,'directory',directory),self.assertRaises(OSError):WorkspaceLease(self.root).acquire()
        self.assertFalse((self.root/'target').exists())
    async def test_web_busy_cross_runtime_sends_no_model_request(self):
        from mybot.workspace_lease import WorkspaceLease
        lease=WorkspaceLease(self.root).acquire()
        try:
            runtime=ChatRuntime(self.config,client_factory=lambda c:self.client)
            c=runtime.new();await runtime.start(c,'hello');await c.task
            self.assertEqual(c.status,'failed');self.assertEqual(self.client.requests,[])
        finally:lease.release()
    async def test_cli_close_failure_keeps_lease(self):
        from mybot.app import run_gateway
        from mybot.workspace_lease import WorkspaceLease,WorkspaceBusy
        from unittest.mock import AsyncMock
        client=Client();client.close=AsyncMock(side_effect=RuntimeError('close failed'))
        try:
            with patch('mybot.app.build_client',return_value=client),patch.object(AgentLoop,'run',new=AsyncMock()):
                with self.assertRaises(RuntimeError):await run_gateway(self.config)
            with self.assertRaises(WorkspaceBusy):WorkspaceLease(self.root).acquire()
        finally:
            for lease in list(WorkspaceLease.uncertain):
                if lease.workspace==self.root:lease.release();WorkspaceLease.uncertain.remove(lease)

    async def test_scenario_a_long_dialogue(self):
        self.semantic();old=deepcopy(self.agent.session.export_turns());await self.agent.handle_message('继续')
        r=self.agent.last_runtime_report;self.assertEqual(r['compaction_requests'],1);self.assertEqual(self.agent.session.export_turns()[:-1],old)
        SCENARIO_RESULTS['A']=dict(original_char_budget=self.config.context_max_chars,resources=r,retained=['goal','changed constraint','pending tests','unknown provider'],information_loss='source excerpts explicitly incomplete; semantic selection may omit facts',ended=True,false_verified=False)
    async def test_scenario_b_long_code(self):
        (self.root/'long.py').write_text('print("中文")\n'*5000)
        self.client.effects=[response(calls=[call('code','read_file','{"path":"long.py"}')]),response('仅分析节选')]
        reply=await self.agent.handle_message('读取长代码')
        self.assertIn('未验证全文',reply);r=self.agent.last_runtime_report;self.assertTrue(r['context']['current_clipped'])
        SCENARIO_RESULTS['B']=dict(original_char_budget=self.config.context_max_chars,resources=r,retained=['current user','system','tool call id code'],information_loss='tool body clipped with explicit marker',ended=True,false_verified=False)
    async def test_scenario_c_receipt_and_current_revision_test(self):
        from scripts.check_web_ui import config,SyntheticClient
        from scripts.check_patch_preview_receipt import init
        from scripts.check_tool_verification_reliability import approve
        init(self.root);cfg=config(self.root,True);cfg.context_enabled=True;cfg.context_token_budget={'mode':'estimate','input_limit':30000,'model_windows':{}};cfg.context_tool_result_max_chars=4000
        class SearchClient(SyntheticClient):
            searched=False
            async def create(self, **kwargs):
                if not self.searched:
                    self.searched=True
                    return response(calls=[call('search','search_code','{"query":"value","path":"."}')])
                return await super().create(**kwargs)
        client=SearchClient(cfg);tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',preview_receipt=True,command={'mode':'macos_readonly'},command_approval_provider=approve)
        agent=AgentLoop(client,cfg,tools,ContextBuilder(self.root));agent.session.restore(self.history(25000));await agent.handle_message('修复当前项目')
        self.assertEqual(agent.last_coding_report['state'],'verified');self.assertGreater(agent.last_coding_report['tests_passed_after_last_patch'],0)
        if agent._git_capsule:agent._git_capsule.close()
        SCENARIO_RESULTS['C']=dict(original_char_budget=cfg.context_max_chars,resources=agent.last_runtime_report,controller=agent.last_coding_report,retained=['receipt scope','current revision','native test evidence'],information_loss='old full turns deterministically summarized',ended=True,false_verified=False,strict_success_claimed=False)


def check_runtime_accounting():run(AccountingChecks)
if __name__=='__main__':
    import sys
    from pathlib import Path
    check_runtime_accounting()
    if len(sys.argv)==3 and sys.argv[1]=='--scenarios':Path(sys.argv[2]).write_text(json.dumps(SCENARIO_RESULTS,ensure_ascii=False,indent=2)+'\n')
