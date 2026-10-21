"""Offline tests for the opt-in live failover smoke probe; never send HTTP."""
import contextlib
import io
import unittest
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, Mock, patch

from mybot.provider_failover import ProviderFailoverClient
from scripts.smoke_provider_failover import main, run_live


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
