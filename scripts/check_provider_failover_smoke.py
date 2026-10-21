"""Offline tests for the opt-in live failover smoke probe; never send HTTP."""
import contextlib
import io
import unittest
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, Mock, patch

from mybot.provider_failover import ProviderFailoverClient
from scripts.smoke_provider_failover import main, run_live, RequestMeter, SmokeFailure


def model_reply():
    return N(choices=[N(message=N(content='OK'))])


def fake_client(effects):
    return N(chat=N(completions=N(create=AsyncMock(side_effect=effects))), close=AsyncMock())


class SmokeChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cfg = N(provider='coco', model='deepseek-v4.1-flash', request_timeout_seconds=2)
        self.primary = fake_client([model_reply()])
        self.backup = fake_client([model_reply(), model_reply()])
        self.gateway = ProviderFailoverClient(self.primary, self.cfg, N(model='glm-5.3-flash'), Mock(return_value=self.backup))
        self.settings = [patch('mybot.config.GatewayConfig', return_value=self.cfg),
                         patch('mybot.config._PROVIDERS', {'coco2': {'model': 'glm-5.3-flash'}}),
                         patch('mybot.provider_failover.build_gateway_client', return_value=self.gateway)]

    async def probe(self, mode):
        with self.settings[0], self.settings[1], self.settings[2], contextlib.redirect_stdout(io.StringIO()):
            return await run_live(mode, timeout=1)

    async def test_forced_fault_uses_backup_twice(self):
        result = await self.probe('forced')
        self.assertEqual((result['active_provider'], result['primary_injected_failures']), ('coco2', 1))
        self.primary.chat.completions.create.assert_not_awaited()
        self.primary.close.assert_awaited_once()
        self.assertEqual(self.backup.chat.completions.create.await_count, 2)
        self.backup.close.assert_awaited_once()
        for call in self.backup.chat.completions.create.call_args_list:
            self.assertEqual(call.kwargs['model'], 'glm-5.3-flash')

    async def test_natural_success_stays_primary(self):
        result = await self.probe('natural')
        self.assertEqual(result['active_provider'], 'coco')
        self.primary.chat.completions.create.assert_awaited_once()
        self.backup.chat.completions.create.assert_not_awaited()

    async def test_natural_failure_uses_backup(self):
        import httpx
        from openai import APIConnectionError
        self.primary.chat.completions.create.side_effect = APIConnectionError(request=httpx.Request('POST', 'https://injected.invalid'))
        result = await self.probe('natural')
        self.assertEqual(result['active_provider'], 'coco2')
        self.backup.chat.completions.create.assert_awaited_once()
        self.assertEqual(result['physical_model_requests'], 2)
        self.assertEqual(result['physical_requests_by_provider'], {'coco':1,'coco2':1})

    async def test_forced_failure_keeps_request_count_and_closes(self):
        import httpx
        from openai import APIConnectionError
        self.backup.chat.completions.create.side_effect=APIConnectionError(request=httpx.Request('POST','https://injected.invalid'))
        with self.assertRaises(SmokeFailure) as ctx:await self.probe('forced')
        r=ctx.exception.report
        self.assertEqual(r['physical_model_requests'],1)
        self.assertEqual(r['primary_injected_failures'],1)
        self.assertEqual(r['valid_responses'],0)
        self.assertEqual(r['failure_stage'],'request_1')
        self.assertTrue(r['cleanup_confirmed'])

    async def test_second_backup_failure_not_repeated(self):
        self.backup.chat.completions.create.side_effect=[model_reply(),RuntimeError('PRIVATE_ERROR_SENTINEL')]
        with self.assertRaises(SmokeFailure) as ctx:await self.probe('forced')
        r=ctx.exception.report
        self.assertEqual(r['physical_model_requests'],2)
        self.assertEqual(r['valid_responses'],1)
        self.assertEqual(r['failure_stage'],'request_2')
        self.assertNotIn('PRIVATE_ERROR_SENTINEL',str(r))

    async def test_outer_timeout_and_primary_reserve_share_config(self):
        with self.settings[0],self.settings[1],self.settings[2] as build,contextlib.redirect_stdout(io.StringIO()):
            r=await run_live('natural',timeout=.75)
        self.assertEqual(build.call_args.args[0].request_timeout_seconds,.75)
        self.assertEqual(r['primary_reserve_timeout_seconds'],.375)
        self.assertEqual(self.cfg.request_timeout_seconds,2)

    async def test_invalid_timeout_rejected_before_build(self):
        for timeout in (0,-1,float('inf'),float('nan')):
            with self.settings[0],self.settings[1],patch('mybot.provider_failover.build_gateway_client') as build:
                with self.assertRaises(ValueError):await run_live('natural',timeout=timeout)
                build.assert_not_called()

    async def test_response_body_not_retained(self):
        self.primary.chat.completions.create.side_effect=[N(choices=[N(message=N(content='PRIVATE_RESPONSE_SENTINEL'))])]
        r=await self.probe('natural')
        self.assertNotIn('PRIVATE_RESPONSE_SENTINEL',str(r))

    async def test_transport_counts_outbound_dispatch_and_caps_two(self):
        import httpx
        from openai import AsyncOpenAI
        seen=[]
        async def handler(request):
            seen.append(request)
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'glm-5.3-flash',
                'choices':[{'index':0,'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}]})
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        raw=AsyncOpenAI(api_key='synthetic-only',base_url='https://offline.invalid/v1',http_client=http,max_retries=0)
        meter=RequestMeter();wrapped=meter.wrap(raw,'coco2','glm-5.3-flash')
        try:
            for _ in range(2):await wrapped.chat.completions.create(model='glm-5.3-flash',messages=[{'role':'user','content':'OK'}])
            with self.assertRaises(RuntimeError):await wrapped.chat.completions.create(model='glm-5.3-flash')
        finally:await wrapped.close()
        self.assertEqual(meter.http_calls['coco2'],2);self.assertEqual(len(seen),2)
        self.assertTrue(http.is_closed)

    async def test_new_client_starts_primary_after_previous_failover(self):
        await self.probe('forced')
        fresh=ProviderFailoverClient(fake_client([model_reply()]),self.cfg,N(model='glm-5.3-flash'),Mock())
        self.gateway=fresh
        with self.settings[0],self.settings[1],patch('mybot.provider_failover.build_gateway_client',return_value=fresh):
            r=await run_live('natural',timeout=1)
        self.assertEqual(r['active_provider'],'coco');self.assertEqual(r['physical_model_requests'],1)

    async def test_sdk_wire_uses_own_key_model_and_sticky_context(self):
        import httpx,json
        from openai import AsyncOpenAI
        seen=[]
        async def handler(request):
            body=json.loads(request.content)
            seen.append((request.headers['authorization'],body['model'],body['messages']))
            if body['model']=='deepseek-v4.1-flash':
                return httpx.Response(503,json={'error':{'message':'synthetic unavailable','type':'server_error'}})
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'glm-5.3-flash',
                'choices':[{'index':0,'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}]})
        def sdk(key):
            return AsyncOpenAI(api_key=key,base_url='https://offline.invalid/v1',max_retries=0,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        primary=sdk('synthetic-primary');backup=sdk('synthetic-backup')
        gateway=ProviderFailoverClient(primary,self.cfg,N(model='glm-5.3-flash'),lambda cfg:backup)
        messages=[{'role':'user','content':'synthetic context'}]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                for _ in range(2):await gateway.create(model='deepseek-v4.1-flash',messages=messages)
        finally:await gateway.close()
        self.assertEqual([(key,model) for key,model,_ in seen],[
            ('Bearer synthetic-primary','deepseek-v4.1-flash'),
            ('Bearer synthetic-backup','glm-5.3-flash'),('Bearer synthetic-backup','glm-5.3-flash')])
        self.assertTrue(all(body==messages for _,_,body in seen))
        self.assertTrue(primary.is_closed() and backup.is_closed())

    async def test_wrong_model_blocks_before_client(self):
        with patch('mybot.config.GatewayConfig', return_value=self.cfg), \
             patch('mybot.config._PROVIDERS', {'coco2': {'model': 'wrong'}}), \
             patch('mybot.provider_failover.build_gateway_client') as build:
            with self.assertRaises(ValueError):
                await run_live('forced', timeout=1)
            build.assert_not_called()

    def test_cost_confirmation_guard(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as err:
            main(['--live'])
        self.assertEqual(err.exception.code, 2)


def check_provider_failover_smoke():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SmokeChecks)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    check_provider_failover_smoke()
