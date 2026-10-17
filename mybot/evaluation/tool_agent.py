"""Synthetic tool-agent harness. Golds grade transient observations, never enter live prompts.

No Phase 9 scoring changes. MCP enter/call/exit stay in the same owner Task.
"""
import asyncio
import contextlib
import hashlib
import io
import json
import math
import random
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace as N

from openai import APITimeoutError
from ..agent import AgentLoop, ContextBuilder
from ..agent.context_manager import ContextBudgetError
from ..config import GatewayConfig, PROJECT_DIR, build_client
from ..mcp_client.manager import MCPClientManager
from ..tools import build_default_tool_registry
from .runner import save_report
from scripts.compare_tool_discovery import demo_server

MODES = ('eager','progressive_literal','progressive_hybrid')
TOKEN_KEYS = ('prompt_tokens','completion_tokens','total_tokens','cached_input_tokens')
INCOMPLETE = {'request_budget_exceeded','total_time_exceeded'}


class EvaluationStop(RuntimeError):
    def __init__(self, category): self.category = category


@dataclass(frozen=True)
class Limits:
    max_cases: int = 12
    repeats: int = 1
    max_requests: int = 240
    max_output_tokens: int = 512
    max_react_steps: int = 16
    context_max_chars: int = 160000
    task_timeout: float = 15.0
    total_timeout: float = 240.0
    request_timeout: float = 10.0
    seed: int = 16

    def __post_init__(self):
        for key,low,high in (('max_cases',1,15),('repeats',1,5),('max_requests',1,2000),
                             ('max_output_tokens',1,4096),('max_react_steps',1,30),('context_max_chars',1,500000),('seed',0,2**32-1)):
            value=getattr(self,key)
            if type(value) is not int or not low<=value<=high: raise ValueError('Invalid evaluation limit: '+key)
        for key,high in (('task_timeout',120),('total_timeout',1800),('request_timeout',60)):
            value=getattr(self,key)
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=high:
                raise ValueError('Invalid evaluation time limit: '+key)


def load_cases():
    doc=json.loads((PROJECT_DIR/'evals/tool_agent_cases.json').read_text())
    if doc['version']!=1 or len({c['case_id'] for c in doc['cases']})!=len(doc['cases']):
        raise ValueError('Invalid synthetic cases')
    return doc['cases']


def field(obj,key): return obj.get(key) if isinstance(obj,dict) else getattr(obj,key,None)


def usage_values(usage):
    values={key:field(usage,key) for key in TOKEN_KEYS[:3]}
    details=field(usage,'prompt_tokens_details')
    values['cached_input_tokens']=field(details,'cached_tokens')
    values={k:v if type(v) is int and v>=0 else None for k,v in values.items()}
    if (values['cached_input_tokens'] is not None and values['prompt_tokens'] is not None
            and values['cached_input_tokens']>values['prompt_tokens']): values['cached_input_tokens']=None
    return values


def token_totals(usages, requests):
    return {key:sum(u[key] for u in usages) if usages and len(usages)==requests and all(u[key] is not None for u in usages) else None for key in TOKEN_KEYS}


def validate_prices(prices):
    if prices is None: return None
    allowed={'currency','input_price_per_million','output_price_per_million','cached_input_price_per_million'}
    if not isinstance(prices,dict) or set(prices)-allowed or not {'currency','input_price_per_million','output_price_per_million'}<=prices.keys():
        raise ValueError('Invalid explicit prices')
    if not isinstance(prices['currency'],str) or not re.fullmatch('[A-Z]{3}',prices['currency']): raise ValueError('Invalid currency')
    for key,value in prices.items():
        if key!='currency' and (type(value) not in (int,float) or not math.isfinite(value) or value<0): raise ValueError('Invalid price')
    return dict(prices)


def estimated_cost(tokens,prices):
    if prices is None or any(tokens[k] is None for k in ('prompt_tokens','completion_tokens','cached_input_tokens')): return None
    cached=tokens['cached_input_tokens']
    if cached and 'cached_input_price_per_million' not in prices: return None
    value=((tokens['prompt_tokens']-cached)*prices['input_price_per_million']
           +tokens['completion_tokens']*prices['output_price_per_million']
           +cached*prices.get('cached_input_price_per_million',0))/1000000
    return {'currency':prices['currency'],'amount':value} if math.isfinite(value) else None


