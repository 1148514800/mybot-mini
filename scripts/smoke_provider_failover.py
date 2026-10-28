"""Bounded opt-in connectivity probe; default is offline, never starts AgentLoop."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import time
from types import SimpleNamespace

EXPECTED_PRIMARY = 'deepseek-v4.1-flash'
EXPECTED_BACKUP = 'glm-5.3-flash'
PROMPT = [{'role': 'user', 'content': 'Reply with exactly OK.'}]


class InjectedFailure:
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


class SmokeFailure(Exception):
    """Only a fixed-field, sanitized report crosses the CLI boundary."""
    def __init__(self, report):
        self.report = report
        super().__init__('Live smoke failed; inspect sanitized report')


class RequestMeter:
    def __init__(self):
        self.sdk_calls = {'coco': 0, 'coco2': 0}
        self.http_calls = {'coco': 0, 'coco2': 0}
        self.transport_observed = False
        self.receipts = []

    def wrap(self, client, provider, model):
        meter = self
        transport = getattr(client, '_client', None)
        hooks = getattr(transport, 'event_hooks', None)
        if isinstance(hooks, dict):
            self.transport_observed = True
            async def on_request(request):
                # Runs immediately before dispatch, including SDK retry attempts.
                if request.method != 'POST' or not request.url.path.endswith('/chat/completions'):
                    raise RuntimeError('Unexpected smoke endpoint')
                if sum(meter.http_calls.values()) >= 2:
                    raise RuntimeError('Physical request budget exceeded')
                body = json.loads(request.content)
                if body.get('model') != model:
                    raise RuntimeError('Unexpected smoke model')
                meter.http_calls[provider] += 1
            hooks.setdefault('request', []).append(on_request)

        async def create(**kwargs):
            if sum(meter.sdk_calls.values()) >= 2:
                raise RuntimeError('SDK call budget exceeded')
            if kwargs.get('model') != model:
                raise RuntimeError('Unexpected smoke model')
            meter.sdk_calls[provider] += 1
            receipt = {'provider': provider, 'model': model, 'status': 'started'}
            meter.receipts.append(receipt)
            started = time.monotonic()
            try:
                reply = await client.chat.completions.create(**kwargs)
                receipt['status'] = 'returned'
                choice = reply.choices[0] if reply.choices else None
                finish = getattr(choice, 'finish_reason', None)
                receipt['finish_reason'] = finish if finish in ('stop', 'length', 'tool_calls', 'content_filter', None) else 'other'
                message = getattr(choice, 'message', None)
                text = getattr(message, 'content', None)
                receipt['response_text_chars'] = len(text) if isinstance(text, str) else 0
                usage = getattr(reply, 'usage', None)
                receipt['tokens'] = {k: getattr(usage, k, None) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
                return reply
            except BaseException as exc:
                receipt.update(status='error', error_type=type(exc).__name__)
                status = getattr(exc, 'status_code', None)
                if type(status) is int: receipt['http_status'] = status
                raise
            finally:
                receipt['duration_seconds'] = round(time.monotonic() - started, 6)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)), close=client.close)


async def run_live(mode: str, *, timeout: float = 30.0) -> dict:
    from mybot.config import GatewayConfig, _PROVIDERS
    from mybot.provider_failover import ProviderFailoverClient, build_gateway_client

    config = copy.copy(GatewayConfig())
    backup = _PROVIDERS.get('coco2', {}) if isinstance(_PROVIDERS, dict) else {}
    if mode not in ('forced', 'natural'):
        raise ValueError('Invalid smoke mode')
    if config.provider != 'coco' or config.model != EXPECTED_PRIMARY:
        raise ValueError('Expected coco/deepseek-v4.1-flash')
    if not isinstance(backup, dict) or backup.get('model') != EXPECTED_BACKUP:
        raise ValueError('Expected coco2/glm-5.3-flash')
    if not all(math.isfinite(v) and v > 0 for v in (timeout, config.request_timeout_seconds)):
        raise ValueError('Timeouts must be finite and positive')
    # Give the wrapper and its outer timeout the SAME total deadline. Otherwise
    # --timeout=30 with config=60 can cancel just as the primary's half expires.
    config.request_timeout_seconds = min(timeout, config.request_timeout_seconds)
    gateway = build_gateway_client(config)
    if not isinstance(gateway, ProviderFailoverClient):
        await gateway.close()
        raise RuntimeError('Failover client was not activated')

    meter = RequestMeter()
    injected = None
    stage = 'setup'
    started = time.monotonic()
    result = {'status': 'FAIL', 'mode': mode, 'max_physical_model_requests': 2,
              'primary_model': EXPECTED_PRIMARY, 'backup_model': EXPECTED_BACKUP,
              'request_timeout_seconds': config.request_timeout_seconds,
              'primary_reserve_timeout_seconds': config.request_timeout_seconds / 2,
              'logical_requests': 0, 'valid_responses': 0,
              'estimated_cost': None, 'cost_status': 'unknown; not free'}
    failure = None
    try:
        if mode == 'forced':
            original = gateway._primary
            injected = InjectedFailure()
            gateway._primary = injected
            await original.close()
        else:
            gateway._primary = meter.wrap(gateway._primary, 'coco', EXPECTED_PRIMARY)
        # The ordered chain dispatches and closes clients from this table.
        gateway._clients[0] = gateway._primary
        factory = gateway._factory
        gateway._factory = lambda cfg: meter.wrap(factory(cfg), 'coco2', EXPECTED_BACKUP)
        for number in range(2 if mode == 'forced' else 1):
            stage = f'request_{number + 1}'
            result['logical_requests'] += 1
            reply = await asyncio.wait_for(gateway.chat.completions.create(
                model=config.model, messages=PROMPT, max_tokens=64), timeout=config.request_timeout_seconds)
            if not reply.choices or not (reply.choices[0].message.content or '').strip():
                raise RuntimeError('No usable response')
            result['valid_responses'] += 1
            if mode == 'forced' and gateway.active_provider != 'coco2':
                raise AssertionError('Expected sticky backup')
        if injected and injected.calls != 1:
            raise AssertionError('Injected primary replayed')
        result['status'] = 'PASS'
    except Exception as exc:
        failure = exc
        result.update(error_type=type(exc).__name__, failure_stage=stage)
    finally:
        try:
            await gateway.close()
            result['cleanup_confirmed'] = True
        except Exception as exc:
            result.update(status='FAIL', cleanup_confirmed=False, cleanup_error_type=type(exc).__name__)
            if failure is None:
                failure = exc
                result.update(error_type=type(exc).__name__, failure_stage='cleanup')
        result.update(active_provider=gateway.active_provider,
            primary_injected_failures=injected.calls if injected else 0,
            sdk_create_calls=dict(meter.sdk_calls),
            physical_model_requests=sum(meter.http_calls.values()) if meter.transport_observed else sum(meter.sdk_calls.values()),
            physical_requests_by_provider=dict(meter.http_calls) if meter.transport_observed else dict(meter.sdk_calls),
            counting_method='http_request_hook' if meter.transport_observed else 'synthetic_sdk_entry',
            request_receipts=meter.receipts, duration_seconds=round(time.monotonic()-started,6))
        result['model_requests'] = result['physical_model_requests']
    if failure is not None:
        raise SmokeFailure(result) from None
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--confirm-api-cost', action='store_true', help='Allow at most 2 physical requests')
    parser.add_argument('--mode', choices=('forced', 'natural'), default='forced')
    parser.add_argument('--timeout-seconds', type=float, default=30.0)
    args = parser.parse_args(argv)
    if not args.live:
        if args.confirm_api_cost: parser.error('--confirm-api-cost requires --live')
        from scripts.check_provider_failover import check_provider_failover
        check_provider_failover()
        print('OFFLINE PASS; no real API calls')
        return 0
    if not args.confirm_api_cost: parser.error('Live requests require --live --confirm-api-cost')
    try:
        result = asyncio.run(run_live(args.mode, timeout=args.timeout_seconds))
    except SmokeFailure as exc:
        result = exc.report
    except Exception as exc:
        # Setup failed before model dispatch; do not echo arbitrary exception text.
        result = {'status': 'FAIL', 'mode': args.mode, 'failure_stage': 'setup',
                  'error_type': type(exc).__name__, 'physical_model_requests': 0}
    print('LIVE ' + result['status'] + ': ' + json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
