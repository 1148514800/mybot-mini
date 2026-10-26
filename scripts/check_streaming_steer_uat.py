"""New eight-request UAT gate tests; every SDK send is intercepted MockTransport."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import httpx
from openai import AsyncOpenAI
from mybot.runtime_accounting import RuntimeAccounting
from mybot.provider_failover import ProviderFailoverClient
from mybot.agent import AgentLoop,ContextBuilder
from mybot.tools import build_default_tool_registry
from scripts.streaming_steer_uat.plan import *
from scripts.streaming_steer_uat.budget import Ledger,BudgetStop
from scripts.streaming_steer_uat.adapter import BudgetClient
from scripts.streaming_steer_uat.server import require_authorization,make_app,ReadRegistry
from scripts.streaming_steer_uat import prepare as prep

P=dict(model=MODELS['coco'],base_url='http://mock.invalid/v1',api_key='synthetic-test-only')
class Checks(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.ledger=Ledger(self.root/'ledger.sqlite',plan_hash());self.ledger.start('R01');self.cfg=config_for(self.root,P)
 def req(self):return dict(model=self.cfg.model,messages=[dict(role='user',content='OFFLINE MOCK ONLY')],tools=None,max_tokens=100,stream=True,stream_options={'include_usage':True})
 def raw(self,handler,retries=0):return AsyncOpenAI(api_key='synthetic-test-only',base_url=P['base_url'],max_retries=retries,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
 def wrapper(self,handler,case='R01',**kw):return BudgetClient(self.raw(handler),self.cfg,self.ledger,case,barrier=0,**kw)
 async def handler(self,request):
  data=dict(id='mock',object='chat.completion.chunk',created=1,model='mock',choices=[dict(index=0,delta={'content':'合成回复\n'},finish_reason='stop')],usage=None)
  usage=dict(id='mock',object='chat.completion.chunk',created=1,model='mock',choices=[],usage=dict(prompt_tokens=1,completion_tokens=2,total_tokens=3))
  return httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: '+json.dumps(data)+'\n\ndata: '+json.dumps(usage)+'\n\ndata: [DONE]\n\n')
 def next(self,case):self.ledger.finish('R01');self.ledger.start(case)
 def test_no_authorization_before_all_access(self):
  with patch('scripts.streaming_steer_uat.server.verify_frozen') as v,patch('scripts.streaming_steer_uat.server.credentials') as c,patch('scripts.streaming_steer_uat.server.build_client') as b:
   with self.assertRaises(BudgetStop):make_app('R01',self.root/'absent',self.root/'no-provider')
  v.assert_not_called();c.assert_not_called();b.assert_not_called()
 def test_old_authorizations_refused(self):
  for v in ('GRANTED_16_REQUESTS','GRANTED_10_REQUESTS','GRANTED_8_REQUESTS ',None,True,'NOT_GRANTED'):
   with self.assertRaises(BudgetStop):require_authorization(v)
 def test_contract_exact_caps(self):self.assertEqual(LIMITS,{'R01':1,'R02':4,'R03':1,'R04':2});self.assertEqual(sum(LIMITS.values()),8);self.assertEqual(contract()['authorization'],'NOT_GRANTED')
 def test_frozen_barriers_and_messages(self):self.assertEqual(len(MESSAGES),4);self.assertEqual(set(STEER),{'R02','R03'});self.assertEqual(BARRIER,{'R01':0,'R02':8,'R03':8,'R04':8});self.assertIn('LANTERN-LOCAL-42',FIXTURES['README.md'])
 def test_no_rerun(self):
  with self.assertRaises(BudgetStop):self.ledger.start('R01')
 def test_order(self):
  with self.assertRaises(BudgetStop):self.ledger.start('R04')
 def test_capacity_no_transfer(self):
  rid=self.ledger.reserve('R01','coco','mock','agent',1);self.ledger.settle(rid,'failed')
  with self.assertRaisesRegex(BudgetStop,'case_budget'):self.ledger.reserve('R01','coco2','mock','agent',1)
 def test_global_eight_durable(self):
  for c,cap in LIMITS.items():
   if c!='R01':self.ledger.start(c)
   for _ in range(cap):rid=self.ledger.reserve(c,'coco','mock','agent',1);self.ledger.settle(rid,'cancelled')
   self.ledger.finish(c)
  self.assertEqual(len(Ledger(self.ledger.path,plan_hash()).rows()),8)
  with self.ledger.connect() as db:db.execute("UPDATE cases SET status='running' WHERE id='R04'")
  with self.assertRaisesRegex(BudgetStop,'global_budget'):self.ledger.reserve('R04','coco','mock','agent',1)
 def test_unsettled_blocks_reopen(self):
  self.ledger.reserve('R01','coco','mock','agent',1)
  with self.assertRaises(BudgetStop):Ledger(self.ledger.path,plan_hash()).reserve('R01','coco','mock','agent',1)
 def test_unsettled_blocks_finish(self):
  self.ledger.reserve('R01','coco','mock','agent',1)
  with self.assertRaises(BudgetStop):self.ledger.finish('R01')
 def test_concurrent_reservations(self):
  def attempt(i):
   try:return self.ledger.reserve('R01','coco','mock','agent',1)
   except BudgetStop:return None
  with ThreadPoolExecutor(max_workers=6) as pool:rows=list(pool.map(attempt,range(8)))
  self.assertEqual(sum(v is not None for v in rows),1)
 def test_summary_blocked_counted_conservatively(self):
  with self.assertRaises(BudgetStop):self.ledger.reserve('R01','coco','mock','compaction',1)
  self.assertEqual(self.ledger.rows()[0]['state'],'blocked')
 def test_http_retry_gate(self):
  rid=self.ledger.reserve('R01','coco','mock','agent',1);self.ledger.http(rid)
  with self.assertRaises(BudgetStop):self.ledger.http(rid)
 def test_identity_replacement(self):
  self.ledger.path.rename(self.root/'old')
  self.ledger.path.write_bytes(b'different')
  with self.assertRaises(BudgetStop):self.ledger.rows()
 def test_tool_registry_native_loop_only_two(self):
  self.cfg.workspace.mkdir();tools=ReadRegistry(build_default_tool_registry(self.cfg.workspace),['read_file','list_files']);a=AgentLoop(None,self.cfg,tools,ContextBuilder(self.cfg.workspace));self.addCleanup(a.close_history)
  self.assertEqual({t.name for t in tools.iter_tools()},{'read_file','list_files'});self.assertFalse(tools.permitted('apply_patch'));self.assertFalse(tools.has_tool('create_plan'))
 async def test_sdk_stream_once_usage(self):
  c=self.wrapper(self.handler);a=RuntimeAccounting()
  try:r=await a.request(c,self.cfg,self.req())
  finally:await c.close()
  row=self.ledger.rows()[0];self.assertEqual(row['state'],'returned');self.assertEqual(row['http_attempts'],1);self.assertEqual(json.loads(row['usage'])['total_tokens'],3);self.assertEqual(a.snapshot()['physical_requests'],1);self.assertEqual(r.choices[0].message.content,'合成回复\n')
 async def test_reservation_remains_while_consuming(self):
  checked=[]
  async def handler(req):
   checked.append(self.ledger.rows()[0]['state']);return await self.handler(req)
  c=self.wrapper(handler);a=RuntimeAccounting()
  try:await a.request(c,self.cfg,self.req())
  finally:await c.close()
  self.assertEqual(checked,['reserved'])
 async def test_bad_options_no_send(self):
  called=[]
  async def handler(req):called.append(1);return await self.handler(req)
  c=self.wrapper(handler)
  try:
   with self.assertRaises(BudgetStop):await RuntimeAccounting().request(c,self.cfg,{**self.req(),'stream_options':{}})
  finally:await c.close()
  self.assertEqual(called,[]);self.assertEqual(self.ledger.rows(),[])
 async def test_unsafe_registry_no_send(self):
  c=self.wrapper(self.handler)
  try:
   with self.assertRaises(BudgetStop):await RuntimeAccounting().request(c,self.cfg,{**self.req(),'tools':[{'function':{'name':'apply_patch'}}]})
  finally:await c.close()
  self.assertEqual(self.ledger.rows(),[])
 def test_retries_nonzero_rejected(self):
  c=self.raw(self.handler,retries=1)
  with self.assertRaises(BudgetStop):BudgetClient(c,self.cfg,self.ledger,'R01')
  self.addAsyncCleanup(c.close)
 async def test_authentication_halts(self):
  async def handler(req):return httpx.Response(401,json={'error':{'message':'synthetic auth'}})
  c=self.wrapper(handler)
  try:
   with self.assertRaises(Exception):await RuntimeAccounting().request(c,self.cfg,self.req())
  finally:await c.close()
  self.assertEqual(self.ledger.rows()[0]['http_attempts'],1)
  with self.assertRaises(BudgetStop):self.ledger.reserve('R01','coco','mock','agent',1)
 async def test_first_chunk_failure_fallback_each_counted(self):
  self.next('R02')
  async def error(req):return httpx.Response(503,json={'error':{'message':'synthetic'}})
  primary=self.wrapper(error,'R02');backup=self.wrapper(self.handler,'R02');g=ProviderFailoverClient(primary,self.cfg,replace(self.cfg,provider='coco2'),lambda _:backup)
  try:r=await RuntimeAccounting().request(g,self.cfg,self.req())
  finally:await g.close()
  self.assertEqual(len(self.ledger.rows()),2);self.assertEqual(sum(r['http_attempts'] for r in self.ledger.rows()),2)
 async def test_after_chunk_failure_never_fallback(self):
  self.next('R02')
  class Broken(httpx.AsyncByteStream):
   async def __aiter__(self):
    yield b'data: {"id":"x","object":"chat.completion.chunk","created":1,"model":"x","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n';raise OSError('synthetic broken stream')
   async def aclose(self):pass
  async def handler(req):return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Broken())
  primary=self.wrapper(handler,'R02');backup=self.wrapper(self.handler,'R02');g=ProviderFailoverClient(primary,self.cfg,replace(self.cfg,provider='coco2'),lambda _:backup)
  try:r=await RuntimeAccounting().request(g,self.cfg,self.req())
  finally:await g.close()
  self.assertEqual(len(self.ledger.rows()),1);self.assertIsNone(r.usage);self.assertEqual(r.stream_delivery['status'],'provider_error')
 async def test_cancel_closes_settles_unknown(self):
  closed=[]
  class Waiting(httpx.AsyncByteStream):
   async def __aiter__(self):
    yield b'data: {"id":"x","object":"chat.completion.chunk","created":1,"model":"x","choices":[{"index":0,"delta":{"content":"hello"},"finish_reason":null}]}\n\n';await asyncio.sleep(10)
   async def aclose(self):closed.append(True)
  async def handler(req):return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Waiting())
  c=self.wrapper(handler);t=asyncio.create_task(RuntimeAccounting().request(c,self.cfg,self.req()));await asyncio.sleep(.03);t.cancel()
  with self.assertRaises(asyncio.CancelledError):await t
  await c.close();self.assertTrue(closed);row=self.ledger.rows()[0];self.assertEqual(row['state'],'cancelled');self.assertIsNone(json.loads(row['usage'])['total_tokens'])
 def test_configuration_no_authority_or_summary(self):
  self.assertTrue(self.cfg.web_streaming and self.cfg.web_steer);self.assertFalse(self.cfg.coding_enabled or self.cfg.mcp_enabled or self.cfg.skills_enabled);self.assertEqual(self.cfg.coding_command['mode'],'off');self.assertEqual(self.cfg.context_compaction['mode'],'deterministic')
 def test_prepare_once_no_live_client(self):
  provider=self.root/'provider.json';provider.write_text(json.dumps({'llm':{'provider':'coco','providers':{'coco':P,'coco2':{**P,'model':MODELS['coco2']}}}}));probe=self.root/'probe.json';probe.write_text(json.dumps(dict(passed=True,profiles_removed=True,server_closed=True)))
  batch=self.root/'batch'
  with patch('scripts.streaming_steer_uat.server.build_client') as b:
   data=prep.prepare(batch,provider,probe);b.assert_not_called()
  self.assertTrue(data['configuration']['web_streaming']);self.assertEqual((batch/'workspace/README.md').read_text(),FIXTURES['README.md'])
  with self.assertRaises(BudgetStop):prep.prepare(batch,provider,probe)
 def test_invalid_browser_probe_prevents_batch(self):
  probe=self.root/'probe.json';probe.write_text('{}')
  with self.assertRaises(BudgetStop):prep.prepare(self.root/'absent',self.root/'no-config',probe)
  self.assertFalse((self.root/'absent').exists())
 async def test_barrier_preserves_chunks_and_separates_first_text(self):
  from scripts.streaming_steer_uat.adapter import ObservedStream
  from scripts.streaming_fixtures import Stream,chunk
  import time
  self.next('R02');rid=self.ledger.reserve('R02','coco','mock','agent',1);a=chunk();b=chunk('visible',finish='stop');stream=ObservedStream(Stream([a,b]),self.ledger,rid,'R02',time.monotonic(),self.req(),barrier=.02)
  it=stream.__aiter__();self.assertIs(await anext(it),a);start=time.monotonic();self.assertIs(await anext(it),b);self.assertGreaterEqual(time.monotonic()-start,.015)
  with self.assertRaises(StopAsyncIteration):await anext(it)
  await stream.close();self.assertFalse(stream.record['first_chunk_is_text']);self.assertGreaterEqual(stream.first_text,stream.first);self.assertGreaterEqual(stream.record['controlled_barrier_seconds'],.015)
 async def test_first_terminal_chunk_has_no_barrier(self):
  from scripts.streaming_steer_uat.adapter import ObservedStream
  from scripts.streaming_fixtures import Stream,chunk
  import time
  rid=self.ledger.reserve('R01','coco','mock','agent',1);stream=ObservedStream(Stream([chunk('done',finish='stop')]),self.ledger,rid,'R01',time.monotonic(),self.req(),barrier=.1)
  async for item in stream:pass
  await stream.close();self.assertTrue(stream.record['first_chunk_terminal']);self.assertEqual(stream.waited,0)
 async def test_full_web_readonly_steer_mock_transport(self):
  from scripts.streaming_steer_uat.adapter import BudgetClient as RealClient
  batch=self.root/'web-batch';(batch/'workspace').mkdir(parents=True);(batch/'private').mkdir(mode=0o700)
  for name,text in FIXTURES.items():
   path=batch/'workspace'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
  requests=[]
  async def handler(req):
   body=json.loads(req.content);requests.append(body);n=len(requests)
   if n==1:packets=[{'delta':{'role':'assistant'},'finish_reason':None},{'delta':{'tool_calls':[{'index':0,'id':'list','type':'function','function':{'name':'list_files','arguments':'{\"path\":\".\"}'}}]},'finish_reason':'tool_calls'}]
   elif n==2:packets=[{'delta':{'role':'assistant'},'finish_reason':None},{'delta':{'tool_calls':[{'index':0,'id':'read','type':'function','function':{'name':'read_file','arguments':'{\"path\":\"README.md\"}'}}]},'finish_reason':'tool_calls'}]
   else:
    self.assertIn('LANTERN-LOCAL-42',str(body['messages']));packets=[{'delta':{'content':'本地Markdown搜索演示，标识LANTERN-LOCAL-42。它不联网也不修改输入。'},'finish_reason':'stop'}]
   data=[dict(id='x',object='chat.completion.chunk',created=1,model='mock',choices=[dict(index=0,**v)]) for v in packets]
   return httpx.Response(200,headers={'content-type':'text/event-stream'},text=''.join('data: '+json.dumps(v)+'\n\n' for v in data)+'data: [DONE]\n\n')
  def sdk(cfg):return self.raw(handler)
  def client(*a,**kw):return RealClient(*a,**kw,barrier=.04)
  with patch('scripts.streaming_steer_uat.server.verify_frozen',return_value={'usage':{'unsettled':0}}),patch('scripts.streaming_steer_uat.server.credentials',return_value={'coco':P,'coco2':{**P,'model':MODELS['coco2']}}),patch('scripts.streaming_steer_uat.server.build_client',side_effect=sdk),patch('scripts.streaming_steer_uat.server.BudgetClient',side_effect=client):
   app=make_app('R02',batch,self.root/'mock-provider',authorization=REQUIRED_AUTHORIZATION);app.uat_ledger.start('R01');app.uat_ledger.finish('R01')
   async with app.app.router.lifespan_context(app.app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8899') as h:
     await h.get('/');boot=(await h.get('/api/bootstrap')).json();headers={'Origin':'http://127.0.0.1:8899','X-Mybot-CSRF':boot['csrf']};c=(await h.post('/api/conversations',json={},headers=headers)).json();sid=c['id']
     r=await h.post('/api/conversations/'+sid+'/messages',json={'message':MESSAGES['R02']},headers=headers);self.assertEqual(r.status_code,202)
     for _ in range(50):
      if list((batch/'private').glob('R02-*-first-chunk.json')):break
      await asyncio.sleep(.002)
     conv=app.runtime.conversations[sid];r=await h.post('/api/conversations/'+sid+'/steer',json=dict(expected_turn_id=conv.history.turn_id,client_request_id='mock-user',text=STEER['R02']),headers=headers);self.assertEqual(r.status_code,200);await conv.task
     self.assertEqual(conv.state()['steers'][0]['status'],'applied');self.assertEqual(len(requests),3);self.assertNotIn(STEER['R02'],str(requests[0]));self.assertIn(STEER['R02'],str(requests[1]));self.assertIn('not_executed_pending_user_steer',str(requests[1]));self.assertEqual([v['name'] for v in app.runtime.event_store.query('SELECT name FROM tools')],['read_file'])
   self.assertEqual(len(app.uat_ledger.rows()),3)

def check_streaming_steer_uat():
 r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
 if not r.wasSuccessful():raise AssertionError('streaming live UAT offline checks failed')
if __name__=='__main__':check_streaming_steer_uat()
