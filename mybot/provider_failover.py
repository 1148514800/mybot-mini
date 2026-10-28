"""Ordered, task-sticky provider failover; each physical send retains native gates."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError


def recoverable_error(exc):
    # SDK connection wrappers must not turn host/authority/budget bugs into retries.
    cause = exc
    for _ in range(8):
        cause = cause.__cause__
        if cause is None: break
        if isinstance(cause, (TypeError, ValueError, RuntimeError, PermissionError)): return False
    return (isinstance(exc, (APIConnectionError, APITimeoutError, TimeoutError, httpx.TransportError, ConnectionError))
            or isinstance(exc, APIStatusError) and (exc.status_code in (401,403,404,408,429) or 500 <= exc.status_code < 600))


class FallbackBudgetExceeded(Exception):
    """A native safety/budget gate refused the next physical request."""


class ProviderChainExhausted(Exception):
    """Only bounded, sanitized classifications; never raw SDK exception strings."""
    def __init__(self, failures):
        self.failures = tuple(failures)
        super().__init__('所有可尝试 Provider 均失败：' + '；'.join(f'{name}（{reason}）' for name, reason in failures)[:4096])


class ProviderFailoverClient:
    def __init__(self, primary, config, backup=None, factory=None, *, providers=None, recoverable=None):
        # Keep the established two-client constructor for evaluation adapters.
        if providers is None:
            from .config import GatewayConfig
            providers = [] if backup is None else [backup if isinstance(backup, GatewayConfig) else replace(config,
                provider=getattr(backup, 'provider', 'backup'), model=backup.model,
                api_key=getattr(backup, 'api_key', config.api_key), base_url=getattr(backup, 'base_url', config.base_url))]
        self._configs = (config, *providers)
        if len({c.provider for c in self._configs}) != len(self._configs): raise ValueError('duplicate_provider')
        self._clients = {0: primary}
        self._index = 0
        self._primary, self._config, self._factory = primary, config, factory
        self._backup_config = self._configs[1] if len(self._configs) > 1 else config
        self._backup = None
        self._recoverable = recoverable or recoverable_error
        self.before_fallback = lambda definitions: True
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    @property
    def active_config(self): return self._configs[self._index]

    @property
    def active_provider(self): return self.active_config.provider

    @property
    def secret_values(self): return tuple(dict.fromkeys(c.api_key for c in self._configs if c.api_key))

    @property
    def logical_request_timeout(self):
        # Stream closure can take up to 3s; task deadlines remain authoritative.
        return sum(c.request_timeout_seconds + 3 for c in self._configs)

    def reset_task(self): self._index = 0

    def _label(self, value):
        value = str(value)
        for secret in self.secret_values: value = value.replace(secret, '[REDACTED]')
        return ''.join(c for c in value if c.isalnum() or c in '._-/[]:@+ ')[:128]

    @staticmethod
    def _reason(exc):
        if isinstance(exc, (TimeoutError, APITimeoutError, httpx.TimeoutException)): return '请求超时'
        if isinstance(exc, APIStatusError): return f'HTTP {exc.status_code}'
        return '连接或网络失败'

    @staticmethod
    def _stream_safe(record):
        # Native consume assembles calls only after a trusted terminal and close.
        # No tool from this response can execute while dispatch is still pending.
        d = record.get('stream_diagnostic') or {}
        return (d.get('closed') is True and d.get('close_called') is True and not record.get('terminal_trusted')
                and ((d.get('phase') == 'sdk_iteration' and d.get('error_code') in
                      ('stream_transport_interrupted','stream_local_timeout','stream_user_or_caller_cancelled'))
                     or d.get('phase') == 'terminal_validation' and d.get('error_code') == 'stream_terminal_missing'))

    @staticmethod
    def _discard(record):
        from .agent.streaming import OBSERVER
        notify, _ = OBSERVER.get() or (None, ())
        d = record.get('stream_diagnostic') or {}
        if notify and d.get('stream_id'):
            notify(dict(type='model_stream_discarded', stream_id=d['stream_id'], text='',
                        status='discarded', preview_revision=1000000))

    async def create(self, **kwargs):
        from .runtime_accounting import dispatch
        from .agent.token_counter import TokenCounter
        failures = []
        order = [(self._index + offset) % len(self._configs) for offset in range(len(self._configs))]
        for offset, index in enumerate(order):
            settings = self._configs[index]
            request = {**kwargs, 'model':settings.model}
            TokenCounter.enforce(settings, request)
            if offset:
                if not self.before_fallback(kwargs.get('tools')): raise FallbackBudgetExceeded()
                print(f'[LLM] {failures[-1][0]} {failures[-1][1]}，自动切换到 {self._label(settings.provider)} / {self._label(settings.model)}')
            self._index = index
            if index not in self._clients:
                self._clients[index] = self._factory(settings)
                if index == 1: self._backup = self._clients[index]
            attempt = {}
            timer = asyncio.timeout(settings.request_timeout_seconds)
            try:
                async with timer:
                    response = await dispatch(self._clients[index], settings, request, is_fallback=bool(offset or index), record=attempt)
            except Exception as exc:
                if attempt.get('dispatch_phase') == 'host_preflight' or not self._recoverable(exc): raise
                if kwargs.get('stream') and attempt.get('sdk_stream_opened') and not self._stream_safe(attempt): raise
                # An enclosing task Stop/deadline raises CancelledError, never enters here.
                reason = self._reason(exc)
                attempt.update(status='failed', failure_category=reason, provider_deadline_expired=timer.expired())
                self._discard(attempt)
            else:
                code = (getattr(response, 'stream_delivery', None) or {}).get('error_code')
                if code not in ('stream_transport_interrupted','stream_local_timeout','stream_terminal_missing') or not self._stream_safe(attempt):
                    return response
                reason = '流式响应中断'
                attempt.update(status='failed', failure_category=reason)
                self._discard(attempt)
            failures.append((self._label(settings.provider), reason))
        raise ProviderChainExhausted(failures) from None

    async def close(self):
        clients = {id(c):c for c in self._clients.values()}
        results = await asyncio.gather(*(c.close() for c in clients.values()), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException): raise result


def provider_order(default, providers):
    """JSON declaration order, rotated to the default; no client construction."""
    if not isinstance(providers, dict) or any(not isinstance(n,str) or not n for n in providers):
        raise ValueError('invalid_provider_configuration')
    names = list(providers)
    if default in names:
        start = names.index(default)
        names = names[start:] + names[:start]
    return names


def validate_provider(raw):
    if (not isinstance(raw, dict) or
        any(not isinstance(raw.get(k), str) or not raw[k].strip() for k in ('api_key','base_url','model')) or
        raw['api_key'].startswith('YOUR_')):
        raise ValueError('invalid_provider_configuration')


def build_gateway_client(config):
    from .config import _PROVIDERS, build_client
    configs = []
    names = provider_order(config.provider, _PROVIDERS)
    if config.provider not in names:
        configs.append(config)  # Legacy top-level credentials/config remain supported.
    for name in names:
        raw = _PROVIDERS[name]
        validate_provider(raw)
        configs.append(replace(config, provider=name, **{k:raw[k] for k in ('api_key','base_url','model')}))

    def factory(settings): return build_client(settings).with_options(max_retries=0)
    return ProviderFailoverClient(factory(configs[0]), configs[0], factory=factory, providers=configs[1:])