def pair_messages(messages, complete=False):
    pending=set(); seen=set()
    for message in messages:
        if message['role']=='assistant' and message.get('tool_calls'):
            if pending: return False
            for call in message['tool_calls']:
                if call['id'] in seen: return False
                seen.add(call['id']);pending.add(call['id'])
        elif message['role']=='tool':
            if message['tool_call_id'] not in pending:return False
            pending.remove(message['tool_call_id'])
        elif pending:return False
    return not pending if complete else True


class Observation:
    def __init__(self,case):
        self.case=case
        self.requests=0; self.usages=[]; self.latencies=[]; self.schemas=[]; self.events=[]
        self.retrieved=set(); self.activated=set(); self.correct=set(); self.errors=[]
        self.terminal=None; self.finished=False; self.paired=True; self.plan_incomplete=False

    def tool(self,name,raw,result):
        try: args=json.loads(raw) if isinstance(raw,str) else raw
        except (ValueError,TypeError):args={}
        args=args if isinstance(args,dict) else {}
        known={req['tool'] for req in self.case['required']}
        safe=name if name in known or name in ('search_mcp_tools','activate_mcp_tools','create_plan','update_plan','read_file','write_file','list_files') else '<other>'
        self.events.append({'name':safe,'success':result.success})
        if name=='search_mcp_tools' and result.success:
            try: self.retrieved.update(m['name'] for m in json.loads(result.output)['matches'])
            except (ValueError,KeyError,TypeError): pass
        if name=='activate_mcp_tools' and result.success:
            # Historical coverage only. Runtime active state remains exclusively in Catalog.
            self.activated.update(args.get('names',[]))
        if result.success:
            for index,req in enumerate(self.case['required']):
                if name==req['tool'] and all(args.get(k)==v for k,v in req['arguments'].items()) and all(f in result.output for f in req['facts']):
                    self.correct.add(index)
        else:
            error=result.error or ''
            if error.startswith('activation_schema_limit'):kind='schema_budget_exceeded'
            elif error.startswith('mcp_tool_not_visible_in_request'):kind='tool_not_visible'
            elif name=='activate_mcp_tools':kind='activation_failed'
            elif name in ('create_plan','update_plan') or 'plan' in error.lower() or 'step' in error.lower():kind='planning_failed'
            elif 'arguments' in error or 'field' in error:kind='invalid_tool_arguments'
            else:kind='tool_execution_failed'
            self.errors.append(kind)


class MeasuringClient:
    def __init__(self,client,observation,budget):
        self.client,self.obs,self.budget=client,observation,budget
        self.chat=N(completions=N(create=self.create))

    async def create(self,**kwargs):
        if time.monotonic()>=self.budget['deadline']:
            self.obs.terminal='total_time_exceeded';raise EvaluationStop(self.obs.terminal)
        if self.budget['used']>=self.budget['maximum']:
            self.obs.terminal='request_budget_exceeded';raise EvaluationStop(self.obs.terminal)
        self.obs.paired &= pair_messages(kwargs['messages'],complete=True)
        self.budget['used']+=1;self.obs.requests+=1
        self.obs.schemas.append(len(json.dumps(kwargs.get('tools') or [],ensure_ascii=False)))
        start=time.perf_counter()
        try:
            response=await self.client.chat.completions.create(**kwargs)
            if not response.choices or not hasattr(response.choices[0].message,'tool_calls'):
                raise EvaluationStop('provider_unsupported')
            self.obs.usages.append(usage_values(getattr(response,'usage',None)))
            return response
        except (TimeoutError,APITimeoutError):
            self.obs.terminal='model_timeout';raise
        except EvaluationStop as exc:
            self.obs.terminal=exc.category;raise
        except asyncio.CancelledError: raise
        except Exception as exc:
            # Inspect only structured status/code; never retain SDK error bodies/URLs.
            code=getattr(exc,'code',None)
            self.obs.terminal=('provider_unsupported' if getattr(exc,'status_code',None) in (400,404,422)
                               and code in ('unsupported_parameter','unsupported_value','model_not_found','function_calling_not_supported') else 'unknown_failure')
            raise EvaluationStop(self.obs.terminal) from None
        finally: self.obs.latencies.append(time.perf_counter()-start)


class MeasuredAgent(AgentLoop):
    def __init__(self,*args,observation,**kwargs):
        self.observation=observation
        super().__init__(*args,**kwargs)

    async def _execute(self,name,raw_arguments):
        result=await super()._execute(name,raw_arguments)
        self.observation.tool(name,raw_arguments,result)
        return result

    def _finish_turn(self,messages,turn_start,reply,reason=''):
        self.observation.finished=not reason
        if reason and '上限' in reason:self.observation.terminal='react_limit'
        if self.plan.steps and any(s.status!='completed' for s in self.plan.steps):
            self.observation.plan_incomplete=True
        return super()._finish_turn(messages,turn_start,reply,reason)


