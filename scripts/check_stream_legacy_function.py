"""Raw SDK SSE regression: no real provider, keys, user workspace or Live DB."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from openai.types.chat.chat_completion_chunk import ChoiceDeltaFunctionCall
from scripts.legacy_stream_fixtures import MISSING,USAGE,packets,client
from scripts.streaming_fixtures import chunk,Stream
from scripts.eventstore_fixtures import configuration
from mybot.agent.streaming import consume,_legacy
from mybot.runtime_accounting import RuntimeAccounting,usage_values

class Checks(unittest.IsolatedAsyncioTestCase):
 async def sdk(self,value=MISSING,*,frames=None,code=None,usage=True,count=221):
  requests=[];sdk=client(packets(value,count=count,usage=usage) if frames is None else frames,requests);a=RuntimeAccounting()
  with tempfile.TemporaryDirectory() as t:
   try:r=await a.request(sdk,configuration(Path(t).resolve()),dict(model='synthetic',messages=[dict(role='user',content='synthetic')],stream=True,stream_options={'include_usage':True}))
   finally:await sdk.close()
  d=a.records[0]['stream_diagnostic'];self.assertEqual(len(requests),1);self.assertEqual(a.snapshot()['physical_requests'],1);self.assertEqual(a.snapshot()['http_dispatch_attempts'],1);self.assertEqual(d['error_code'],code);self.assertTrue(d['closed']);self.assertLessEqual(len(d['recent_chunks']),8)
  if code is None:self.assertTrue(d['natural_eof']);self.assertTrue(a.records[0]['terminal_trusted']);self.assertEqual(r.stream_delivery['status'],'complete')
  else:self.assertFalse(a.records[0]['terminal_trusted']);self.assertIsNone(r.choices[0].message.tool_calls);self.assertIsNone(usage_values(r.usage)['total_tokens'])
  self.assertNotIn('PRIVATE',json.dumps(d));return r,d,a
 async def test_synthetic_221_empty_sdk(self):
  r,d,a=await self.sdk({});self.assertEqual(d['chunks_observed'],222);self.assertEqual(d['terminal_count'],1);self.assertEqual(d['finish_reason'],'stop');self.assertEqual(usage_values(r.usage),USAGE);self.assertTrue(a.snapshot()['usage_complete']);self.assertEqual(d['recent_chunks'][-2]['legacy_function_call_kind'],'object')
 async def test_synthetic_221_real_legacy(self):
  _,d,_=await self.sdk({'name':'PRIVATE-NAME'},code='stream_legacy_function_call_unsupported');self.assertEqual(d['chunk_index'],221);self.assertFalse(d['natural_eof'])
 async def test_221_without_usage(self):
  r,d,_=await self.sdk({},usage=False);self.assertEqual(d['chunks_observed'],221);self.assertIsNone(usage_values(r.usage)['total_tokens'])
 async def test_sdk_missing_vs_null_fields_set(self):
  for raw,present in [(MISSING,False),(None,True),({},True)]:
   requests=[]
   async with client(packets(raw,count=2,usage=False),requests) as sdk:
    stream=await sdk.chat.completions.create(model='synthetic',messages=[dict(role='user',content='synthetic')],stream=True)
    parsed=[p async for p in stream];await stream.close();delta=parsed[-1].choices[0].delta
    self.assertEqual('function_call' in delta.model_fields_set,present)
    if raw=={}:
     self.assertIsInstance(delta.function_call,ChoiceDeltaFunctionCall);self.assertTrue(bool(delta.function_call));self.assertEqual(delta.function_call.model_fields_set,set());self.assertIsNone(delta.function_call.name);self.assertIsNone(delta.function_call.arguments)
 async def test_pydantic_direct_empty_object(self):
  p=chunk('ok',finish='stop');p['choices'][0]['delta']['function_call']=ChoiceDeltaFunctionCall()
  d={};r=await consume(Stream([p]),record=d);self.assertTrue(d['terminal_trusted']);self.assertTrue(d['stream_diagnostic']['recent_chunks'][0]['legacy_semantically_empty'])
 async def test_real_postfinish_code(self):await self.sdk(frames=[chunk('ok',finish='stop'),chunk('PRIVATE-CONTENT')],code='stream_after_finish_payload')
 async def test_postfinish_tools(self):
  from scripts.streaming_fixtures import tool
  await self.sdk(frames=[chunk('ok',finish='stop'),chunk(tools=[tool(0,'call','PRIVATE-NAME','PRIVATE-ARGS')])],code='stream_after_finish_payload')
 async def test_duplicate_finish_empty_legacy(self):
  p=chunk(finish='stop');p['choices'][0]['delta']['function_call']={}
  await self.sdk(frames=[chunk('ok',finish='stop'),p],code='stream_duplicate_finish')
 async def test_empty_after_finish_no_semantic_payload(self):
  p=chunk('');p['choices'][0]['delta']['function_call']={}
  await self.sdk(frames=[chunk('ok',finish='stop'),p,dict(choices=[],usage=USAGE)])
 async def test_nonempty_after_finish_legacy_distinct(self):
  p=chunk('');p['choices'][0]['delta']['function_call']={'name':'PRIVATE'}
  await self.sdk(frames=[chunk('ok',finish='stop'),p],code='stream_legacy_function_call_unsupported')
 async def test_legacy_on_usage_only_trailer_not_ignored(self):
  # No choice delta exists on a legitimate empty-choices trailer, so no legacy payload can be promoted.
  r,d,_=await self.sdk({},count=2);self.assertEqual(d['recent_chunks'][-1]['legacy_function_call_present'],False)
 async def test_ring_lengths_bounded(self):
  _,d,_=await self.sdk({'name':'PRIVATE'+'x'*70000},code='stream_legacy_function_call_unsupported',count=2)
  self.assertEqual(d['recent_chunks'][-1]['legacy_name_length'],65536)
 async def test_extra_count_bounded(self):
  p=chunk('ok',finish='stop');p['choices'][0]['delta']['function_call']={str(i):'PRIVATE' for i in range(300)}
  d={};await consume(Stream([p]),record=d);self.assertEqual(d['stream_diagnostic']['recent_chunks'][0]['legacy_extra_field_count'],256);self.assertNotIn('PRIVATE',json.dumps(d))
 async def test_legacy_code_in_safe_events(self):
  p=chunk('ok');p['choices'][0]['delta']['function_call']={'arguments':'PRIVATE'};events=[];await consume(Stream([p]),notify=events.append)
  self.assertEqual(events[-1]['error_code'],'stream_legacy_function_call_unsupported');self.assertNotIn('PRIVATE',json.dumps(events))

# Separate test IDs for the SDK's permissive construct parser, including falsy bad types.
CASES={
 'missing':(MISSING,None),'null':(None,None),'empty':({},None),'null_fields':({'name':None,'arguments':None},None),'empty_fields':({'name':'','arguments':''},None),
 'name':({'name':'PRIVATE'},'unsupported'),'arguments':({'arguments':'PRIVATE'},'unsupported'),'space_name':({'name':' '},'unsupported'),
 'extra':({'opaque':'PRIVATE'},'unsupported'),'empty_extra':({'opaque':None},'unsupported'),
 'string':('PRIVATE','invalid'),'empty_string':('','invalid'),'list':([],'invalid'),'nonempty_list':(['PRIVATE'],'invalid'),'false':(False,'invalid'),'zero':(0,'invalid'),
 'bad_name_number':({'name':12},'invalid'),'bad_name_bool':({'name':False},'invalid'),'bad_arguments_list':({'arguments':[]},'invalid'),'bad_arguments_object':({'arguments':{}},'invalid')}
for label,(value,suffix) in CASES.items():
 async def check(self,v=value,s=suffix):await self.sdk(v,count=2,code=None if s is None else 'stream_legacy_function_call_'+s)
 setattr(Checks,'test_sdk_'+label,check)

if __name__=='__main__':unittest.main()
