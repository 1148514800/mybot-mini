"""Explicit mixed-provider adapter for the original Coding Harness, not a new agent."""
import asyncio
import copy
from dataclasses import replace
import hashlib
import math
import time
from types import SimpleNamespace as N

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIStatusError, APIResponseValidationError
from ..provider_failover import ProviderFailoverClient, FallbackBudgetExceeded
from ..config import GatewayConfig, build_client
from .coding_live import CodingClient, CodingEvaluationStop, labels
from .tool_agent import usage_values, token_totals

POLICY = 'network-timeout-429-500-502-503-504-v1'


def error_category(exc):
    if isinstance(exc, asyncio.CancelledError): return 'cancelled'
    if isinstance(exc, (TimeoutError, APITimeoutError)): return 'request_timeout'
    if isinstance(exc, APIConnectionError):
        return 'local_programming_error' if isinstance(exc.__cause__,(TypeError,ValueError,RuntimeError)) else 'connection_error'
    if isinstance(exc, APIResponseValidationError): return 'protocol_error'
    if isinstance(exc, APIStatusError):
        return {400:'parameter_error',401:'authentication_error',403:'permission_error',429:'rate_limit'}.get(
            exc.status_code, 'server_error' if 500 <= exc.status_code <= 599 else 'http_error')
    return 'local_programming_error'


def recoverable(exc):
    if isinstance(exc, APIConnectionError) and isinstance(exc.__cause__,(TypeError,ValueError,RuntimeError)):
        return False
    return (isinstance(exc, (APIConnectionError, APITimeoutError, TimeoutError))
        or isinstance(exc, APIStatusError) and exc.status_code in (429,500,502,503,504))


def settings(base, *, live, backup=None):
    from ..config import _PROVIDERS
    from .artifacts import redact
    raw = backup if backup is not None else (_PROVIDERS.get('coco2', {}) if isinstance(_PROVIDERS,dict) else {})
    if base.provider != 'coco': raise ValueError('failover_requires_coco')
    if not isinstance(raw,dict): raise ValueError('invalid_backup_configuration')
    model = raw.get('model') or ('glm-5.3-flash' if not live else None)
    secondary = replace(base,provider='coco2',model=model,api_key=raw.get('api_key') if live else None,
        base_url=raw.get('base_url') if live else None)
    known_keys=(base.api_key,secondary.api_key,raw.get('api_key'),*(
        value.get('api_key') for value in (_PROVIDERS.values() if isinstance(_PROVIDERS,dict) else ()) if isinstance(value,dict)))
    known_keys=tuple(value for value in known_keys if isinstance(value,str))
    for cfg in (base,secondary):
        if not isinstance(cfg.model,str) or not cfg.model or redact(cfg.model,known_keys)!=cfg.model or labels(cfg)['model']=='<unavailable>':
            raise ValueError('invalid_provider_labels')
        if live and (not isinstance(cfg.api_key,str) or not cfg.api_key or cfg.api_key.startswith('YOUR_') or not isinstance(cfg.base_url,str) or not cfg.base_url):
            raise ValueError('missing_provider_configuration')
    return base,secondary


