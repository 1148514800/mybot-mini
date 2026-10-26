"""Deterministic protocol diagnostics; synthetic packets and SDK MockTransport only."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from openai import AsyncOpenAI,APIConnectionError
from mybot.agent.streaming import consume,StreamCleanupError,StreamErrorCode,OBSERVER
from mybot.runtime_accounting import RuntimeAccounting,usage_values
from scripts.streaming_fixtures import chunk,tool,Stream,Client
from scripts.eventstore_fixtures import configuration
from scripts.uat.budget import BudgetStop

USAGE=dict(prompt_tokens=7,completion_tokens=9,total_tokens=16)
class Checks(unittest.IsolatedAsyncioTestCase):
 async def run_stream(self,packets,code=None,status='provider_error',eof=False):
  s=Stream(packets);events=[]
  with tempfile.TemporaryDirectory() as tmp:
   cfg=configuration(Path(tmp).resolve());client=Client([s]);accounting=RuntimeAccounting();token=OBSERVER.set((events.append,()))
   try:r=await accounting.request(client,cfg,dict(model='synthetic',messages=[dict(role='user',content='synthetic')],stream=True,stream_options={'include_usage':True}))
   finally:OBSERVER.reset(token)
   self.assertEqual(accounting.snapshot()['physical_requests'],1);self.assertEqual(accounting.snapshot()['logical_requests'],1)
   self.assertFalse(accounting.snapshot()['fallback_used']);self.assertEqual(len(client.requests),1)
   record=accounting.records[0]
  self.assertEqual(r.stream_delivery['status'],status);self.assertEqual(record['stream_diagnostic']['error_code'],code)
  self.assertEqual(record['stream_diagnostic']['natural_eof'],eof);self.assertTrue(s.closed)
  self.assertEqual(record['terminal_trusted'],eof and status in ('complete','tool_calls','output_truncated','content_filtered','empty_response'))
  self.assertLessEqual(len(record['stream_diagnostic']['recent_chunks']),8)
  return r,record,events
 async def test_standard(self):await self.run_stream([chunk('hello'),chunk(finish='stop')],None,'complete',True)
 async def test_usage_trailer(self):
  r,_,_=await self.run_stream([chunk('ok',finish='stop'),dict(choices=[],usage=USAGE)],None,'complete',True);self.assertEqual(usage_values(r.usage),USAGE)
 async def test_duplicate_finish_after_stop(self):
  _,r,_=await self.run_stream([chunk('ok',finish='stop'),chunk(finish='stop')],'stream_duplicate_finish');self.assertEqual(r['stream_diagnostic']['terminal_count'],2);self.assertEqual(r['stream_diagnostic']['chunk_index'],2)
 async def test_payload_after_stop(self):await self.run_stream([chunk('ok',finish='stop'),chunk('private-body')],'stream_after_finish_payload')
 async def test_missing_choices(self):await self.run_stream([{}],'stream_choices_invalid')
 async def test_null_choices(self):await self.run_stream([dict(choices=None)],'stream_choices_invalid')
 async def test_wrong_choices(self):await self.run_stream([dict(choices='private')],'stream_choices_invalid')
 async def test_wrong_role(self):
  p=chunk('secret');p['choices'][0]['delta']['role']='private-role';await self.run_stream([p],'stream_role_invalid')
 async def test_multiple_choices(self):
  p=chunk('ok');p['choices']*=2;await self.run_stream([p],'stream_choice_index_invalid')
 async def test_wrong_index(self):
  p=chunk();p['choices'][0]['index']=True;await self.run_stream([p],'stream_choice_index_invalid')
 async def test_content_type(self):await self.run_stream([chunk({'secret':'value'})],'stream_content_type_invalid')
 async def test_fragmented_tool(self):
  r,_,_=await self.run_stream([chunk(tools=[tool(0,'a','read_', '{"path":')]),chunk(tools=[tool(0,name='file',args='"README.md"}')],finish='tool_calls')],None,'tool_calls',True);self.assertEqual(r.choices[0].message.tool_calls[0].function.name,'read_file')
 async def test_bad_arguments(self):
  r,_,_=await self.run_stream([chunk(tools=[tool(0,'a','read_file','{')],finish='tool_calls')],'stream_tool_arguments_invalid',eof=True);self.assertIsNone(r.choices[0].message.tool_calls)
 async def test_tool_index_gap(self):await self.run_stream([chunk(tools=[tool(2,'a','read_file','{}')],finish='tool_calls')],'stream_tool_index_gap',eof=True)
 async def test_invalid_tool_fragment(self):await self.run_stream([chunk(tools=[tool(16,'a','read_file','{}')])],'stream_tool_fragment_invalid')
 async def test_terminal_missing(self):await self.run_stream([chunk('half')],'stream_terminal_missing','response_unconfirmed',True)
 async def test_length(self):await self.run_stream([chunk('half',finish='length')],None,'output_truncated',True)
 async def test_filtered(self):await self.run_stream([chunk('half',finish='content_filter')],None,'content_filtered',True)
 async def test_before_first_network(self):
  s=Stream([APIConnectionError(request=httpx.Request('POST','http://mock.invalid'))]);record={}
  with self.assertRaises(APIConnectionError):await consume(s,record=record)
  self.assertEqual(record['stream_diagnostic']['error_code'],'stream_transport_interrupted');self.assertTrue(s.closed)
 async def test_after_first_network(self):await self.run_stream([chunk('half'),OSError('private exception')],'stream_transport_interrupted')
 async def test_stop_then_network(self):await self.run_stream([chunk('half',finish='stop'),OSError('private exception')],'stream_transport_interrupted')
 async def test_close_failure(self):
  class Bad(Stream):
   async def close(self):raise OSError('PRIVATE-EXCEPTION')
  record={}
  with self.assertRaises(StreamCleanupError):await consume(Bad([chunk('ok',finish='stop')]),record=record)
  d=record['stream_diagnostic'];self.assertEqual(d['error_code'],'stream_close_unconfirmed');self.assertTrue(d['natural_eof']);self.assertFalse(d['closed']);self.assertFalse(record['terminal_trusted']);self.assertNotIn('PRIVATE',json.dumps(d))
 async def test_early_iteration_stop_without_terminal(self):await self.run_stream([],'stream_terminal_missing','response_unconfirmed',True)
 async def test_local_buffer(self):
  r,d,_=await self.run_stream([chunk('x'*32769)],'stream_local_buffer_limit','output_truncated');self.assertLessEqual(len(r.choices[0].message.content),32768);self.assertEqual(d['stream_diagnostic']['origin'],'local_limit')
 async def test_null_usage(self):
  r,_,_=await self.run_stream([chunk('ok',finish='stop'),dict(choices=[],usage=None)],None,'complete',True);self.assertIsNone(usage_values(r.usage)['total_tokens'])
 async def test_cancel_finally(self):
  s=Stream([chunk('x')],delay=10);d={};t=asyncio.create_task(consume(s,record=d));await asyncio.sleep(.01);t.cancel()
  with self.assertRaises(asyncio.CancelledError):await t
  self.assertEqual(d['stream_diagnostic']['error_code'],'stream_user_or_caller_cancelled');self.assertTrue(s.closed)
 async def test_sdk_local_timeout(self):
  s=Stream([TimeoutError('private')]);d={}
  with self.assertRaises(TimeoutError):await consume(s,record=d)
  self.assertEqual(d['stream_diagnostic']['error_code'],'stream_local_timeout');self.assertTrue(s.closed)
 async def test_more_than_328_legal(self):
  r,d,_=await self.run_stream([chunk('x') for _ in range(400)]+[chunk(finish='stop')],None,'complete',True);self.assertEqual(d['stream_diagnostic']['chunks_observed'],401);self.assertEqual(len(r.choices[0].message.content),400)
 async def test_provider_error_frame(self):await self.run_stream([dict(error={'message':'PRIVATE'})],'stream_provider_error_frame')
 async def test_diagnostic_never_contains_text_arguments_errors(self):
  _,d,e=await self.run_stream([chunk(tools=[tool(0,'PRIVATE-ID','read_file','PRIVATE-ARG')],finish='tool_calls')],'stream_tool_arguments_invalid',eof=True)
  self.assertNotIn('PRIVATE',json.dumps(d));self.assertNotIn('PRIVATE',json.dumps(e))
 async def test_ring_is_bounded(self):
  _,d,_=await self.run_stream([chunk('x') for _ in range(1000)]+[chunk(finish='stop'),chunk(finish='stop')],'stream_duplicate_finish');self.assertEqual(len(d['stream_diagnostic']['recent_chunks']),8)
 async def test_budget_guard_not_swallowed(self):
  s=Stream([chunk('half'),BudgetStop('PRIVATE-GUARD')]);d={}
  with self.assertRaises(BudgetStop):await consume(s,record=d)
  self.assertEqual(d['stream_diagnostic']['error_code'],'stream_host_failure');self.assertFalse(d['terminal_trusted']);self.assertNotIn('PRIVATE',json.dumps(d))
 async def test_store_guard_not_swallowed(self):
  from mybot.storage.event_schema import StoreError
  s=Stream([chunk('half'),StoreError('PRIVATE')]);d={}
  with self.assertRaises(StoreError):await consume(s,record=d)
  self.assertEqual(d['stream_diagnostic']['origin'],'host')
 async def test_preview_callback_failure_not_provider(self):
  def bad(e):
   if e['type']=='model_text_delta':raise RuntimeError('PRIVATE')
  with self.assertRaises(RuntimeError):await consume(Stream([chunk('text\n')]),notify=bad)
 async def test_unknown_finish_does_not_leak(self):
  _,d,e=await self.run_stream([chunk('ok',finish='PRIVATE-FINISH')],'stream_terminal_missing','response_unconfirmed',True);self.assertNotIn('PRIVATE',json.dumps(d));self.assertNotIn('PRIVATE',json.dumps(e))
 async def test_tool_argument_limit(self):await self.run_stream([chunk(tools=[tool(0,'a','read_file','x'*65537)])],'stream_local_buffer_limit')
 async def test_finish_with_tools_rejected(self):await self.run_stream([chunk(tools=[tool(0,'a','read_file','{}')],finish='stop')],'stream_tool_arguments_invalid',eof=True)
 async def test_close_failure_keeps_primary(self):
  class Bad(Stream):
   async def close(self):raise OSError('private')
  d={}
  with self.assertRaises(StreamCleanupError):await consume(Bad([chunk('x',finish='stop'),chunk(finish='stop')]),record=d)
  self.assertEqual(d['stream_primary_error_code'],'stream_duplicate_finish')
 async def test_sdk_mocktransport_real_parser(self):
  frames=[chunk('SDK\n',finish='stop'),dict(choices=[],usage=USAGE)]
  async def handler(request):return httpx.Response(200,headers={'content-type':'text/event-stream'},text=''.join('data: '+json.dumps(dict(id='mock',object='chat.completion.chunk',created=1,model='mock',**p))+'\n\n' for p in frames)+'data: [DONE]\n\n')
  with tempfile.TemporaryDirectory() as t:
   cfg=configuration(Path(t));client=AsyncOpenAI(api_key='mock',base_url='http://mock.invalid',http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),max_retries=0);a=RuntimeAccounting()
   r=await a.request(client,cfg,dict(model='mock',messages=[dict(role='user',content='mock')],stream=True,stream_options={'include_usage':True}));await client.close()
   self.assertEqual(len(a.records),1);self.assertEqual(usage_values(r.usage),USAGE);self.assertTrue(a.records[0]['stream_diagnostic']['natural_eof'])

def check_stream_protocol_diagnostics():
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
 if not r.wasSuccessful():raise AssertionError('stream diagnostics failed')
if __name__=='__main__':check_stream_protocol_diagnostics()
