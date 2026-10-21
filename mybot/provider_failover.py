"""Bounded CLI-only coco -> coco2 failover; evaluation clients stay single-model."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

from openai import APIError


class FallbackBudgetExceeded(Exception):
    """The controller refused a second physical model request."""


class ProviderFailoverClient:
    def __init__(self, primary, config, backup, factory, *, recoverable=None):
        self._primary = primary
        self._config = config
        self._backup_config = backup
        self._factory = factory
        self._backup = None
        self._recoverable = recoverable
        self.active_provider = 'coco'
        self.before_fallback = lambda definitions: True
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        # AgentLoop's outer timeout remains authoritative. Reserve half for fallback
        # rather than extending its deadline or treating cancellation as an API error.
        if self.active_provider == 'coco':
            try:
                async with asyncio.timeout(self._config.request_timeout_seconds / 2):
                    return await self._primary.chat.completions.create(**kwargs)
            except (APIError, TimeoutError) as exc:
                if self._recoverable is not None and not self._recoverable(exc):
                    raise
                if not self.before_fallback(kwargs.get('tools')):
                    raise FallbackBudgetExceeded() from None
                self.active_provider = 'coco2'
                print('[LLM] coco 请求失败，切换到 coco2 备用模型。')
        if self._backup is None:
            self._backup = self._factory(self._backup_config)
        # Never reuse coco's model name on the backup endpoint. No tool is replayed.
        return await self._backup.chat.completions.create(
            **{**kwargs, 'model': self._backup_config.model})

    async def close(self):
        results = await asyncio.gather(
            *(client.close() for client in (self._primary, self._backup) if client is not None),
            return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result


def build_gateway_client(config):
    from .config import _PROVIDERS, build_client
    backup = _PROVIDERS.get('coco2') if isinstance(_PROVIDERS, dict) else None
    if config.provider != 'coco' or not backup:
        return build_client(config)
    if not isinstance(backup, dict) or any(
        not isinstance(backup.get(k), str) or not backup[k].strip()
        for k in ('api_key', 'base_url', 'model')
    ) or backup['api_key'].startswith('YOUR_'):
        raise ValueError('coco2 fallback requires configured api_key, base_url and model')
    fallback = replace(config, provider='coco2', api_key=backup['api_key'],
                       base_url=backup['base_url'], model=backup['model'])

    def factory(settings):
        # Count every physical request; do not hide extra retries inside the SDK.
        return build_client(settings).with_options(max_retries=0)

    return ProviderFailoverClient(factory(config), config, fallback, factory)