class FixedClient:
    """Predeclared synthetic script. Does not estimate real model competence."""
    def __init__(self,script,progressive):
        self.actions=[]; self.reply=script['reply'];self.index=0;self.last=None
        for step in script['steps']:
            if progressive:
                self.actions.extend([('search_mcp_tools',{'query':step['query']},step['tool']),
                                     ('activate_mcp_tools',{'names':[step['tool']]},None)])
            self.actions.append((step['tool'],step['arguments'],step['facts']))
        self.chat=N(completions=N(create=self.create))

    async def create(self,**kwargs):
        visible={d['function']['name'] for d in kwargs.get('tools') or []}
        if not pair_messages(kwargs['messages'],complete=True):raise AssertionError('Tool result pairing')
        if self.last:
            name,args,expect=self.last
            text=next(m['content'] for m in reversed(kwargs['messages']) if m['role']=='tool')
            if name=='search_mcp_tools':
                # A literal Chinese miss is recorded, not repaired or changed to hybrid.
                self.last_candidates={m['name'] for m in json.loads(text)['matches']}
                if expect not in self.last_candidates:
                    self.actions=[]; self.index=0; self.reply='unavailable'; self.last=None
            elif name.startswith('mcp__') and not all(f in text for f in expect):
                raise AssertionError('Real MCP result does not satisfy fixture')
        if self.index==len(self.actions):return N(choices=[N(message=N(content=self.reply,tool_calls=None))],usage=None)
        name,args,expect=self.actions[self.index]
        if name not in visible:raise AssertionError('Offline script attempted invisible tool')
        self.index+=1;self.last=(name,args,expect)
        return N(choices=[N(message=N(content=None,tool_calls=[N(id=f'synthetic-{self.index}',function=N(name=name,arguments=json.dumps(args)))]))],usage=None)


def contains_fact(text, fact):
    # Stable identifiers/numbers must be whole ASCII tokens: TASK-1 is not TASK-10.
    return bool(re.search(r'(?<![A-Za-z0-9_-])'+re.escape(fact)+r'(?![A-Za-z0-9_-])',text,re.IGNORECASE))


def grade(obs,reply,progressive,audit):
    required={r['tool'] for r in obs.case['required']}
    final=all(contains_fact(reply,f) for f in obs.case['final_required']) and not any(contains_fact(reply,f) for f in obs.case['final_forbidden'])
    if 'final_exact' in obs.case: final = final and reply.strip()==obs.case['final_exact']
    actual=sum(e['executed'] for e in audit)
    calls=(len(obs.correct)==len(obs.case['required']) and actual==len(obs.case['required']))
    if not required: calls=actual==0 and not obs.events
    task=bool(final and calls and obs.finished and obs.terminal is None and obs.paired and not obs.plan_incomplete)
    retrieval=required<=obs.retrieved if progressive and required else None
    activation=required<=obs.activated if progressive and required else None
    causes=[]
    if not task:
        if obs.terminal:causes.append(obs.terminal)
        if retrieval is False:causes.append('retrieval_miss')
        if activation is False:causes.append('activation_failed')
        if not calls:
            causes.extend(obs.errors)
            if any(e['name'] not in required | {'search_mcp_tools','activate_mcp_tools','create_plan','update_plan'} for e in obs.events):causes.append('wrong_tool_selected')
            if not obs.correct and not obs.errors and actual:causes.append('invalid_tool_arguments')
        if obs.plan_incomplete:causes.append('planning_failed')
        if not final:causes.append('incorrect_final_answer')
        if not causes:causes.append('unknown_failure')
    causes=list(dict.fromkeys(causes))
    return {'retrieval_success':retrieval,'activation_success':activation,'tool_call_success':calls,
            'task_success':task,'final_answer_correct':final,'tool_call_ids_paired':obs.paired,
            'failure_category':causes[0] if causes else None,'secondary_failures':causes[1:],
            'recovered_errors':list(dict.fromkeys(obs.errors)) if task else [],'actual_mcp_calls':actual}


