"""Observe immutable SDK chunks, keep reservation until EOF/error/cancel+close."""
import asyncio,hashlib,json,time
from types import SimpleNamespace as N
from mybot.runtime_accounting import CURRENT,usage_values
from mybot.agent.streaming import get
from scripts.uat.budget import RESERVATION
from scripts.uat.server import private_json
from .budget import BudgetStop
from .plan import BARRIER

class ObservedStream:
 def __init__(self,raw,ledger,rid,case,start,request,evidence_dir=None,barrier=None):
  self.raw,self.ledger,self.rid,self.case=raw,ledger,rid,case;self.start=start;self.directory=evidence_dir;self.wait=BARRIER[case] if barrier is None else barrier
  self.closed=False;self.eof=False;self.error=None;self.exception=None;self.text='';self.usage=None;self.finish=None;self.count=0;self.first=None;self.first_text=None;self.waited=0;self.tools=[]
  self.request_hash=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest();self.steer_included=any('用户在本Turn补充' in (m.get('content') or '') for m in request['messages'])
  self.record=dict(reservation=rid,case=case,clock='server_monotonic',request_started=start,request_sha256=self.request_hash,steer_included=self.steer_included)
 async def __aiter__(self):
  try:
   async for chunk in self.raw:
    self.count+=1;now=time.monotonic();choices=get(chunk,'choices') or [];delta=get(choices[0],'delta') if choices else None;content=get(delta,'content')
    reason=get(choices[0],'finish_reason') if choices else None
    if self.first is None:
     self.first=now;self.record.update(first_chunk=now,first_chunk_is_text=bool(content),first_chunk_terminal=reason is not None)
     self.save('first-chunk')
    if isinstance(content,str):
     if content and self.first_text is None:self.first_text=now
     self.text=(self.text+content)[:32768]
    for p in get(delta,'tool_calls') or []:
     name=get(get(p,'function'),'name')
     if name:self.tools.append(name)
    if get(chunk,'usage') is not None:self.usage=get(chunk,'usage')
    if reason is not None:self.finish=reason
    yield chunk  # Original object, order and content unchanged.
    if self.count==1 and reason is None and self.wait:
     began=time.monotonic()
     try:await asyncio.sleep(self.wait)
     finally:self.waited+=time.monotonic()-began
   self.eof=True
  except BaseException as exc:self.error=type(exc).__name__;self.exception=exc;raise
 def save(self,suffix):
  if self.directory:private_json(self.directory/f'{self.case}-{self.rid:02}-{suffix}.json',self.record)
 async def close(self):
  if self.closed:return
  try:
   await asyncio.wait_for(self.raw.close(),2)
  except BaseException:
   self.ledger.halt('stream_cleanup_unconfirmed');raise
  self.closed=True
  if not self.eof and self.error is None:self.error='ConsumptionCancelledOrLocallyStopped'
  usage=self.usage if self.eof and self.finish in ('stop','tool_calls','length','content_filter') else None
  self.record.update(chunks=self.count,first_text=self.first_text,first_chunk_seconds=None if self.first is None else self.first-self.start,finish_reason=self.finish,controlled_barrier_seconds=self.waited,eof=self.eof,closed=True,error_type=self.error,usage=usage_values(usage),assembled_text_sha256=hashlib.sha256(self.text.encode()).hexdigest(),assembled_stripped_sha256=hashlib.sha256(self.text.strip().encode()).hexdigest(),tool_name_fragments=self.tools)
  try:self.save('stream');self.ledger.settle(self.rid,'returned' if self.eof else 'cancelled' if isinstance(self.exception,asyncio.CancelledError) or self.exception is None else 'failed',usage,exc=self.exception)
  except BaseException:self.ledger.halt('evidence_or_settlement_failed');raise

class BudgetClient:
 def __init__(self,original,config,ledger,case,evidence_dir=None,barrier=None,streams=None):
  if original.max_retries!=0:raise BudgetStop('sdk_retry')
  self.original,self.config,self.ledger,self.case=original,config,ledger,case;self._client=original._client;self.evidence_dir=evidence_dir;self.barrier=barrier;self.streams=streams
  self.chat=N(completions=N(create=self.create))
  async def http(request):
   token=RESERVATION.get()
   if token is None or token[0] is not ledger:raise BudgetStop('unreserved_http')
   ledger.http(token[1])
   if self.evidence_dir:private_json(self.evidence_dir/f'{self.case}-{token[1]:02}-http.json',dict(http_started=time.monotonic(),clock='server_monotonic',provider=config.provider,model=config.model,body_sha256=hashlib.sha256(request.content).hexdigest()))
  self._client.event_hooks['request'].insert(0,http)
 async def create(self,**request):
  if self.original.max_retries!=0:raise BudgetStop('sdk_retries_changed')
  accounting=CURRENT.get();purpose=accounting.purpose if accounting else 'unknown'
  if request.get('stream') is not True or request.get('stream_options')!={'include_usage':True}:raise BudgetStop('unregistered_stream_options')
  names={v['function']['name'] for v in request.get('tools') or []}
  if not names<= {'read_file','list_files'}:raise BudgetStop('unsafe_registry')
  from mybot.agent.token_counter import TokenCounter
  rid=self.ledger.reserve(self.case,self.config.provider,self.config.model,purpose,TokenCounter.measure(request)['estimated_input_tokens']);start=time.monotonic();token=RESERVATION.set((self.ledger,rid))
  try:
   raw=await self.original.chat.completions.create(**request)
   observed=ObservedStream(raw,self.ledger,rid,self.case,start,request,self.evidence_dir,self.barrier)
   if self.streams is not None:self.streams.append(observed)
   return observed
  except BaseException as exc:self.ledger.settle(rid,'cancelled' if isinstance(exc,asyncio.CancelledError) else 'failed',exc=exc);raise
  finally:RESERVATION.reset(token)
 async def close(self):await self.original.close()
