"""Transparent SDK observer; bounded metadata only, native consumer owns diagnosis."""
import asyncio,hashlib,json,time
from types import SimpleNamespace as N
from mybot.runtime_accounting import CURRENT,PHYSICAL,usage_values
from mybot.agent.streaming import get
from scripts.uat.budget import RESERVATION
from scripts.uat.server import private_json
from .budget import BudgetStop

class ObservedStream:
 def __init__(self,raw,ledger,rid,start,physical):
  self.raw,self.ledger,self.rid,self.start,self.physical=raw,ledger,rid,start,physical
  self.closed=False;self.eof=False;self.count=0;self.first=None;self.first_text=None;self.usage=None
  self.digest=hashlib.sha256();self.text="";self.first_sse=None
 async def __aiter__(self):
  async for chunk in self.raw:
   self.count+=1;now=time.monotonic()
   if self.first is None:self.first=now
   choices=get(chunk,'choices');content=None
   if isinstance(choices,list) and choices:content=get(get(choices[0],'delta'),'content')
   if isinstance(content,str):
    if content and self.first_text is None:self.first_text=now
    self.digest.update(content.encode());self.text=(self.text+content)[:32768]
   if get(chunk,'usage') is not None:self.usage=usage_values(get(chunk,'usage'))
   yield chunk
  self.eof=True
 async def close(self):
  if self.closed:return
  try:await asyncio.wait_for(self.raw.close(),2)
  except BaseException:self.ledger.halt('stream_cleanup_unconfirmed');raise
  self.closed=True
  self.ledger.settle(self.rid,'returned' if self.eof else 'failed',self.usage if self.eof else None)
 def evidence(self):
  p=self.physical or {};d=p.get('stream_diagnostic')
  return dict(reservation=self.rid,clock='server_monotonic',request_started=self.start,chunks=self.count,first_chunk=self.first,first_text_chunk=self.first_text,first_sse_preview=self.first_sse,
   first_chunk_seconds=None if self.first is None else self.first-self.start,first_text_seconds=None if self.first_text is None else self.first_text-self.start,
   first_sse_seconds=None if self.first_sse is None else self.first_sse-self.start,natural_eof=self.eof,sdk_closed=self.closed,
   assembled_sha256=self.digest.hexdigest(),assembled_stripped_sha256=hashlib.sha256(self.text.strip().encode()).hexdigest(),stream_status=p.get('stream_status'),terminal_trusted=p.get('terminal_trusted',False),diagnostic=d,
   usage=usage_values(self.usage),observed_usage_fields_complete=all(v is not None for v in usage_values(self.usage).values()),usage_trusted_complete=bool(p.get('terminal_trusted')) and all(v is not None for v in usage_values(self.usage).values()))

class BudgetClient:
 def __init__(self,original,config,ledger,streams,accountings):
  if original.max_retries!=0:raise BudgetStop('sdk_retry')
  self.original,self.config,self.ledger=original,config,ledger;self.streams,self.accountings=streams,accountings;self._client=original._client
  self.chat=N(completions=N(create=self.create))
  async def gate(request):
   reservation=RESERVATION.get()
   if reservation is None or reservation[0] is not ledger:raise BudgetStop('unreserved_http')
   ledger.http(reservation[1])
  self._client.event_hooks['request'].insert(0,gate)
 async def create(self,**request):
  if self.original.max_retries!=0:raise BudgetStop('sdk_retries_changed')
  if request.get('stream') is not True or request.get('stream_options')!={'include_usage':True}:raise BudgetStop('unregistered_stream_options')
  if request.get('tools'):raise BudgetStop('nonempty_registry')
  accounting=CURRENT.get()
  if accounting is not None and not any(x is accounting for x in self.accountings):self.accountings.append(accounting)
  from mybot.agent.token_counter import TokenCounter
  rid=self.ledger.reserve('D02',self.config.provider,self.config.model,accounting.purpose if accounting else 'unknown',TokenCounter.measure(request)['estimated_input_tokens'])
  token=RESERVATION.set((self.ledger,rid));start=time.monotonic()
  try:
   raw=await self.original.chat.completions.create(**request)
   stream=ObservedStream(raw,self.ledger,rid,start,PHYSICAL.get());self.streams.append(stream);return stream
  except BaseException as exc:
   self.ledger.settle(rid,'cancelled' if isinstance(exc,asyncio.CancelledError) else 'failed',exc=exc);raise
  finally:RESERVATION.reset(token)
 async def close(self):await self.original.close()
