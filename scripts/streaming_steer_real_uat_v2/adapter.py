"""Transparent SDK observer. Original chunks unchanged; counters before transport."""
import asyncio,json,time
from types import SimpleNamespace as N
from mybot.runtime_accounting import CURRENT,PHYSICAL,usage_values
from mybot.agent.streaming import get
from scripts.uat.budget import RESERVATION
from scripts.uat.server import private_json
from .budget import BudgetStop
from .plan import BARRIER
from .evidence import digest,request_view

class ObservedStream:
 def __init__(self,raw,ledger,rid,physical,request,row,directory,wait):
  self.raw,self.ledger,self.rid,self.physical=raw,ledger,rid,physical;self.request=request;self.row=row;self.directory=directory;self.wait=wait
  self.closed=False;self.eof=False;self.count=0;self.first=None;self.first_text=None;self.usage=None;self.text='';self.first_delivered=False;self.waited=0;self.settled=False
 def save(self,suffix='stream'):
  if self.directory:private_json(self.directory/f'{self.row["case"]}-{self.rid:02}-{suffix}.json',self.evidence())
 async def __aiter__(self):
  async for chunk in self.raw:
   self.count+=1;now=time.monotonic();choices=get(chunk,'choices') or [];choice=choices[0] if isinstance(choices,list) and choices else None;content=get(get(choice,'delta'),'content');reason=get(choice,'finish_reason')
   if self.first is None:self.first=now;self.row['first_chunk_terminal']=reason is not None;self.save('first-chunk')
   if isinstance(content,str):
    if content and self.first_text is None:self.first_text=now
    self.text=(self.text+content)[:32768]
   if get(chunk,'usage') is not None:self.usage=usage_values(get(chunk,'usage'))
   yield chunk
   if self.count==1 and reason is None:
    self.first_delivered=True;self.row['first_nonterminal_delivery_monotonic']=time.monotonic();self.save('first-delivered')
    if self.wait:
     began=time.monotonic()
     try:await asyncio.sleep(self.wait)
     finally:self.waited+=time.monotonic()-began
  self.eof=True
 async def close(self):
  if self.closed:return
  try:await asyncio.wait_for(self.raw.close(),2)
  except BaseException:self.ledger.halt('stream_cleanup_unconfirmed');raise
  self.closed=True;self.row['sdk_request_unchanged_at_close']=digest(self.request)==self.row['sdk_request_sha256']
 def finalize(self):
  # Native consumer assigns terminal_trusted AFTER close. Finalize at next SDK
  # admission or turn settlement, never promote observer Usage before validation.
  if self.settled:return
  if not self.closed:raise BudgetStop('stream_cleanup_unconfirmed')
  trusted=self.eof and self.physical.get('terminal_trusted') is True
  cancelled=(self.physical.get('stream_diagnostic') or {}).get('error_code')=='stream_user_or_caller_cancelled'
  self.ledger.settle(self.rid,'returned' if trusted else 'cancelled' if cancelled else 'failed',self.usage if trusted else None)
  self.settled=True;self.save()
 def evidence(self):
  p=self.physical or {}
  return dict(**self.row,chunks=self.count,first_chunk=self.first,first_text=self.first_text,first_nonterminal_delivered=self.first_delivered,
   controlled_barrier_seconds=self.waited,barrier_planned_seconds=self.wait,natural_eof=self.eof,sdk_closed=self.closed,terminal_trusted=p.get('terminal_trusted',False),stream_status=p.get('stream_status'),diagnostic=p.get('stream_diagnostic'),
   observed_usage=usage_values(self.usage),settled_usage=usage_values(self.usage if self.settled and p.get('terminal_trusted') else None),reply_sha256=digest(self.text.strip()))

class BudgetClient:
 def __init__(self,original,config,ledger,case,streams,requests,source_rows,directory=None,barriers=BARRIER):
  if original.max_retries!=0:raise BudgetStop('sdk_retry')
  self.original,self.config,self.ledger,self.case=original,config,ledger,case;self.streams,self.requests,self.source_rows,self.directory=streams,requests,source_rows,directory;self.barriers=barriers;self._client=original._client
  self.chat=N(completions=N(create=self.create))
  async def gate(request):
   token=RESERVATION.get()
   if token is None or token[0] is not ledger:raise BudgetStop('unreserved_http')
   ledger.http(token[1]);row=next(x for x in self.requests if x['reservation']==token[1]);body=json.loads(request.content)
   row.update(http_attempts=1,http_dispatch_monotonic=time.monotonic(),wire_body_sha256=digest(body),wire_messages_match_sdk=digest(body.get('messages'))==row['sdk_messages_sha256'])
   self.save(row)
  self._client.event_hooks['request'].insert(0,gate)
 def save(self,row):
  if self.directory:private_json(self.directory/f'{self.case}-{row["reservation"]:02}-request.json',row)
 async def create(self,**request):
  for stream in self.streams:
   if not stream.settled:stream.finalize()
  if self.original.max_retries!=0:raise BudgetStop('sdk_retries_changed')
  if request.get('stream') is not True or request.get('stream_options')!={'include_usage':True}:raise BudgetStop('unregistered_stream_options')
  allowed={'read_file','list_files'} if self.case=='T01' else set()
  if not {v['function']['name'] for v in request.get('tools') or []}<=allowed:raise BudgetStop('unsafe_registry')
  a=CURRENT.get();p=PHYSICAL.get() or {};purpose=a.purpose if a else 'unknown'
  from mybot.agent.token_counter import TokenCounter
  rid=self.ledger.reserve(self.case,self.config.provider,self.config.model,purpose,TokenCounter.measure(request)['estimated_input_tokens'])
  row=dict(case=self.case,reservation=rid,provider=self.config.provider,model=self.config.model,native_is_fallback=p.get('is_fallback',False),sdk_admission_monotonic=time.monotonic(),http_attempts=0,provider_http_response_observed=False,**request_view(request,self.case,self.source_rows()))
  self.requests.append(row);self.save(row);token=RESERVATION.set((self.ledger,rid))
  try:
   raw=await self.original.chat.completions.create(**request);row['provider_http_response_observed']=True;self.save(row)
   stream=ObservedStream(raw,self.ledger,rid,p,request,row,self.directory,self.barriers[self.case] if not any(s.count for s in self.streams) else 0);self.streams.append(stream);return stream
  except BaseException as exc:
   row['opening_failed']=True;row['provider_http_response_observed']=type(getattr(exc,'status_code',None)) is int;self.save(row)
   self.ledger.settle(rid,'cancelled' if isinstance(exc,asyncio.CancelledError) else 'failed',exc=exc);raise
  finally:RESERVATION.reset(token)
 async def close(self):await self.original.close()