def summarize(results,live,prices):
    summary={}
    for mode in dict.fromkeys(r['agent_mode'] for r in results):
        rows=[r for r in results if r['agent_mode']==mode]
        completed=[r for r in rows if r['status']=='complete']
        item={'samples':len(rows),'completed':len(completed),'incomplete':len(rows)-len(completed)}
        for key in ('task_success','tool_call_success','final_answer_correct'):
            item[{'task_success':'task_success_rate','tool_call_success':'tool_call_success_rate','final_answer_correct':'final_answer_accuracy'}[key]]=sum(r[key] for r in completed)/len(completed) if completed else None
        item['retrieval_failure_count']=sum(r['retrieval_success'] is False for r in completed)
        item['activation_failure_count']=sum(r['activation_success'] is False for r in completed)
        for key in ('llm_requests','cumulative_schema_chars','task_wall_time_seconds','request_latency_seconds','tool_calls','tool_failures','search_calls','activate_calls','actual_mcp_calls'):
            item['total_llm_requests' if key=='llm_requests' else key]=sum(r[key] for r in rows)
        item['mean_llm_requests_per_task']=item['total_llm_requests']/len(rows)
        tokens={k:sum(r[k] for r in rows) if all(r[k] is not None for r in rows) else None for k in TOKEN_KEYS}
        item.update(tokens);item['input_tokens']=tokens['prompt_tokens'];item['output_tokens']=tokens['completion_tokens']
        item['estimated_cost']=estimated_cost(tokens,prices) if live else None
        summary[mode]=item
    return summary


def safe_label(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_./-]{1,128}',value) else '<unavailable>'


