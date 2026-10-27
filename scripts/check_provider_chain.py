"""Small Mock-only chain tests: no canary, provider credentials or paid transport."""
import asyncio
import contextlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import APIStatusError

from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.streaming import OBSERVER, StreamCleanupError
from mybot.provider_failover import ProviderFailoverClient, ProviderChainExhausted, build_gateway_client
from mybot.runtime_accounting import RuntimeAccounting
from mybot.tools import build_default_tool_registry
from scripts.check_provider_failover import client, failed
from scripts.check_session import response, call
from scripts.eventstore_fixtures import configuration
from scripts.streaming_fixtures import Client, Stream, chunk, tool


class ChainChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cfg=configuration(Path(self.tmp.name).resolve(),provider='alpha',model='model-a',api_key='alpha-private-key',context_token_budget={'mode':'estimate','input_limit':20000})
        self.configs=[self.cfg,replace(self.cfg,provider='beta',model='model-b',api_key='beta-private-key'),replace(self.cfg,provider='gamma',model='model-c',api_key='gamma-private-key')]

    def gateway(self,clients):
        self.clients=clients
        return ProviderFailoverClient(clients[0],self.cfg,factory=lambda cfg:clients[['alpha','beta','gamma'].index(cfg.provider)],providers=self.configs[1:])

    async def invoke(self,g,**extra):
        with contextlib.redirect_stdout(io.StringIO()):
            return await RuntimeAccounting().request(g,self.cfg,dict(model=self.cfg.model,messages=[dict(role='user',content='offline')],**extra))

    async def test_first_success_skips_all_backups(self):
        g=self.gateway([client([response('first')]),client([]),client([])])
        await self.invoke(g);self.assertEqual(len(g._clients),1)

    async def test_two_failures_third_success_and_sticky_model(self):
        g=self.gateway([client([failed()]),client([TimeoutError()]),client([response('third'),response('again')])])
        await self.invoke(g);await self.invoke(g)
        self.assertEqual(g.active_provider,'gamma')
        self.assertEqual(self.clients[2].chat.completions.create.await_count,2)
        self.assertTrue(all(c.kwargs['model']=='model-c' for c in self.clients[2].chat.completions.create.call_args_list))
        self.assertEqual(self.clients[0].chat.completions.create.await_count,1)

    async def test_middle_default_config_wraps_json_order_and_own_credentials(self):
        providers={n:dict(api_key=n+'-private',base_url='http://'+n+'.invalid/v1',model=n+'-model') for n in ('alpha','beta','gamma')}
        built=[]
        def factory(cfg):
            built.append(cfg);return client([failed()] if cfg.provider!='alpha' else [response('wrapped')])
        with patch('mybot.config._PROVIDERS',providers),patch('mybot.config.build_client',side_effect=factory):
            g=build_gateway_client(replace(self.cfg,provider='beta'))
            await self.invoke(g)
        self.assertEqual([c.provider for c in built],['beta','gamma','alpha'])
        for c in built:
            self.assertEqual((c.api_key,c.base_url,c.model),(c.provider+'-private','http://'+c.provider+'.invalid/v1',c.provider+'-model'))
            self.assertEqual(c.coding_command,self.cfg.coding_command)

    async def test_all_fail_once_with_sanitized_reason(self):
        g=self.gateway([client([failed()]),client([failed()]),client([failed()])])
        with self.assertRaises(ProviderChainExhausted) as caught:await self.invoke(g)
        self.assertIn('所有可尝试 Provider',str(caught.exception));self.assertEqual(len(caught.exception.failures),3)
        self.assertNotIn('private',str(caught.exception));self.assertNotIn('example.invalid',str(caught.exception))
        self.assertTrue(all(c.chat.completions.create.await_count==1 for c in self.clients))

    async def test_unavailable_statuses_switch_but_bad_parameters_do_not(self):
        for status in (401,403,404,408,429,500,501,599,400,422):
            error=APIStatusError('DO_NOT_LOG_SECRET',response=httpx.Response(status,request=httpx.Request('POST','http://mock.invalid')),body=None)
            g=self.gateway([client([error]),client([response('ok')]),client([])])
            if status in (400,422):
                with self.assertRaises(APIStatusError):await self.invoke(g)
                self.assertEqual(len(g._clients),1)
            else:await self.invoke(g);self.assertEqual(g.active_provider,'beta')

    async def test_host_permission_and_wrapped_host_errors_never_switch(self):
        for error in (ValueError('bug'),PermissionError('denied'),RuntimeError('budget')):
            g=self.gateway([client([error]),client([]),client([])])
            with self.assertRaises(type(error)):await self.invoke(g)
            self.assertEqual(len(g._clients),1)
        wrapped=failed();wrapped.__cause__=RuntimeError('host gate')
        g=self.gateway([client([wrapped]),client([]),client([])])
        with self.assertRaises(type(wrapped)):await self.invoke(g)
        self.assertEqual(len(g._clients),1)

    async def test_new_agent_task_resets_default_and_completed_tool_not_replayed(self):
        (self.cfg.workspace/'note').write_text('example')
        g=self.gateway([client([response(calls=[call('once','read_file','{"path":"note"}')]),failed(),response('new task')]),client([response('fallback')]),client([])])
        tools=build_default_tool_registry(self.cfg.workspace);native=tools.get_tool('read_file')
        a=AgentLoop(g,self.cfg,tools,ContextBuilder(self.cfg.workspace))
        with patch.object(native,'execute',wraps=native.execute) as read,contextlib.redirect_stdout(io.StringIO()):
            await a.handle_message('read note');self.assertEqual(g.active_provider,'beta');self.assertEqual(read.await_count,1)
            await a.handle_message('new task');self.assertEqual(g.active_provider,'alpha');self.assertEqual(read.await_count,1)
        self.assertEqual(a.last_runtime_report['physical_requests'],1)

    async def test_loop_gives_each_provider_full_window(self):
        self.cfg=replace(self.cfg,request_timeout_seconds=.04)
        self.configs=[replace(c,request_timeout_seconds=.04) for c in self.configs]
        async def slow(**kwargs):await asyncio.sleep(.03);return response('second')
        second=client([]);second.chat.completions.create.side_effect=slow
        async def pending(**kwargs):await asyncio.sleep(10)
        first=client([]);first.chat.completions.create.side_effect=pending
        g=self.gateway([first,second,client([])])
        a=AgentLoop(g,self.cfg,build_default_tool_registry(self.cfg.workspace),ContextBuilder(self.cfg.workspace))
        with contextlib.redirect_stdout(io.StringIO()):reply=await a.handle_message('test')
        self.assertIn('second',reply);self.assertEqual(a.last_runtime_report['physical_requests'],2)

    async def test_native_controller_budget_blocks_third_send(self):
        self.cfg=replace(self.cfg,coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'macos_readonly'},coding_autonomy={'enabled':True,'max_model_requests':2})
        self.configs=[replace(self.cfg,provider=c.provider,model=c.model,api_key=c.api_key) for c in self.configs]
        g=self.gateway([client([failed()]),client([failed()]),client([response('forbidden')])])
        tools=build_default_tool_registry(self.cfg.workspace,coding_enabled=True,patch_mode='write',command=self.cfg.coding_command)
        a=AgentLoop(g,self.cfg,tools,ContextBuilder(self.cfg.workspace))
        with contextlib.redirect_stdout(io.StringIO()):await a.handle_message('investigate')
        self.assertEqual(a.last_coding_report['model_requests'],2);self.assertEqual(a.last_runtime_report['physical_requests'],2);self.assertEqual(len(g._clients),2)
        self.assertEqual(a._logical_request_timeout(type('Deadline',(),{'remaining_seconds':.05})()),.05)

    async def test_stream_fragment_closed_discarded_and_never_executed(self):
        first=Stream([chunk('partial alpha'),chunk(tools=[tool(0,'unfinished','read_file','{')]),OSError('network')])
        second=Stream([chunk('complete beta',finish='stop')]);g=self.gateway([Client([first]),Client([second]),Client([])])
        events=[];token=OBSERVER.set((events.append,g.secret_values));a=RuntimeAccounting()
        try:
            with contextlib.redirect_stdout(io.StringIO()):r=await a.request(g,self.cfg,dict(model='model-a',messages=[dict(role='user',content='test')],stream=True))
        finally:OBSERVER.reset(token)
        self.assertEqual(r.choices[0].message.content,'complete beta');self.assertIsNone(r.choices[0].message.tool_calls)
        self.assertTrue(first.closed);self.assertEqual([r['provider'] for r in a.records],['alpha','beta'])
        discarded=next(e for e in events if e['type']=='model_stream_discarded');self.assertEqual(discarded['text'],'')
        self.assertEqual(a.records[0]['status'],'failed');self.assertIsNone(a.snapshot()['provider_reported_total_tokens'])

    async def test_stream_close_failure_stops_chain(self):
        class BrokenClose(Stream):
            async def close(self):raise RuntimeError('cannot close')
        g=self.gateway([Client([BrokenClose([chunk('partial'),OSError('network')])]),Client([]),Client([])])
        with self.assertRaises(StreamCleanupError):await self.invoke(g,stream=True)
        self.assertEqual(len(g._clients),1)

    async def test_invalid_tool_protocol_is_not_retried(self):
        g=self.gateway([Client([Stream([chunk(tools=[tool(0,'x','bad-name!','{}')],finish='tool_calls')])]),Client([]),Client([])])
        r=await self.invoke(g,stream=True);self.assertEqual(len(g._clients),1);self.assertIsNone(r.choices[0].message.tool_calls)

    async def test_stop_during_fallback_stream_does_not_try_third(self):
        slow=Stream([chunk('late')],delay=10)
        g=self.gateway([Client([failed()]),Client([slow]),Client([])])
        with contextlib.redirect_stdout(io.StringIO()):
            task=asyncio.create_task(self.invoke(g,stream=True))
            while not g._index:await asyncio.sleep(.001)
            await asyncio.sleep(.01);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(slow.closed);self.assertEqual(len(g._clients),2)

    async def test_stream_failure_after_prior_tool_does_not_replay_tool(self):
        self.cfg=replace(self.cfg,web_streaming=True)
        (self.cfg.workspace/'note').write_text('offline')
        first=Client([Stream([chunk(tools=[tool(0,'once','read_file','{"path":"note"}')],finish='tool_calls')]),Stream([chunk('partial'),OSError('network')])])
        g=self.gateway([first,Client([Stream([chunk('complete',finish='stop')])]),Client([])])
        registry=build_default_tool_registry(self.cfg.workspace);native=registry.get_tool('read_file')
        a=AgentLoop(g,self.cfg,registry,ContextBuilder(self.cfg.workspace),event_callback=lambda e:None)
        with patch.object(native,'execute',wraps=native.execute) as read,contextlib.redirect_stdout(io.StringIO()):
            await a.handle_message('read note')
        self.assertEqual(read.await_count,1);self.assertEqual(a.last_runtime_report['physical_requests'],3)

    async def test_all_provider_keys_redacted_in_preview_final_and_web(self):
        self.cfg=replace(self.cfg,web_streaming=True)
        text=' '.join(c.api_key for c in self.configs)+'\n'
        g=self.gateway([Client([failed()]),Client([failed()]),Client([Stream([chunk(text,finish='stop')])])])
        events=[];a=AgentLoop(g,self.cfg,build_default_tool_registry(self.cfg.workspace),ContextBuilder(self.cfg.workspace),event_callback=events.append)
        with contextlib.redirect_stdout(io.StringIO()):reply=await a.handle_message('test')
        from mybot.web.runtime import Conversation
        from mybot.agent.session import Session
        c=Conversation('test',Session(6));c.secret_values=g.secret_values;c.emit(dict(type='display',text=text))
        for secret in g.secret_values:
            self.assertNotIn(secret,reply);self.assertNotIn(secret,str(events));self.assertNotIn(secret,str(c.events))

    async def test_host_admission_timeout_is_not_provider_failure(self):
        def reject():raise TimeoutError('host gate')
        g=self.gateway([client([response('unused')]),client([]),client([])])
        with self.assertRaises(TimeoutError):
            await RuntimeAccounting(on_dispatch=reject).request(g,self.cfg,dict(model='model-a',messages=[dict(role='user',content='test')]))
        self.assertEqual(len(g._clients),1);self.clients[0].chat.completions.create.assert_not_awaited()

    async def test_preview_callback_timeout_does_not_retry_host_failure(self):
        def broken(event):
            if event['type']=='model_text_delta':raise TimeoutError('host observer')
        first=Stream([chunk('line\n'),chunk('later')],delay=.11);g=self.gateway([Client([first]),Client([]),Client([])])
        token=OBSERVER.set((broken,()))
        try:
            with self.assertRaises((TimeoutError,StreamCleanupError)):await self.invoke(g,stream=True)
        finally:OBSERVER.reset(token)
        self.assertTrue(first.closed);self.assertEqual(len(g._clients),1)

    async def test_sticky_provider_uses_its_window_not_default_model_window(self):
        self.cfg=replace(self.cfg,max_completion_tokens=64,context_token_budget={'mode':'estimate','input_limit':20000,'model_windows':{'alpha/model-a':1000,'beta/model-b':20000}})
        self.configs=[replace(self.cfg,provider=c.provider,model=c.model,api_key=c.api_key) for c in self.configs]
        g=self.gateway([client([failed()]),client([response('ok'),response('larger')]),client([])])
        await self.invoke(g)
        with contextlib.redirect_stdout(io.StringIO()):
            r=await RuntimeAccounting().request(g,self.cfg,dict(model='model-a',messages=[dict(role='user',content='x'*2000)]))
        self.assertEqual(r.choices[0].message.content,'larger');self.assertEqual(g.active_provider,'beta')

    async def test_real_mock_http_each_attempt_and_names_counted(self):
        sends=[]
        from openai import AsyncOpenAI
        def sdk(cfg):
            async def handler(request):
                sends.append((cfg.provider,__import__('json').loads(request.content)['model']))
                if cfg.provider!='gamma':return httpx.Response(503,json={'error':{'message':'private'}})
                return httpx.Response(200,json={'id':'mock','choices':[{'index':0,'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
            return AsyncOpenAI(api_key=cfg.api_key,base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        g=ProviderFailoverClient(sdk(self.cfg),self.cfg,providers=self.configs[1:],factory=sdk);a=RuntimeAccounting()
        try:
            with contextlib.redirect_stdout(io.StringIO()):await a.request(g,self.cfg,dict(model='model-a',messages=[dict(role='user',content='test')]))
        finally:await g.close()
        self.assertEqual(sends,[('alpha','model-a'),('beta','model-b'),('gamma','model-c')]);self.assertEqual(a.snapshot()['http_dispatch_attempts'],3)
        self.assertIsNone(a.snapshot()['provider_reported_total_tokens']);self.assertEqual(a.snapshot()['reported_token_subtotal'],3)


if __name__=='__main__':unittest.main()
