"""Native SDK observation with the C01 registered schema set; original stream observer."""
import asyncio,json,time
from types import SimpleNamespace as N
from mybot.runtime_accounting import CURRENT,PHYSICAL
from scripts.uat.budget import RESERVATION
from scripts.uat.server import private_json
from scripts.streaming_steer_real_uat_v2.adapter import ObservedStream
from scripts.streaming_steer_real_uat_v2.evidence import digest,request_view
from .budget import BudgetStop
from .plan import TOOLS
class BudgetClient:
 def __init__(self,original,config,ledger,case,streams,requests,source_rows,directory=None,barriers=None):
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
  allowed=TOOLS
  if not {v['function']['name'] for v in request.get('tools') or []}<=allowed:raise BudgetStop('unsafe_registry')
  a=CURRENT.get();p=PHYSICAL.get() or {};purpose=a.purpose if a else 'unknown'
  from mybot.agent.token_counter import TokenCounter
  rid=self.ledger.reserve(self.case,self.config.provider,self.config.model,purpose,TokenCounter.measure(request)['estimated_input_tokens'])
  row=dict(case=self.case,reservation=rid,provider=self.config.provider,model=self.config.model,native_is_fallback=p.get('is_fallback',False),sdk_admission_monotonic=time.monotonic(),http_attempts=0,provider_http_response_observed=False,**request_view(request,self.case,self.source_rows()))
  self.requests.append(row);self.save(row);token=RESERVATION.set((self.ledger,rid))
  try:
   raw=await self.original.chat.completions.create(**request);row['provider_http_response_observed']=True;self.save(row)
   stream=ObservedStream(raw,self.ledger,rid,p,request,row,self.directory,0);self.streams.append(stream);return stream
  except BaseException as exc:
   row['opening_failed']=True;row['provider_http_response_observed']=type(getattr(exc,'status_code',None)) is int;self.save(row)
   self.ledger.settle(rid,'cancelled' if isinstance(exc,asyncio.CancelledError) else 'failed',exc=exc);raise
  finally:RESERVATION.reset(token)
 async def close(self):await self.original.close()
