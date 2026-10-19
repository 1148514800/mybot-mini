"""Request/time/estimated-cost gates around the existing SDK and metadata Trace."""
from dataclasses import dataclass
import asyncio
import hashlib
import math
import sys
import time
from types import SimpleNamespace as N

from openai import APITimeoutError
from ..config import build_client
from ..tools.command_process import resolve_launch
from ..tools import macos_sandbox
from .trace import TracedClient, RequestLimitError
from .tool_agent import usage_values, token_totals, validate_prices, estimated_cost, safe_label, pair_messages


class CodingEvaluationStop(RuntimeError):
    def __init__(self, category): self.category = category; super().__init__(category)


@dataclass(frozen=True)
class Limits:
    max_cases: int = 2
    repeats: int = 1
    max_requests: int = 24
    max_model_requests_per_case: int = 12
    max_output_tokens: int = 2048
    task_timeout: float = 240
    total_timeout: float = 900
    request_timeout: float = 45
    judge_timeout: float = 10
    seed: int = 24

    def __post_init__(self):
        for name,low,high in [('max_cases',1,12),('repeats',1,5),('max_requests',1,240),
            ('max_model_requests_per_case',1,30),('max_output_tokens',1,8192),('seed',0,2**32-1)]:
            value=getattr(self,name)
            if type(value) is not int or not low<=value<=high: raise ValueError('invalid_limit_'+name)
        for name,high in [('task_timeout',600),('total_timeout',3600),('request_timeout',120),('judge_timeout',60)]:
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not .01<=value<=high:
                raise ValueError('invalid_limit_'+name)


class RequestBudget:
    def __init__(self, limits, prices=None, max_cost=None):
        self.limits=limits; self.prices=validate_prices(prices); self.max_cost=max_cost
        if max_cost is not None and (type(max_cost) not in (int,float) or not math.isfinite(max_cost) or max_cost<=0 or prices is None):
            raise ValueError('invalid_estimated_cost_limit')
        self.state={'used':0,'maximum':limits.max_requests}
        self.deadline=time.monotonic()+limits.total_timeout
        self.usages=[];self.successes=0;self.api_failures=0

    @property
    def tokens(self):return token_totals(self.usages,self.state['used'])

    def check(self):
        if time.monotonic()>=self.deadline: raise CodingEvaluationStop('total_timeout')
        if self.state['used']>=self.state['maximum']: raise CodingEvaluationStop('model_request_budget')
        if self.max_cost is not None and self.state['used']:
            cost=estimated_cost(self.tokens,self.prices)
            if cost is None: raise CodingEvaluationStop('unknown_estimated_cost')
            if cost['amount']>=self.max_cost: raise CodingEvaluationStop('estimated_cost_budget')


class CodingClient:
    """Original TracedClient counts attempts; this adapter adds aggregate gates."""
    def __init__(self, raw, trace, budget):
        self.trace=trace;self.budget=budget;self.original=TracedClient(raw,trace,budget.state);self.ids=set()
        self.chat=N(completions=N(create=self.create))

    async def create(self, **kwargs):
        self.budget.check()
        self.trace.paired &= pair_messages(kwargs['messages'],complete=True)
        event_start=len(self.trace.events)
        prior_usage=len(self.trace.usage)
        try:
            response=await self.original.create(**kwargs)
            message=response.choices[0].message
            if not hasattr(message,'tool_calls') or not hasattr(message,'content'):
                raise CodingEvaluationStop('provider_unsupported')
            calls=message.tool_calls
            if getattr(message,'function_call',None) is not None and not calls:
                raise CodingEvaluationStop('provider_unsupported')
            if calls is not None and not isinstance(calls,(list,tuple)):
                raise CodingEvaluationStop('provider_unsupported')
            if any(not isinstance(c.id,str) or not isinstance(c.function.name,str) or not isinstance(c.function.arguments,str) for c in calls or []):
                raise CodingEvaluationStop('provider_unsupported')
            ids=[c.id for c in calls or []]
            if len(ids)>32 or any(not value or len(value)>256 or value in self.ids for value in ids) or len(set(ids))!=len(ids):
                raise CodingEvaluationStop('provider_unsupported')
            if (message.content is not None and (not isinstance(message.content,str) or len(message.content)>65536)) or sum(len(c.function.arguments) for c in calls or [])>131072:
                raise CodingEvaluationStop('provider_unsupported')
            self.ids.update(ids)
            self.budget.successes+=1
            self.trace.events[-1]['output_sha256']=hashlib.sha256((message.content or '').encode()).hexdigest()
            return response
        except asyncio.CancelledError: raise
        except (TimeoutError,APITimeoutError):
            self.budget.api_failures+=1
            raise CodingEvaluationStop('provider_timeout') from None
        except CodingEvaluationStop:
            self.budget.api_failures+=1
            raise
        except (AttributeError,IndexError,TypeError):
            self.budget.api_failures+=1
            raise CodingEvaluationStop('provider_unsupported') from None
        except RequestLimitError:
            raise CodingEvaluationStop('model_request_budget') from None
        except Exception as exc:
            self.budget.api_failures+=1
            unsupported=(getattr(exc,'status_code',None) in (400,404,422) and getattr(exc,'code',None) in
                ('unsupported_parameter','unsupported_value','model_not_found','function_calling_not_supported'))
            raise CodingEvaluationStop('provider_unsupported' if unsupported else 'provider_error') from None
        finally:
            for event in self.trace.events[event_start:]:
                if event['event']=='llm_request':event['schema_chars']=len(__import__('json').dumps(kwargs.get('tools') or [],ensure_ascii=False))
            if len(self.trace.usage)>prior_usage:
                self.budget.usages.append(usage_values(self.trace.usage[-1]))


def labels(config):
    from .artifacts import redact
    result={}
    for key,value in [('provider',config.provider),('model',config.model)]:
        value=value if isinstance(value,str) else ''
        result[key]=safe_label(value) if value and not value.startswith('/') and redact(value,(config.api_key,))==value else '<unavailable>'
    return result


async def live_client(config, limits, *, live, confirm_api_cost, cases, prices):
    # No SDK construction, network or silent offline fallback until both explicit gates.
    if live is not True or confirm_api_cost is not True: raise ValueError('live_requires_cost_confirmation')
    if not config.api_key or config.api_key.startswith('YOUR_'): raise ValueError('missing_credentials')
    if not sys.stdin.isatty() or not sys.stdout.isatty(): raise ValueError('live_requires_tty')
    runtime=resolve_launch(('python','-m','unittest'),config.workspace)
    if not await macos_sandbox.verify_sandbox(runtime.roots): raise ValueError('sandbox_unavailable')
    import json
    print(json.dumps({'mode':'LIVE','provider':labels(config)['provider'],'model':labels(config)['model'],
        'cases':cases,'repeats':limits.repeats,'global_request_limit':limits.max_requests,
        'total_timeout':limits.total_timeout,'prices_configured':prices is not None,
        'command_approval':'each invocation requires human approval','sandbox':'macos_readonly verified'},ensure_ascii=True))
    # build_client already sets max_retries=0 for autonomy; pin it again explicitly.
    client=None
    try:
        client=build_client(config)
        return client.with_options(max_retries=0,timeout=limits.request_timeout)
    except Exception:
        if client is not None: await client.close()
        raise CodingEvaluationStop('provider_setup_error') from None