async def evaluate(*,live=False,confirm_api_cost=False,limits=None,modes=MODES,prices=None,base_config=None,client_factory=None):
    if type(live) is not bool or type(confirm_api_cost) is not bool or live!=confirm_api_cost:
        raise ValueError('Live requires both --live and --confirm-api-cost')
    limits=limits or Limits(); prices=validate_prices(prices)
    modes=tuple(modes)
    if not modes or len(set(modes))!=len(modes) or any(m not in (*MODES,'progressive_bm25') for m in modes):raise ValueError('Invalid agent modes')
    cases=load_cases()[:limits.max_cases]
    neutral=dict(mcp_enabled=False,mcp_servers={},mcp_discovery={'enabled':False},session_persist=False,skills_enabled=False,debug=False)
    base=base_config or GatewayConfig(**neutral,**({} if live else dict(provider='offline',model='fixed-script',api_key=None,base_url=None)))
    common=replace(base,**neutral,context_enabled=True,context_max_chars=limits.context_max_chars,
                   context_tool_result_max_chars=4000,max_react_steps=limits.max_react_steps,
                   max_completion_tokens=limits.max_output_tokens,request_timeout_seconds=limits.request_timeout)
    started=time.monotonic(); budget={'used':0,'maximum':limits.max_requests,'deadline':started+limits.total_timeout}
    results=[];client=None;raw_client=None;stop=None
    try:
        if live:
            raw_client=client_factory(common) if client_factory else build_client(common)
            client=raw_client.with_options(max_retries=0,timeout=limits.request_timeout)
        rng=random.Random(limits.seed)
        for repeat in range(1,limits.repeats+1):
            for case in cases:
                order=list(modes);rng.shuffle(order)
                for mode in order:
                    obs=Observation(case);reply='';audit=[];agent=None
                    task_started=time.perf_counter()
                    if budget['used']>=limits.max_requests:stop='request_budget_exceeded'
                    if time.monotonic()>=budget['deadline']:stop='total_time_exceeded'
                    if stop:obs.terminal=stop
                    else:
                        with tempfile.TemporaryDirectory(prefix='mybot-tool-eval-') as folder:
                            workspace=Path(folder)/'workspace';workspace.mkdir()
                            progressive=mode!='eager'
                            config=replace(common,workspace=workspace,session_path=Path(folder)/'state.json',
                                mcp_enabled=True,mcp_servers={'catalog':demo_server()},
                                mcp_discovery={'enabled':progressive,'retrieval_mode':mode.removeprefix('progressive_') if progressive else 'literal'})
                            tools=build_default_tool_registry(workspace)
                            # timeout surrounds the whole connection lifecycle in THIS owner task.
                            remaining=budget['deadline']-time.monotonic()
                            try:
                                async with asyncio.timeout(min(limits.task_timeout,max(0,remaining))):
                                    async with MCPClientManager(config,tools) as manager:
                                        actual_client=client if live else (client_factory(config,case,mode) if client_factory else FixedClient(case['offline'],progressive))
                                        agent=MeasuredAgent(MeasuringClient(actual_client,obs,budget),config,tools,ContextBuilder(workspace),observation=obs)
                                        try:
                                            with contextlib.redirect_stdout(io.StringIO()):reply=await agent.handle_message(case['prompt'])
                                        finally:audit=manager.audit
                            except TimeoutError:
                                obs.terminal='total_time_exceeded' if time.monotonic()>=budget['deadline'] else 'model_timeout'
                            except ContextBudgetError:obs.terminal='context_budget_exceeded'
                            except EvaluationStop as exc:obs.terminal=exc.category
                            except asyncio.CancelledError: raise
                            except Exception:obs.terminal=obs.terminal or 'unknown_failure'
                            if agent:
                                obs.paired &= pair_messages(agent.session.history(),complete=True)
                                if obs.terminal and agent.session.history():obs.paired=False
                    if obs.terminal in INCOMPLETE:stop=obs.terminal
                    tokens=token_totals(obs.usages,obs.requests) if live else dict.fromkeys(TOKEN_KEYS)
                    score=grade(obs,reply,mode!='eager',audit)
                    incomplete=obs.terminal in INCOMPLETE
                    if incomplete:
                        for key in ('task_success','tool_call_success','final_answer_correct','retrieval_success','activation_success'):score[key]=None
                        score.update(failure_category=obs.terminal,secondary_failures=[])
                    results.append({'case_id':case['case_id'],'repeat':repeat,'agent_mode':mode,'status':'incomplete' if incomplete else 'complete',
                        **score,**tokens,'llm_requests':obs.requests,'request_latency_seconds':sum(obs.latencies),
                        'request_latencies_seconds':list(obs.latencies),'task_wall_time_seconds':time.perf_counter()-task_started,
                        'tool_calls':len(obs.events),'tool_failures':sum(not e['success'] for e in obs.events),
                        'search_calls':sum(e['name']=='search_mcp_tools' for e in obs.events),
                        'activate_calls':sum(e['name']=='activate_mcp_tools' for e in obs.events),
                        'initial_schema_chars':obs.schemas[0] if obs.schemas else None,'cumulative_schema_chars':sum(obs.schemas),
                        'estimated_cost':estimated_cost(tokens,prices) if live else None})
    finally:
        if client is not None:await client.close()
        if raw_client is not None and raw_client is not client:await raw_client.close()
    paired=[]
    for repeat in range(1,limits.repeats+1):
        for case in cases:
            rows=[r for r in results if r['case_id']==case['case_id'] and r['repeat']==repeat]
            if len(rows)==len(modes) and all(r['status']=='complete' for r in rows): paired.append(rows)
    differences={}
    for mode in modes:
        pairs=[{r['agent_mode']:r for r in rows} for rows in paired]
        if mode!='eager' and 'eager' in modes:
            differences[mode]={'pairs':len(pairs),'task_success_delta':sum(int(p[mode]['task_success'])-int(p['eager']['task_success']) for p in pairs)/len(pairs) if pairs else None,
                               'mean_requests_delta':sum(p[mode]['llm_requests']-p['eager']['llm_requests'] for p in pairs)/len(pairs) if pairs else None}
    summary=summarize(results,live,prices)
    case_version=hashlib.sha256((PROJECT_DIR/'evals/tool_agent_cases.json').read_bytes()).hexdigest()
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT_DIR,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):commit=None
    try: dirty=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=PROJECT_DIR,stderr=subprocess.DEVNULL).strip())
    except (OSError,subprocess.CalledProcessError):dirty=None
    return {'mode':'live' if live else 'offline','actual_tokens':{k:sum(r[k] for r in results) if all(r[k] is not None for r in results) else None for k in TOKEN_KEYS} if live else None,
            'actual_cost':None,'live_task_success_rate':{m:s['task_success_rate'] for m,s in summary.items()} if live else None,
            'provider':safe_label(common.provider) if live else 'offline','model':safe_label(common.model) if live else 'fixed-script',
            'git_commit':commit,'worktree_dirty':dirty,'case_sha256':case_version,'configuration':{**limits.__dict__,'modes':list(modes),'temperature':0.1,'sdk_max_retries':0,'prices':prices},
            'sample_count':len(results),'incomplete_count':sum(r['status']=='incomplete' for r in results),
            'complete_paired_cases':len(paired),'paired_differences':differences,'overall':summary,'results':results,
            'limitations':['Fixed scripts validate harness only; no model ability claim.' if not live else 'Provider randomness remains; order seed is not a model seed.',
                          'Missing usage/cache fields remain null. Estimated cost is not a bill or a hard spending cap.']}