class FailoverCodingClient(CodingClient):
    """The existing logical trace plus before-dispatch physical accounting/fences."""
    def __init__(self, configs, trace, budget, attempt, case_id, factory, *, live=False):
        self.configs=configs;self.attempt=attempt;self.case_id=case_id;self.factory=factory
        self.controller=lambda:None;self.logical=0;self.records=[];self.stops=[];self.deadline=0
        self.transition=False;self.current=None;self.clients=[]
        self.transport_fault=False
        self._budget=budget
        self.live=live
        primary=self.wrap(factory(configs[0]),configs[0])
        gateway=ProviderFailoverClient(primary,configs[0],configs[1],
            lambda cfg:self.wrap(factory(cfg),cfg),recoverable=lambda exc:recoverable(exc) and not self.transport_fault)
        gateway.before_fallback=self.reserve_fallback
        self.gateway=gateway
        super().__init__(gateway,trace,budget)
        # TracedClient counts logical requests ONLY. The global state is reserved
        # by wrap() immediately before each SDK create, including fallback.
        self.original.budget={'used':0,'maximum':budget.limits.max_requests}

    def fence(self):
        self.attempt.check()
        c=self.controller()
        if c is not None and not c.check_time():
            self.stops.append({'logical_request':self.logical,'reason':c.stop_reason,'phase':'controller_deadline_gate'})
            raise FallbackBudgetExceeded()
        if time.monotonic() >= min(self.deadline or math.inf,self._budget.deadline):
            self.stops.append({'logical_request':self.logical,'reason':'total_timeout' if time.monotonic()>=self._budget.deadline else 'request_timeout','phase':'deadline_gate'})
            raise TimeoutError()

    def reserve_fallback(self, definitions):
        self.fence()
        c=self.controller()
        try:self._budget.check()
        except CodingEvaluationStop as exc:
            self.stops.append({'logical_request':self.logical,'reason':exc.category,'phase':'fallback_gate'})
            if c is not None:
                c.stop('budget_exhausted' if exc.category=='model_request_budget' else 'blocked',exc.category)
                raise FallbackBudgetExceeded() from None
            raise
        if c is not None and not c.before_request(definitions):
            self.stops.append({'logical_request':self.logical,'reason':c.stop_reason,'phase':'controller_gate'})
            return False
        self.transition=True
        return True

    def wrap(self, raw, cfg):
        if hasattr(raw,'with_options'):raw=raw.with_options(max_retries=0)
        self.clients.append(raw)
        hooks=getattr(getattr(raw,'_client',None),'event_hooks',None)
        observed=isinstance(hooks,dict)
        if observed:
            async def on_http(request):
                self.fence()
                record=self.current
                if record is None or record['provider']!=cfg.provider or record['http_dispatch_count']:
                    self.transport_fault=True
                    raise RuntimeError('unexpected_transport_retry')
                if request.method!='POST' or not request.url.path.endswith('/chat/completions'):
                    self.transport_fault=True
                    raise RuntimeError('unexpected_transport_endpoint')
                record['http_dispatch_count']+=1
            hooks.setdefault('request',[]).append(on_http)

        async def create(**kwargs):
            self.fence();self._budget.check()
            if kwargs.get('model')!=cfg.model:raise CodingEvaluationStop('provider_unsupported')
            self._budget.state['used']+=1
            record=dict(case_id=self.case_id,attempt_id=self.attempt.identity['attempt_id'],
                logical_request=self.logical,physical_request=len(self.records)+1,
                global_physical_request=self._budget.state['used'],provider=cfg.provider,model=labels(cfg)['model'],
                is_fallback=cfg.provider=='coco2',fallback_transition=self.transition and cfg.provider=='coco2',
                phase='sdk_create',status='started',error_category=None,http_status=None,
                execution_mode='live' if self.live else 'offline_synthetic',
                client_kind='openai_sdk' if isinstance(raw,AsyncOpenAI) else 'synthetic_client',
                http_dispatch_count=0 if observed else None,budget_or_deadline_stop=False,usage=usage_values(None))
            self.transition=False
            self.records.append(record);self.current=record;started=time.monotonic()
            try:
                c=self.controller();remaining=min(self.deadline,self._budget.deadline)-time.monotonic()
                if c is not None:remaining=min(remaining,c.remaining_seconds)
                async with asyncio.timeout(max(.000001,remaining)):
                    response=await raw.chat.completions.create(**kwargs)
                self.fence()
                record.update(status='returned',usage=usage_values(getattr(response,'usage',None)))
                return response
            except BaseException as exc:
                record.update(status='cancelled' if isinstance(exc,asyncio.CancelledError) else 'error',error_category='protocol_error' if self.transport_fault else error_category(exc))
                status=getattr(exc,'status_code',None)
                if type(status) is int and 100<=status<=599:record['http_status']=status
                record['budget_or_deadline_stop']=isinstance(exc,(TimeoutError,APITimeoutError,asyncio.CancelledError,FallbackBudgetExceeded))
                raise
            finally:
                record['duration_seconds']=round(time.monotonic()-started,6)
                self.current=None
        async def close():
            closing=getattr(raw,'close',None)
            if closing is not None:await closing()
        return N(chat=N(completions=N(create=create)),close=close)

    async def create(self, **kwargs):
        self.attempt.check();self.logical+=1
        self.deadline=min(time.monotonic()+self.configs[0].request_timeout_seconds,self._budget.deadline)
        c=self.controller()
        if c is not None:self.deadline=min(self.deadline,time.monotonic()+max(0,c.remaining_seconds))
        try:return await super().create(**kwargs)
        except CodingEvaluationStop as exc:
            if exc.category=='provider_unsupported' and self.records:
                self.records[-1].update(status='protocol_rejected',error_category='protocol_error')
            raise

    async def close(self):await self.gateway.close()

    def summary(self):
        records=copy.deepcopy(self.records)
        transitions=[r for r in records if r['fallback_transition']]
        counts={p:sum(r['provider']==p for r in records) for p in ('coco','coco2')}
        http=sum(r['http_dispatch_count'] for r in records) if all(r['http_dispatch_count'] is not None for r in records) else None
        return dict(policy=POLICY,logical_model_requests=self.logical,physical_model_requests=len(records),
            physical_requests_by_provider=counts,http_model_requests=http,
            http_count_semantics='pre_transport_dispatch_attempts; not billing confirmation' if http is not None else 'unknown',
            fallback_attempts=len(transitions),fallback_successes=sum(r['status']=='returned' for r in transitions),
            fallback_failures=sum(r['status']!='returned' for r in transitions),
            active_provider=self.gateway.active_provider,requests=records,stops=copy.deepcopy(self.stops),estimated_cost=None)

    def metric_fields(self):
        summary=self.summary();tokens=token_totals([r['usage'] for r in self.records],len(self.records))
        return {**{k:summary[k] for k in ('logical_model_requests','physical_model_requests','physical_requests_by_provider',
            'fallback_attempts','fallback_successes','fallback_failures')},'llm_requests':len(self.records),
            'input_tokens':tokens['prompt_tokens'],'output_tokens':tokens['completion_tokens'],
            'total_tokens':tokens['total_tokens'],'cached_input_tokens':tokens['cached_input_tokens']}


