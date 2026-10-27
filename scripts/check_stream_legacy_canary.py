"""New canary tests only use temporary roots and MockTransport, never Live batches."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts.stream_legacy_canary.plan import MESSAGE,plan_hash,config_for
from scripts.stream_legacy_canary.budget import Ledger,BudgetStop
from scripts.stream_legacy_canary.server import make_app,require_authorization
from scripts.stream_legacy_canary.mock import make_mock
from scripts.stream_legacy_canary.prepare import prepare

class BudgetChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.l=Ledger(self.root/'ledger.sqlite',plan_hash())
 def tearDown(self):self.tmp.cleanup()
 def reserve(self):return self.l.reserve('D02','coco','deepseek-v4.1-flash','agent',10)
 def test_auth_before_io(self):
  for auth in ('NOT_GRANTED','GRANTED_8_REQUESTS','GRANTED_10_REQUESTS',None):
   with self.assertRaises(BudgetStop):make_app('/does/not/exist','/no/config',auth)
 def test_exact_auth(self):require_authorization('GRANTED_1_REQUEST')
 def test_no_admission_without_attempt(self):
  with self.assertRaises(BudgetStop):self.reserve()
 def test_one_reservation(self):
  self.l.start('D02');r=self.reserve();self.l.settle(r,'returned')
  with self.assertRaises(BudgetStop):self.reserve()
  self.assertEqual(len(self.l.rows()),1)
 def test_one_http(self):
  self.l.start('D02');r=self.reserve();self.l.http(r)
  with self.assertRaises(BudgetStop):self.l.http(r)
  self.assertEqual(self.l.rows()[0]['http_attempts'],1)
 def test_no_unreserved_http(self):
  with self.assertRaises(BudgetStop):self.l.http(88)
 def test_failed_not_retryable(self):
  self.l.start('D02');r=self.reserve();self.l.settle(r,'failed');self.l.finish('D02',False)
  with self.assertRaises(BudgetStop):self.l.start('D02')
 def test_restart_not_retryable(self):
  self.l.start('D02');other=Ledger(self.l.path,plan_hash())
  with self.assertRaises(BudgetStop):other.start('D02')
 def test_unsettled_not_finished(self):
  self.l.start('D02');self.reserve()
  with self.assertRaises(BudgetStop):self.l.finish('D02',True)
 def test_summary_blocked(self):
  self.l.start('D02')
  with self.assertRaises(BudgetStop):self.l.reserve('D02','coco','x','compaction',1)
  self.assertEqual(self.l.rows()[0]['http_attempts'],0)
 def test_halt_cleanup_preserved(self):
  self.l.start('D02');self.l.halt('original');self.l.finish('D02',False)
  with self.l.connect() as db:self.assertEqual(db.execute("select value from meta where key='halt'").fetchone()[0],'original')
 def test_existing_batch_rejected(self):
  with self.assertRaisesRegex(BudgetStop,'batch_exists'):prepare(self.root,'absent','absent')
 def test_changed_ledger_identity(self):
  self.l.path.rename(self.root/'old');self.l.path.write_bytes((self.root/'old').read_bytes());self.l.path.chmod(0o600)
  with self.assertRaises(BudgetStop):self.l.rows()
 def test_concurrent_reservation_only_one(self):
  from concurrent.futures import ThreadPoolExecutor
  self.l.start('D02')
  def attempt(_):
   try:return self.reserve()
   except BudgetStop:return None
  with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(attempt,range(4)))
  self.assertEqual(sum(x is not None for x in results),1);self.assertEqual(len(self.l.rows()),1)
 def test_config(self):
  c=config_for(self.root,dict(model='deepseek-v4.1-flash',base_url='http://mock.invalid',api_key=None))
  self.assertTrue(c.web_streaming);self.assertFalse(c.web_steer or c.mcp_enabled or c.skills_enabled or c.coding_enabled);self.assertEqual(c.context_compaction['mode'],'deterministic')

class RuntimeChecks(unittest.IsolatedAsyncioTestCase):
 async def run_case(self,mode):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();app=make_mock(root,8900,mode)
   async with app.app.router.lifespan_context(app.app):
    c=app.runtime.new();self.assertTrue(await app.runtime.start(c,MESSAGE));await c.task;await asyncio.sleep(.05)
    self.assertEqual(len(app.mock_requests),1);self.assertEqual(app.mock_requests[0]['stream_options'],{'include_usage':True});self.assertFalse(app.mock_requests[0].get('tools'))
    self.assertEqual(len(app.uat_ledger.rows()),1);self.assertEqual(app.uat_ledger.rows()[0]['http_attempts'],1)
    result=dict(app.canary_result)
    with self.assertRaises(BudgetStop):await app.runtime.start(c,MESSAGE)
   cleanup=json.loads((root/'private/cleanup.json').read_text());self.assertTrue(cleanup['runtime_closed'] and cleanup['lease_released'] and cleanup['database_consistent']);self.assertFalse(cleanup['cleanup_uncertain'])
   return result,app.uat_ledger.rows()
 async def test_sdk_standard(self):
  r,rows=await self.run_case('standard');self.assertEqual(r['protocol'],'PASS');self.assertTrue(r['trusted_final_persisted']);self.assertTrue(r['streams'][0]['natural_eof']);self.assertTrue(r['streams'][0]['sdk_closed']);self.assertEqual(json.loads(rows[0]['usage'])['total_tokens'],30)
 async def test_sdk_missing_usage_protocol_pass(self):
  r,_=await self.run_case('missing');self.assertEqual(r['protocol'],'PASS');self.assertFalse(r['streams'][0]['observed_usage_fields_complete'])
 async def test_duplicate_diagnosed(self):
  r,_=await self.run_case('duplicate');self.assertEqual(r['protocol'],'FAIL');d=r['streams'][0]['diagnostic'];self.assertEqual(d['error_code'],'stream_duplicate_finish');self.assertEqual(d['chunk_index'],4);self.assertLessEqual(len(d['recent_chunks']),8);self.assertNotIn('合成',json.dumps(d,ensure_ascii=False))
 async def test_before_first_fallback_blocked(self):
  r,_=await self.run_case('before');self.assertEqual(r['protocol'],'FAIL');self.assertEqual(r['physical_requests'],1);self.assertEqual(r['http_attempts'],1);self.assertTrue(r['fallback_dispatch_blocked']);self.assertEqual(r['providers'],['coco'])
 async def test_after_first_no_fallback(self):
  r,_=await self.run_case('after');self.assertEqual(r['protocol'],'FAIL');self.assertFalse(r['fallback_dispatch_blocked']);self.assertEqual(r['streams'][0]['diagnostic']['error_code'],'stream_transport_interrupted')
 async def test_input_is_frozen(self):
  with tempfile.TemporaryDirectory() as tmp:
   app=make_mock(Path(tmp).resolve(),8900)
   async with app.app.router.lifespan_context(app.app):
    with self.assertRaises(BudgetStop):await app.runtime.start(app.runtime.new(),'changed')
    self.assertEqual(len(app.mock_requests),0)

class AdapterChecks(unittest.IsolatedAsyncioTestCase):
 async def test_close_failure_stays_unsettled(self):
  from scripts.stream_legacy_canary.adapter import ObservedStream
  class Raw:
   async def close(self):raise OSError('synthetic close')
  with tempfile.TemporaryDirectory() as tmp:
   l=Ledger(Path(tmp).resolve()/'ledger',plan_hash());l.start('D02');rid=l.reserve('D02','coco','model','agent',1);stream=ObservedStream(Raw(),l,rid,0,{})
   with self.assertRaises(OSError):await stream.close()
   self.assertFalse(stream.closed);self.assertEqual(l.rows()[0]['state'],'reserved')
   with l.connect() as db:self.assertEqual(db.execute("select value from meta where key='halt'").fetchone()[0],'stream_cleanup_unconfirmed')
 async def test_options_tools_and_retry_rejected_before_http(self):
  from scripts.stream_legacy_canary.adapter import BudgetClient
  from scripts.stream_legacy_canary.mock import client_builder
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();cfg=config_for(root,dict(model='mock',base_url='http://mock.invalid',api_key=None));l=Ledger(root/'ledger',plan_hash());l.start('D02');counter=[];sdk=client_builder('standard',counter)(cfg);client=BudgetClient(sdk,cfg,l,[],[])
   try:
    for request in ({'stream':False},{'stream':True},{'stream':True,'stream_options':{'include_usage':False}},{'stream':True,'stream_options':{'include_usage':True},'tools':[{}]}):
     with self.assertRaises(BudgetStop):await client.create(**request)
    sdk.max_retries=1
    with self.assertRaises(BudgetStop):await client.create(stream=True,stream_options={'include_usage':True})
    self.assertEqual(counter,[]);self.assertEqual(l.rows(),[])
   finally:await sdk.close()

class FreezeChecks(unittest.TestCase):
 def setUp(self):
  import scripts.stream_legacy_canary.prepare as module
  self.m=module;self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.batch=self.root/'batch';self.provider=self.root/'config';self.provider.write_text('synthetic config fingerprint')
  self.probe=self.root/'probe.json';self.probe.write_text(json.dumps(dict(passed=True,profiles_removed=True,server_closed=True)))
  self.patches=[patch.object(module,'provider_snapshot',side_effect=lambda p:{'hash':module.file_hash(p)}),patch.object(module,'sources',return_value={'synthetic.py':'fixed'}),patch.object(module.subprocess,'check_output',side_effect=lambda cmd,**kw:'synthetic-commit\n' if 'rev-parse' in cmd else b''),patch.object(module.subprocess,'run')]
  for p in self.patches:p.start()
  module.prepare(self.batch,self.provider,self.probe)
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def freeze(self):return self.m.freeze(self.batch,self.provider)
 def test_prepare_unique(self):
  with self.assertRaises(BudgetStop):self.m.prepare(self.batch,self.provider,self.probe)
 def test_freeze_unique(self):
  self.freeze()
  with self.assertRaises(BudgetStop):self.freeze()
 def test_verify_zero(self):
  self.freeze();self.assertEqual(self.m.verify_frozen(self.batch,self.provider)['usage'],dict(real_requests=0,attempts=0,unsettled=0,http_attempts=0))
 def test_provider_bytes_changed(self):
  self.freeze();self.provider.write_text('changed')
  with self.assertRaises(BudgetStop):self.m.verify_frozen(self.batch,self.provider)
 def test_workspace_changed(self):
  self.freeze();(self.batch/'workspace/README.md').write_text('changed')
  with self.assertRaises(BudgetStop):self.m.verify_frozen(self.batch,self.provider)
 def test_source_changed(self):
  self.freeze()
  with patch.object(self.m,'sources',return_value={'changed':True}),self.assertRaises(BudgetStop):self.m.verify_frozen(self.batch,self.provider)
 def test_event_inode_changed(self):
  self.freeze();p=self.batch/'private/session-events.sqlite3';p.rename(p.with_suffix('.old'));p.write_bytes(p.with_suffix('.old').read_bytes());p.chmod(0o600)
  with self.assertRaises(BudgetStop):self.m.verify_frozen(self.batch,self.provider)
 def test_prepared_changed(self):
  self.freeze();p=self.batch/'prepared.json';p.write_text(p.read_text()+' ')
  with self.assertRaises(BudgetStop):self.m.verify_frozen(self.batch,self.provider)
 def test_halt_admission_and_cleanup_distinct(self):
  self.freeze();ledger=Ledger(self.batch/'private/requests.sqlite',plan_hash());ledger.halt('test')
  with self.assertRaises(BudgetStop):self.m.verify_frozen(self.batch,self.provider)
  self.m.verify_frozen(self.batch,self.provider,allow_halt=True)
 def test_unproven_browser_before_creation(self):
  self.probe.write_text('{}')
  with self.assertRaises(BudgetStop):self.m.prepare(self.root/'other',self.provider,self.probe)
  self.assertFalse((self.root/'other').exists())

if __name__=='__main__':unittest.main()
