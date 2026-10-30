"""Offline failover tests. No SDK transport is allowed in these checks."""
import asyncio
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, Mock, patch

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError

from mybot.config import GatewayConfig
from mybot.provider_failover import ProviderFailoverClient, build_gateway_client, FallbackBudgetExceeded, ProviderChainExhausted
from mybot.agent import AgentLoop, ContextBuilder
from mybot.tools import build_default_tool_registry
from scripts.check_session import response, call, assert_pairs


def failed():
    return APIConnectionError(request=httpx.Request('POST', 'https://example.invalid'))


def client(effect):
    obj = N(chat=N(completions=N(create=AsyncMock(side_effect=effect))), close=AsyncMock())
    obj.with_options = Mock(return_value=obj)
    return obj


class FailoverChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.config = GatewayConfig(context_token_budget={'input_limit':64000}, provider='coco', model='deepseek-v4.1-flash', api_key='synthetic-primary',
            workspace=Path(self.tmp.name), skills_enabled=False, context_enabled=False)
        self.backup = N(provider='coco2', model='glm-5.3-flash')

    def wrapper(self, effect, backup_effect=None):
        self.primary = client(effect)
        self.secondary = client(backup_effect or [response('backup')])
        self.factory = Mock(return_value=self.secondary)
        return ProviderFailoverClient(self.primary, self.config, self.backup, self.factory)

    async def invoke(self, wrapper):
        with contextlib.redirect_stdout(io.StringIO()):
            return await wrapper.chat.completions.create(model=self.config.model, messages=[{'role':'user','content':'test'}], tools=None)

    async def test_success_never_constructs_backup(self):
        w=self.wrapper([response('primary')]);await self.invoke(w)
        self.factory.assert_not_called();self.assertEqual(w.active_provider,'coco')

    async def test_error_uses_backup_model_and_sticks(self):
        w=self.wrapper([failed()],[response('backup'),response('next')]);await self.invoke(w);await self.invoke(w)
        self.assertEqual(self.primary.chat.completions.create.await_count,1)
        self.assertEqual(self.secondary.chat.completions.create.await_count,2)
        for call in self.secondary.chat.completions.create.call_args_list:
            self.assertEqual(call.kwargs['model'],'glm-5.3-flash')
            self.assertEqual(call.kwargs['messages'],[{'role':'user','content':'test'}])
        self.assertEqual(self.config.provider,'coco');self.assertEqual(self.config.model,'deepseek-v4.1-flash')

    async def test_sdk_timeout_falls_back(self):
        w=self.wrapper([APITimeoutError(request=httpx.Request('POST','https://example.invalid'))]);await self.invoke(w)
        self.secondary.chat.completions.create.assert_awaited_once()

    async def test_status_error_falls_back(self):
        r=httpx.Response(503,request=httpx.Request('POST','https://example.invalid'))
        await self.invoke(self.wrapper([APIStatusError('synthetic',response=r,body=None)]))
        self.secondary.chat.completions.create.assert_awaited_once()

    async def test_each_provider_gets_full_window(self):
        w=self.wrapper([])
        class Expired:
            def expired(self): return True
            async def __aenter__(self): raise TimeoutError()
            async def __aexit__(self,*args): pass
        native_timeout=asyncio.timeout
        with patch('mybot.provider_failover.asyncio.timeout',side_effect=[Expired(),native_timeout(60)]) as timer:
            await self.invoke(w)
        self.assertEqual([c.args[0] for c in timer.call_args_list],[self.config.request_timeout_seconds]*2)
        self.secondary.chat.completions.create.assert_awaited_once()

    async def test_cancellation_never_falls_back(self):
        w=self.wrapper([asyncio.CancelledError()])
        with self.assertRaises(asyncio.CancelledError):await self.invoke(w)
        self.factory.assert_not_called()

    async def test_cancellation_while_waiting_does_not_start_backup(self):
        started=asyncio.Event();hold=asyncio.Event()
        async def pending(**kwargs):
            started.set();await hold.wait()
        w=self.wrapper([]);self.primary.chat.completions.create.side_effect=pending
        task=asyncio.create_task(self.invoke(w));await started.wait();task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.factory.assert_not_called()

    async def test_completed_tool_is_not_replayed_on_failover(self):
        (self.config.workspace/'note.txt').write_text('offline note')
        w=self.wrapper([response(calls=[call('read-1','read_file','{"path":"note.txt"}')]),failed()])
        tools=build_default_tool_registry(self.config.workspace)
        native=tools.get_tool('read_file');original=native.execute
        with patch.object(native,'execute',side_effect=original) as read:
            agent=AgentLoop(w,self.config,tools,ContextBuilder(self.config.workspace))
            await self.invoke_agent(agent)
        self.assertEqual(read.await_count,1)
        assert_pairs(self,agent.session.history())
        forwarded=self.secondary.chat.completions.create.call_args.kwargs['messages']
        self.assertTrue(any(m['role']=='tool' for m in forwarded))

    async def invoke_agent(self, agent):
        with contextlib.redirect_stdout(io.StringIO()):await agent.handle_message('Read note.txt')

    async def test_local_programming_error_never_falls_back(self):
        w=self.wrapper([TypeError('synthetic')])
        with self.assertRaises(TypeError):await self.invoke(w)
        self.factory.assert_not_called()

    async def test_backup_error_not_retried(self):
        w=self.wrapper([failed()],[failed()])
        with self.assertRaises(ProviderChainExhausted):await self.invoke(w)
        self.assertEqual(self.secondary.chat.completions.create.await_count,1)

    async def test_budget_refuses_second_request(self):
        w=self.wrapper([failed()]);w.before_fallback=Mock(return_value=False)
        with self.assertRaises(FallbackBudgetExceeded):await self.invoke(w)
        self.factory.assert_not_called();self.assertEqual(w.active_provider,'coco')

    async def test_close_both_even_if_primary_close_fails(self):
        w=self.wrapper([failed()]);await self.invoke(w)
        self.primary.close.side_effect=RuntimeError('synthetic')
        with self.assertRaises(RuntimeError):await w.close()
        self.secondary.close.assert_awaited_once()

    async def test_notice_does_not_include_exception_or_credentials(self):
        w=self.wrapper([failed()]);out=io.StringIO()
        with contextlib.redirect_stdout(out):await w.create(model='deepseek-v4.1-flash')
        self.assertIn('coco2',out.getvalue());self.assertNotIn('synthetic-primary',out.getvalue())
        self.assertNotIn('example.invalid',out.getvalue())

    async def test_config_factory_routes_own_credentials_and_no_sdk_retry(self):
        providers={'coco2':dict(api_key='synthetic-backup',base_url='https://backup.invalid/v1',model='glm-5.3-flash')}
        with patch.object(self.config, 'providers', providers),patch('mybot.config.build_client',side_effect=[client([failed()]),client([response('ok')])]) as factory:
            w=build_gateway_client(self.config);await self.invoke(w)
        backup=factory.call_args_list[1].args[0]
        self.assertEqual((backup.provider,backup.model,backup.api_key,backup.base_url),('coco2','glm-5.3-flash','synthetic-backup','https://backup.invalid/v1'))
        self.assertEqual(w._primary.with_options.call_args.kwargs,{'max_retries':0})
        self.assertEqual(w._backup.with_options.call_args.kwargs,{'max_retries':0})

    async def test_single_provider_uses_zero_retry_client(self):
        sdk=client([response('ok')])
        with patch.object(self.config, 'providers', {}),patch('mybot.config.build_client',return_value=sdk):
            gateway=build_gateway_client(self.config);await self.invoke(gateway)
        self.assertEqual(gateway.active_provider,self.config.provider);sdk.with_options.assert_called_once_with(max_retries=0)

    async def test_incomplete_backup_rejected_without_request(self):
        for bad in ({'model':'glm'}, {'model':'glm','api_key':'YOUR_KEY','base_url':'https://example.invalid'}):
            with patch.object(self.config, 'providers', {'coco2':bad}),patch('mybot.config.build_client') as factory:
                with self.assertRaises(ValueError):build_gateway_client(self.config)
                factory.assert_not_called()

    async def test_original_loop_budget_count_and_no_false_verification(self):
        for limit in (1,2):
            cfg=GatewayConfig(context_token_budget={'input_limit':64000}, provider='coco',model=self.config.model,api_key='synthetic',workspace=Path(self.tmp.name),
                coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'macos_readonly'},
                coding_autonomy={'enabled':True,'max_model_requests':limit},skills_enabled=False,context_enabled=False)
            w=self.wrapper([failed()]);tools=build_default_tool_registry(cfg.workspace,coding_enabled=True,patch_mode='write',command=cfg.coding_command)
            a=AgentLoop(w,cfg,tools,ContextBuilder(cfg.workspace))
            w.before_fallback=lambda definitions:a.coding_controller.before_request(definitions)
            with contextlib.redirect_stdout(io.StringIO()):await a.handle_message('Investigate this repository')
            self.assertEqual(a.last_coding_report['model_requests'],limit)
            self.assertEqual(a.last_coding_report['committed_patches'],0)
            self.assertNotEqual(a.last_coding_report['state'],'verified')
            self.assertEqual(self.secondary.chat.completions.create.await_count,limit-1)


def check_provider_failover():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(FailoverChecks)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_provider_failover()
