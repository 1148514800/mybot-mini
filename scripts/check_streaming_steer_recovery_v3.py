"""Independent two-request gates and native SDK MockTransport tests."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import httpx
from .streaming_steer_recovery_v3.plan import *
from .streaming_steer_recovery_v3.budget import Ledger,BudgetStop
from .streaming_steer_recovery_v3.server import make_app,require_authorization
from .streaming_steer_recovery_v3.mock import make_mock

class BudgetChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.l=Ledger(self.root/'ledger',plan_hash())
 def reserve(self,case='N01',provider='coco',purpose='agent'):return self.l.reserve(case,provider,MODELS[provider],purpose,10)
 def test_caps(self):self.assertEqual(LIMITS,{'N01':1,'N02':1});self.assertEqual(GLOBAL_LIMIT,2)
 def test_auth_before_io(self):
  for a in ('NOT_GRANTED','GRANTED_1_REQUEST','GRANTED_6_REQUESTS',None,True):
   with self.assertRaises(BudgetStop):make_app('N01','absent','absent',authorization=a)
 def test_auth_exact(self):require_authorization('GRANTED_2_REQUESTS')
 def test_browser_auth_before_io(self):
  from .streaming_steer_recovery_v3.browser import run
  with self.assertRaises(RuntimeError):run(self.root/'browser','missing',live=True,authorization='GRANTED_6_REQUESTS')
  self.assertFalse((self.root/'browser').exists())
 def test_no_live_override(self):
  from .streaming_steer_recovery_v3.browser import run
  with self.assertRaises(RuntimeError):run(self.root/'browser','missing',live=True,authorization=REQUIRED_AUTHORIZATION,fault='navigation')
 def test_order(self):
  with self.assertRaises(BudgetStop):self.l.start('N02')
 def test_unique_attempt(self):
  self.l.start('N01');self.l.finish('N01','completed')
  with self.assertRaises(BudgetStop):self.l.start('N01')
 def test_case_one_and_backup_blocked(self):
  self.l.start('N01');r=self.reserve();self.l.http(r);self.l.settle(r,'failed')
  with self.assertRaises(BudgetStop):self.reserve(provider='coco2')
  self.assertEqual(len(self.l.rows()),1)
 def test_total_two_durable(self):
  for c in LIMITS:
   self.l.start(c);r=self.reserve(c);self.l.http(r);self.l.settle(r,'returned');self.l.finish(c,'completed')
  self.assertEqual(len(Ledger(self.l.path,plan_hash()).rows()),2)
  with self.l.connect() as d:d.execute("update cases set status='running' where id='N02'")
  with self.assertRaises(BudgetStop):self.reserve('N02')
 def test_concurrent_reservations(self):
  self.l.start('N01')
  def reserve():
   try:return self.reserve()
   except BudgetStop:return None
  with ThreadPoolExecutor(2) as pool:rows=list(pool.map(lambda _:reserve(),range(2)))
  self.assertEqual(sum(r is not None for r in rows),1)
 def test_summary_blocked(self):
  self.l.start('N01')
  with self.assertRaises(BudgetStop):self.reserve(purpose='summary')
  self.assertEqual(self.l.rows()[0]['http_attempts'],0)
 def test_unsettled_prevents_next_case(self):
  self.l.start('N01');self.reserve()
  with self.assertRaises(BudgetStop):self.l.start('N02')
 def test_halt_preserved_and_finish_allowed(self):
  self.l.start('N01');self.l.halt('first');self.l.halt('second');self.l.finish('N01','failed')
  with self.l.connect() as d:self.assertEqual(d.execute("select value from meta where key='halt'").fetchone()[0],'first')
  with self.assertRaises(BudgetStop):self.l.start('N02')
 def test_duplicate_http_denied(self):
  self.l.start('N01');r=self.reserve();self.l.http(r)
  with self.assertRaises(BudgetStop):self.l.http(r)
  self.assertEqual(self.l.rows()[0]['http_attempts'],1)

class NativeChecks(unittest.IsolatedAsyncioTestCase):
 async def run_case(self,case='N01',mode='normal',action=True):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();(root/'private').mkdir(mode=0o700)
   if case=='N02':
    l=Ledger(root/'private/requests.sqlite',plan_hash());l.start('N01');l.finish('N01','inconclusive')
   app=make_mock(root,8902,case,mode,barriers={'N01':.10,'N02':.10},delay=.015)
   async with app.app.router.lifespan_context(app.app):
    c=app.runtime.new();await app.runtime.start(c,MESSAGES[case])
    for _ in range(400):
     if any(s.first_delivered for s in app.uat_streams) or c.task.done():break
     await asyncio.sleep(.005)
    if action and not c.task.done():
     if case=='N01':app.runtime.steer(c,dict(expected_turn_id=c.history.turn_id,client_request_id='synthetic-once',text=STEER[case]))
     else:await app.runtime.stop(c)
    await c.task;await asyncio.sleep(.03);r=dict(app.uat_result);bodies=list(app.mock_requests);rows=app.uat_ledger.rows()
   cleanup=json.loads((root/'private'/f'{case}-cleanup.json').read_text());self.assertTrue(cleanup['lease_released']);self.assertTrue(cleanup['sdk_streams_closed']);self.assertTrue(cleanup['database_consistent'])
   return r,bodies,rows
 async def test_queued_not_applied(self):
  r,b,rows=await self.run_case();self.assertEqual(len(b),1);self.assertEqual(r['steers'][0]['status'],'not_applied');self.assertFalse(r['protocol_security_halt']);self.assertTrue(r['streams'][0]['sdk_request_unchanged_at_close']);self.assertTrue(any(e['stage']=='queued' for e in r['host_events']));self.assertFalse(any(e['stage']=='native_on_dispatch_admitted' for e in r['host_events']))
 async def test_stop_sdk_close_untrusted(self):
  r,b,rows=await self.run_case('N02');s=r['streams'][0];self.assertEqual(r['status'],'cancelled');self.assertEqual(len(b),1);self.assertTrue(s['sdk_closed']);self.assertFalse(s['terminal_trusted']);self.assertIsNone(s['settled_usage']['total_tokens']);self.assertFalse(r['final_persistence_matches_sdk']);self.assertEqual(s['diagnostic']['error_code'],'stream_user_or_caller_cancelled');self.assertFalse(r['protocol_security_halt'])
 async def test_terminal_first_no_fake_barrier(self):
  r,_,_=await self.run_case(mode='terminal_first');self.assertEqual(r['scenario_premise'],'INCONCLUSIVE');self.assertFalse(r['steers']);self.assertEqual(r['streams'][0]['controlled_barrier_seconds'],0)
 async def test_duplicate_terminal_halts(self):
  r,b,_=await self.run_case(mode='duplicate');self.assertTrue(r['protocol_security_halt']);self.assertEqual(len(b),1)
 async def test_after_first_no_fallback(self):
  r,b,_=await self.run_case(mode='after');self.assertTrue(r['protocol_security_halt']);self.assertEqual(len(b),1);self.assertEqual(r['fallback_dispatches'],0)
 async def test_before_first_backup_blocked_by_one_cap(self):
  r,b,rows=await self.run_case(mode='before');self.assertEqual(len(b),1);self.assertEqual(len(rows),1);self.assertTrue(r['protocol_security_halt'])
 async def test_missing_usage_unknown(self):
  r,_,_=await self.run_case(mode='missing');self.assertTrue(r['streams'][0]['terminal_trusted']);self.assertIsNone(r['streams'][0]['settled_usage']['total_tokens'])
 async def test_no_action_inconclusive(self):
  r,_,_=await self.run_case(action=False);self.assertEqual(r['scenario_premise'],'INCONCLUSIVE');self.assertFalse(r['steers'])
 async def test_empty_registry(self):
  r,b,_=await self.run_case();self.assertFalse(b[0].get('tools'));self.assertFalse(any(e['stage']=='tool_started' for e in r['host_events']))
 async def test_refresh_no_model_resend(self):
  with tempfile.TemporaryDirectory() as tmp:
   app=make_mock(Path(tmp).resolve(),8902,'N01',barriers={'N01':0,'N02':0},delay=.005)
   async with app.app.router.lifespan_context(app.app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8902') as h:
     await h.get('/');csrf=(await h.get('/api/bootstrap')).json()['csrf'];headers={'Origin':'http://127.0.0.1:8902','X-Mybot-CSRF':csrf}
     sid=(await h.post('/api/conversations',json={},headers=headers)).json()['id'];await h.post(f'/api/conversations/{sid}/messages',json={'message':MESSAGES['N01']},headers=headers)
     await app.runtime.conversations[sid].task;await asyncio.sleep(.02)
     for url in ('/','/api/bootstrap',f'/api/conversations/{sid}'):(await h.get(url)).raise_for_status()
     self.assertEqual(len(app.mock_requests),1)

class FreezeChecks(unittest.TestCase):
 def setUp(self):
  import scripts.streaming_steer_recovery_v3.prepare as module
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
