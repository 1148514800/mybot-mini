"""Bounded, opt-in live probe for the CLI's coco -> coco2 provider fallback.

Default mode runs existing offline checks. Live mode only sends constant text to a
model; it never starts AgentLoop, calls tools, or touches Phase25 evidence.
"""
from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace

EXPECTED_PRIMARY = 'deepseek-v4.1-flash'
EXPECTED_BACKUP = 'glm-5.3-flash'
PROMPT = [{'role': 'user', 'content': 'Reply with exactly OK.'}]


class InjectedFailure:
    """A primary that always fails locally, without opening a network connection."""

    def __init__(self):
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        from openai import APIConnectionError
        import httpx
        self.calls += 1
        raise APIConnectionError(request=httpx.Request('POST', 'https://injected.invalid/v1'))

    async def close(self):
        pass


async def run_live(mode: str, *, timeout: float = 30.0) -> dict:
    from mybot.config import GatewayConfig, _PROVIDERS
    from mybot.provider_failover import ProviderFailoverClient, build_gateway_client

    config = GatewayConfig()
    backup = _PROVIDERS.get('coco2', {}) if isinstance(_PROVIDERS, dict) else {}
    if config.provider != 'coco' or config.model != EXPECTED_PRIMARY:
        raise ValueError('Expected llm.provider=coco and coco.model=deepseek-v4.1-flash')
    if not isinstance(backup, dict) or backup.get('model') != EXPECTED_BACKUP:
        raise ValueError('Expected coco2.model=glm-5.3-flash')
    if timeout <= 0 or config.request_timeout_seconds <= 0:
        raise ValueError('Timeouts must be positive')

    gateway = build_gateway_client(config)
    if not isinstance(gateway, ProviderFailoverClient):
        raise RuntimeError('Failover client was not activated; check local coco2 credentials')

    injected = None
    try:
        if mode == 'forced':
            # The real coco client is constructed but never used: close it before
            # replacing it with an in-memory error. Only coco2 can contact the API.
            original = gateway._primary
            injected = InjectedFailure()
            gateway._primary = injected
            await original.close()

        count = 2 if mode == 'forced' else 1
        for _ in range(count):
            reply = await asyncio.wait_for(
                gateway.chat.completions.create(
                    model=config.model, messages=PROMPT, max_tokens=64),
                timeout=min(timeout, config.request_timeout_seconds))
            if not reply.choices or not (reply.choices[0].message.content or '').strip():
                raise RuntimeError('Model returned no usable text')
            if mode == 'forced' and gateway.active_provider != 'coco2':
                raise AssertionError('Expected sticky coco2 after injected failure')

        if mode == 'forced' and injected.calls != 1:
            raise AssertionError('Primary was invoked again after fallback')
        return {'status': 'PASS', 'mode': mode, 'active_provider': gateway.active_provider,
                'primary_injected_failures': injected.calls if injected else 0,
                'model_requests': count, 'max_physical_model_requests': 2,
                'primary_model': EXPECTED_PRIMARY, 'backup_model': EXPECTED_BACKUP}
    finally:
        await gateway.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Allow real model API calls')
    parser.add_argument('--confirm-api-cost', action='store_true', help='Explicitly allow up to 2 paid model requests')
    parser.add_argument('--mode', choices=('forced', 'natural'), default='forced',
                        help='Forced uses injected primary error; natural tries live coco first')
    parser.add_argument('--timeout-seconds', type=float, default=30.0)
    args = parser.parse_args(argv)
    if not args.live:
        if args.confirm_api_cost:
            parser.error('--confirm-api-cost requires --live')
        from scripts.check_provider_failover import check_provider_failover
        check_provider_failover()
        print('OFFLINE PASS; no real API calls')
        return 0
    if not args.confirm_api_cost:
        parser.error('Live requests require --live --confirm-api-cost')
    try:
        result = asyncio.run(run_live(args.mode, timeout=args.timeout_seconds))
    except Exception as exc:
        # Avoid printing provider exception strings; they may contain URLs or keys.
        print(f'LIVE FAIL: {type(exc).__name__} (details suppressed)')
        return 1
    print('LIVE PASS: ' + ', '.join(f'{key}={value}' for key, value in result.items()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
