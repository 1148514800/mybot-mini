"""Shared per-turn accounting; no prompts, payloads, keys or raw SDK errors retained."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field

from .agent.token_counter import TokenCounter

CURRENT = ContextVar('mybot_accounting', default=None)
CURRENT_CONFIG = ContextVar('mybot_accounting_config', default=None)
PHYSICAL = ContextVar('mybot_physical_request', default=None)
TOKEN_KEYS = ('prompt_tokens', 'completion_tokens', 'total_tokens')


# Delivery status is independent of revision verification and task correctness.
OUTPUT_NOTICES = {
    'output_truncated': '模型达到本轮输出长度限制，以下回答可能不完整。可以要求继续回答，或在下一轮调整允许的输出长度。',
    'content_filtered': '供应商过滤了本轮回复，不能确认回答完整。',
    'empty_response': '模型未返回有效文本，本轮回答未完成。',
    'provider_error': '供应商回复状态异常，本轮回答未完成。',
    'response_unconfirmed': '供应商未提供可确认的结束状态，不能确认回答完整。',
}


def response_status(response):
    """Only protocol evidence; never infer completion from prose or its length."""
    if getattr(response,'stream_delivery',None) is not None:return dict(response.stream_delivery)
    choices = getattr(response, 'choices', None)
    if getattr(response, 'error', None) or not choices or len(choices) != 1:
        return dict(status='provider_error', finish_reason='invalid', complete=False)
    choice = choices[0]
    message = getattr(choice, 'message', None)
    finish = getattr(choice, 'finish_reason', None)
    calls = getattr(message, 'tool_calls', None)
    text = getattr(message, 'content', None)
    if finish == 'length': status = 'output_truncated'
    elif finish == 'content_filter': status = 'content_filtered'
    elif message is None or getattr(message, 'function_call', None): status = 'provider_error'
    elif finish == 'tool_calls': status = 'tool_calls' if calls else 'provider_error'
    elif finish == 'stop':
        status = ('provider_error' if calls or (text is not None and not isinstance(text, str)) else
                  'complete' if isinstance(text, str) and text.strip() else 'empty_response')
    elif finish is None and calls:
        # Legacy in-process clients omit the finish field. Tool permissions still
        # apply; this does not establish a complete natural-language response.
        status = 'tool_calls'
    else: status = 'response_unconfirmed'
    return dict(status=status, finish_reason=finish if finish in ('stop','tool_calls','length','content_filter') else 'unknown',
                complete=status == 'complete')


def usage_values(usage):
    def get(key):
        value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        return value if type(value) is int and value >= 0 else None
    return {key:get(key) for key in TOKEN_KEYS}


def find_gateway(client):
    # Existing adapters have explicit ownership links, never infer from model text.
    from .provider_failover import ProviderFailoverClient
    pending, seen = [client], set()
    while pending:
        item = pending.pop()
        if item is None or id(item) in seen: continue
        seen.add(id(item))
        if isinstance(item, ProviderFailoverClient): return item
        pending.extend(getattr(item, name, None) for name in ('client', 'original', 'gateway'))
    return None


def owns_dispatch(client):
    if find_gateway(client) is not None: return True
    pending,seen=[client],set()
    while pending:
        item=pending.pop()
        if item is None or id(item) in seen:continue
        seen.add(id(item))
        if getattr(item,'runtime_dispatch',False) is True:return True
        pending.extend(getattr(item,name,None) for name in ('client','original'))
    return False


def active_config(client, default):
    gateway = find_gateway(client)
    return gateway._backup_config if gateway is not None and gateway.active_provider == 'coco2' else default


async def observe_http(request):
    record = PHYSICAL.get()
    if record is None: return
    if asyncio.current_task().cancelling(): raise asyncio.CancelledError()
    if record['http_dispatch_attempts']:
        raise RuntimeError('unexpected_sdk_retry')
    record['http_dispatch_attempts'] = 1
    ledger=CURRENT.get()
    if ledger is not None and ledger.on_dispatch is not None:ledger.on_dispatch()


async def dispatch(client, config, request, *, is_fallback=False):
    measurement = TokenCounter.enforce(config, request)
    if asyncio.current_task().cancelling(): raise asyncio.CancelledError()
    ledger = CURRENT.get()
    if ledger is None:
        result=await client.chat.completions.create(**request)
        if request.get('stream'):
            from .agent.streaming import consume
            return await consume(result,secrets=(getattr(config,'api_key',None),))
        return result
    hooks = getattr(getattr(client, '_client', None), 'event_hooks', None)
    observable = isinstance(hooks, dict)
    if observable and observe_http not in hooks.setdefault('request', []): hooks['request'].append(observe_http)
    record = {'provider':getattr(config,'provider','unknown'), 'model':getattr(config,'model','unknown'),
              'purpose':ledger.purpose, 'status':'started', 'is_fallback':is_fallback, 'http_dispatch_attempts':0 if observable else None,
              'usage':usage_values(None), **measurement}
    if request.get('stream'):record.update(streaming_requested=True,streaming=False,first_chunk_received=False,output_exposed=False,terminal_trusted=False,stream_status='opening')
    ledger.records.append(record)
    token = PHYSICAL.set(record)
    try:
        if ledger.on_dispatch is not None and ledger.purpose=='agent':ledger.on_dispatch()
        response = await client.chat.completions.create(**request)
        if request.get('stream'):
            from .agent.streaming import consume,OBSERVER
            notify,secrets=OBSERVER.get() or (None,())
            response=await consume(response,record=record,notify=notify,secrets=secrets)
        record.update(status='failed' if getattr(response,'stream_delivery',{}).get('status')=='provider_error' else 'returned', usage=usage_values(getattr(response, 'usage', None)))
        return response
    except asyncio.CancelledError:
        record['status'] = 'cancelled'; raise
    except BaseException:
        record['status'] = 'failed'; raise
    finally:
        PHYSICAL.reset(token)


@dataclass
class RuntimeAccounting:
    on_dispatch: object = None
    logical_requests: int = 0
    compaction_requests: int = 0
    records: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    purpose: str = 'agent'
    outcome: str = 'running'
    observation_errors: int = 0
    output: dict = field(default_factory=dict)
    tool_failures: int = 0
    request_budget_exhausted: bool = False

    async def request(self, client, config, request, *, purpose='agent'):
        effective = active_config(client, config)
        if getattr(effective, 'model', None): request = {**request, 'model':effective.model}
        TokenCounter.enforce(effective, request)
        self.logical_requests += 1
        self.compaction_requests += int(purpose == 'compaction')
        self.purpose = purpose
        token = CURRENT.set(self)
        config_token = CURRENT_CONFIG.set(effective)
        try:
            if owns_dispatch(client):
                return await client.chat.completions.create(**request)
            return await dispatch(client, effective, request)
        finally:
            CURRENT.reset(token)
            CURRENT_CONFIG.reset(config_token)
            self.purpose = 'agent'

    def snapshot(self):
        rows = self.records
        reported = {k:sum(r['usage'][k] for r in rows if r['usage'][k] is not None) for k in TOKEN_KEYS}
        complete = {k:bool(rows) and all(r['usage'][k] is not None for r in rows) for k in TOKEN_KEYS}
        http = sum(r['http_dispatch_attempts'] for r in rows) if rows and all(r['http_dispatch_attempts'] is not None for r in rows) else None
        context = dict(self.context)
        # Report the latest actual agent dispatch, including the backup policy.
        # A summarizer has its own limits and must not replace the task context.
        last_agent = next((r for r in reversed(rows) if r['purpose'] == 'agent'), None)
        if last_agent is not None:
            context.update({key:value for key,value in last_agent.items() if key in context})
        return dict(logical_requests=self.logical_requests, physical_requests=len(rows), http_dispatch_attempts=http,
            http_count_semantics='pre_transport_attempts_not_billing', compaction_requests=self.compaction_requests,
            provider_reported_input_tokens=reported['prompt_tokens'] if complete['prompt_tokens'] else None,
            provider_reported_output_tokens=reported['completion_tokens'] if complete['completion_tokens'] else None,
            provider_reported_total_tokens=reported['total_tokens'] if complete['total_tokens'] else None,
            reported_token_subtotal=reported['total_tokens'], usage_complete=complete['total_tokens'],
            missing_usage_requests=sum(r['usage']['total_tokens'] is None for r in rows),
            fallback_used=any(r['is_fallback'] for r in rows), estimated_cost=None,
            outcome=self.outcome, observation_errors=self.observation_errors, context=context,
            output=dict(self.output), tool_failures=self.tool_failures, task_correctness='unknown',
            request_budget_exhausted=self.request_budget_exhausted)