async def evaluate(*, provider_mode='single', offline_provider_factory=None, backup_config=None, **kwargs):
    from .coding_benchmark import evaluate as original, OfflineClient
    if provider_mode not in ('single','failover'):raise ValueError('invalid_provider_mode')
    live=kwargs.get('live',False)
    if live and (offline_provider_factory is not None or backup_config is not None):
        raise ValueError('live_forbids_synthetic_overrides')
    if provider_mode=='single':
        if offline_provider_factory is not None or backup_config is not None:raise ValueError('single_forbids_backup_overrides')
        return await original(**kwargs)
    if kwargs.get('prices') is not None or kwargs.get('max_estimated_cost') is not None:
        raise ValueError('mixed_model_prices_require_per_model_accounting')
    base=kwargs.pop('base_config',None) or GatewayConfig(**({} if live else dict(provider='coco',model='deepseek-v4.1-flash',api_key=None,base_url=None)))
    _,backup=settings(base,live=live,backup=backup_config)
    def adapter(runtime,config,trace,budget,attempt):
        secondary=replace(config,provider='coco2',model=backup.model,api_key=backup.api_key,base_url=backup.base_url)
        if live:factory=lambda cfg:build_client(cfg)
        else:factory=lambda cfg:offline_provider_factory(runtime,cfg.provider) if offline_provider_factory else OfflineClient()
        return FailoverCodingClient((config,secondary),trace,budget,attempt,runtime.id,factory,live=live)
    report=await original(base_config=base,_adapter_factory=adapter,**kwargs)
    executions=[r['provider_execution'] for r in report['results'] if 'provider_execution' in r]
    http_count=sum(r['http_model_requests'] for r in executions) if all(r['http_model_requests'] is not None for r in executions) else None
    report.update(report_type='coding_failover_benchmark',provider_mode='failover',provider_policy=POLICY,
        logical_model_requests=sum(r['logical_model_requests'] for r in executions),
        physical_model_requests=sum(r['physical_model_requests'] for r in executions),
        physical_requests_by_provider={p:sum(r['physical_requests_by_provider'][p] for r in executions) for p in ('coco','coco2')},
        http_model_requests=http_count,
        **{k:sum(r[k] for r in executions) for k in ('fallback_attempts','fallback_successes','fallback_failures')},
        model_name='mixed',provider_label='mixed',estimated_cost=None,estimated_cost_per_success=None,
        cost_semantics='Mixed model cost unknown without reliable per-model prices and usage.')
    for r in report['results']:r['estimated_cost']=None
    return report
