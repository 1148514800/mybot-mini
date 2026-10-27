"""Independent six-request gates and actual SDK/native Web orchestration, offline only."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from dataclasses import replace
import httpx
from mybot.runtime_accounting import RuntimeAccounting
from scripts.streaming_steer_real_uat_v2.plan import *
from scripts.streaming_steer_real_uat_v2.budget import Ledger,BudgetStop
from scripts.streaming_steer_real_uat_v2.server import make_app,require_authorization
from scripts.streaming_steer_real_uat_v2.mock import make_mock,build_mock
from scripts.streaming_steer_real_uat_v2.adapter import BudgetClient
from scripts.streaming_steer_real_uat_v2 import prepare as prep

class BudgetChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.l=Ledger(self.root/'ledger',plan_hash())
 def reserve(self,case='T01',provider='coco',purpose='agent'):return self.l.reserve(case,provider,MODELS[provider],purpose,10)
 def test_contract_caps(self):self.assertEqual(LIMITS,{'T01':4,'T02':1,'T03':1});self.assertEqual(GLOBAL_LIMIT,6)
 def test_old_auth_rejected_before_io(self):
  for a in ('NOT_GRANTED','GRANTED_1_REQUEST','GRANTED_8_REQUESTS',None,True):
   with self.assertRaises(BudgetStop):make_app('T01','absent','absent',authorization=a)
 def test_browser_old_grant_rejected_before_access(self):
  from scripts.streaming_steer_real_uat_v2.browser import run
  with self.assertRaises(RuntimeError):run(self.root/'browser',self.root/'missing-chrome',live=True,authorization='GRANTED_1_REQUEST')
  self.assertFalse((self.root/'browser').exists())
 def test_exact_auth(self):require_authorization('GRANTED_6_REQUESTS')
 def test_order(self):
  with self.assertRaises(BudgetStop):self.l.start('T02')
 def test_unique_attempt(self):
  self.l.start('T01');self.l.finish('T01','completed')
  with self.assertRaises(BudgetStop):self.l.start('T01')
 def test_t01_four_not_transfer(self):
  self.l.start('T01')
  for _ in range(4):r=self.reserve();self.l.settle(r,'returned')
  with self.assertRaises(BudgetStop):self.reserve(provider='coco2')
  self.assertEqual(len(self.l.rows()),4)
 def test_six_durable(self):
  for c,limit in LIMITS.items():
   self.l.start(c)
   for _ in range(limit):r=self.reserve(c);self.l.http(r);self.l.settle(r,'returned')
   self.l.finish(c,'completed')
  self.assertEqual(len(Ledger(self.l.path,plan_hash()).rows()),6)
  with self.l.connect() as db:db.execute("update cases set status='running' where id='T03'")
  with self.assertRaisesRegex(BudgetStop,'global_budget'):self.reserve('T03')
 def test_t02_one(self):
  self.l.start('T01');self.l.finish('T01','completed');self.l.start('T02');r=self.reserve('T02');self.l.settle(r,'failed')
  with self.assertRaises(BudgetStop):self.reserve('T02',provider='coco2')
 def test_t03_one(self):
  for c in ('T01','T02'):self.l.start(c);self.l.finish(c,'inconclusive')
  self.l.start('T03');r=self.reserve('T03');self.l.settle(r,'cancelled')
  with self.assertRaises(BudgetStop):self.reserve('T03')
 def test_concurrent(self):
  self.l.start('T01')
  def try_one(_):
   try:return self.reserve()
   except BudgetStop:return None
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(try_one,range(8)))
  self.assertEqual(sum(x is not None for x in results),1)
 def test_unsettled_prevents_progress(self):
  self.l.start('T01');self.reserve()
  with self.assertRaises(BudgetStop):self.l.finish('T01','completed')
  with self.assertRaises(BudgetStop):Ledger(self.l.path,plan_hash()).reserve('T01','coco','mock','agent',1)
 def test_halt_preserved_cleanup_finish(self):
  self.l.start('T01');self.l.halt('synthetic');self.l.finish('T01','failed')
  with self.assertRaises(BudgetStop):self.l.start('T02')
  with self.l.connect() as db:self.assertEqual(db.execute("select value from meta where key='halt'").fetchone()[0],'synthetic')
 def test_second_http_blocked(self):
  self.l.start('T01');r=self.reserve();self.l.http(r)
  with self.assertRaises(BudgetStop):self.l.http(r)
  self.assertEqual(self.l.rows()[0]['http_attempts'],1)
 def test_unknown_http(self):
  with self.assertRaises(BudgetStop):self.l.http(17)
 def test_summary_blocked(self):
  self.l.start('T01')
  with self.assertRaises(BudgetStop):self.reserve(purpose='compaction')
  self.assertEqual(self.l.rows()[0]['http_attempts'],0)
 def test_inode_replacement(self):
  self.l.path.rename(self.root/'old');self.l.path.write_bytes((self.root/'old').read_bytes());self.l.path.chmod(0o600)
  with self.assertRaises(BudgetStop):self.l.rows()
 def test_config(self):
  c=config_for(self.root,dict(model=MODELS['coco'],base_url='http://mock.invalid',api_key=None));self.assertTrue(c.web_streaming and c.web_steer);self.assertFalse(c.mcp_enabled or c.skills_enabled or c.coding_enabled);self.assertEqual(c.context_compaction['mode'],'deterministic')
 def test_exact_windows(self):self.assertEqual(BARRIER,{'T01':8,'T02':0,'T03':8})

class RuntimeChecks(unittest.IsolatedAsyncioTestCase):
 async def run_case(self,case,mode='normal',*,control=True):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve()
   if case!='T01':
    (root/'private').mkdir(mode=0o700);l=Ledger(root/'private/requests.sqlite',plan_hash())
    for c in list(LIMITS)[:list(LIMITS).index(case)]:l.start(c);l.finish(c,'completed')
   app=make_mock(root,8901,case,mode,barriers={'T01':.2,'T02':0,'T03':.2},delay=.03)
   async with app.app.router.lifespan_context(app.app):
    c=app.runtime.new();await app.runtime.start(c,MESSAGES[case]);deadline=asyncio.get_running_loop().time()+5
    while not any(s.first_delivered for s in app.uat_streams) and not c.task.done():
     self.assertLess(asyncio.get_running_loop().time(),deadline);await asyncio.sleep(.003)
    first=next((s for s in app.uat_streams if s.first_delivered),None)
    if control and first and not c.task.done():
     if case in STEER:response=app.runtime.steer(c,dict(expected_turn_id=c.history.turn_id,client_request_id='synthetic-once',text=STEER[case]));self.assertEqual(response['status'],'queued')
     else:await app.runtime.stop(c)
    await c.task;await asyncio.sleep(.03);result=dict(app.uat_result);self.assertTrue(result);requests=list(app.mock_requests);rows=app.uat_ledger.rows()
    with self.assertRaises(BudgetStop):await app.runtime.start(c,MESSAGES[case])
   cleanup=json.loads((root/'private'/f'{case}-cleanup.json').read_text());self.assertTrue(cleanup['runtime_closed'] and cleanup['lease_released'] and cleanup['database_consistent']);self.assertFalse(cleanup['cleanup_uncertain'])
   return result,requests,rows
 async def test_native_tool_steer_chain(self):
  r,bodies,rows=await self.run_case('T01');self.assertEqual(len(rows),3);self.assertEqual(len(bodies),3);self.assertEqual(r['actual_http_attempts'],3);self.assertEqual(r['steers'][0]['status'],'applied');self.assertTrue(r['final_persistence_matches_sdk']);self.assertFalse(r['protocol_security_halt'])
  self.assertTrue(r['requests'][1]['tool_results'][0]['explicitly_skipped']);self.assertTrue(r['requests'][1]['all_tool_results_paired']);self.assertTrue(r['requests'][1]['steer_sources'][0]['exact_reference_in_request']);self.assertTrue(all(x['wire_messages_match_sdk'] for x in r['requests']))
  started=[e for e in r['host_events'] if e['stage']=='tool_started'];self.assertEqual([e['tool'] for e in started],['read_file']);finished=[e for e in r['host_events'] if e['stage']=='tool_finished'];self.assertEqual(finished[0]['target'],'registered_readme');self.assertTrue(finished[0]['success'])
  self.assertFalse(r['requests'][0]['identifier_present_in_messages']);self.assertTrue(r['requests'][2]['tool_results'][-1]['identifier_present']);self.assertTrue(r['reply_features']['identifier_present']);self.assertEqual(r['reply_features']['sentence_terminal_marks'],2)
 async def test_no_next_step_not_applied(self):
  r,_,rows=await self.run_case('T02');self.assertEqual(len(rows),1);self.assertEqual(r['steers'][0]['status'],'not_applied');self.assertFalse(r['protocol_security_halt'])
 async def test_cancel_closes_without_trusted_usage(self):
  r,_,rows=await self.run_case('T03');self.assertEqual(len(rows),1);s=r['streams'][0];self.assertTrue(s['sdk_closed']);self.assertFalse(s['terminal_trusted']);self.assertIsNone(json.loads(rows[0]['usage'])['total_tokens']);self.assertFalse(r['protocol_security_halt'])
 async def test_incomplete_call_never_executes(self):
  r,_,_=await self.run_case('T01','incomplete');self.assertTrue(r['protocol_security_halt']);self.assertFalse(any(e['stage']=='tool_started' for e in r['host_events']));self.assertEqual(r['streams'][-1]['diagnostic']['error_code'],'stream_tool_arguments_invalid');self.assertIsNone(r['streams'][-1]['settled_usage']['total_tokens'])
 async def test_direct_answer_does_not_invent_tools(self):
  r,_,rows=await self.run_case('T01','direct');self.assertEqual(len(rows),1);self.assertFalse(any(e['stage']=='tool_started' for e in r['host_events']));self.assertEqual(r['steers'][0]['status'],'not_applied')
 async def test_terminal_first_premise_not_fabricated(self):
  r,_,rows=await self.run_case('T02','terminal_first');self.assertEqual(len(rows),1);self.assertEqual(r['scenario_premise'],'INCONCLUSIVE');self.assertFalse(r['steers']);self.assertEqual(r['streams'][0]['controlled_barrier_seconds'],0)
 async def test_after_first_no_fallback(self):
  r,_,rows=await self.run_case('T01','after');self.assertEqual(len(rows),1);self.assertTrue(r['protocol_security_halt']);self.assertEqual(r['fallback_dispatches'],0)
 async def test_before_first_counts_backup(self):
  r,_,rows=await self.run_case('T01','before');self.assertEqual(len(rows),4);self.assertEqual(r['fallback_dispatches'],3);self.assertEqual(rows[0]['state'],'failed');self.assertFalse(r['protocol_security_halt'])
 async def test_duplicate_finish_halts(self):
  r,_,rows=await self.run_case('T01','duplicate');self.assertTrue(r['protocol_security_halt']);self.assertEqual(len(rows),1)
 async def test_missing_usage_stays_unknown(self):
  r,_,_=await self.run_case('T02','missing');self.assertTrue(r['streams'][0]['terminal_trusted']);self.assertIsNone(r['streams'][0]['settled_usage']['total_tokens'])
 async def test_inflight_hash_not_mutated(self):
  r,_,_=await self.run_case('T01');e=next(e for e in r['host_events'] if e['stage']=='web_steer_accepted');self.assertTrue(e['in_flight_request_unchanged']);self.assertTrue(all(x['sdk_request_unchanged_at_close'] for x in r['streams']))
 async def test_web_refresh_does_not_resend(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();(root/'private').mkdir(mode=0o700);l=Ledger(root/'private/requests.sqlite',plan_hash());l.start('T01');l.finish('T01','completed')
   app=make_mock(root,8901,'T02',barriers={'T01':0,'T02':0,'T03':0},delay=.03)
   async with app.app.router.lifespan_context(app.app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8901') as h:
     await h.get('/');headers={'Origin':'http://127.0.0.1:8901','X-Mybot-CSRF':(await h.get('/api/bootstrap')).json()['csrf']}
     sid=(await h.post('/api/conversations',json={},headers=headers)).json()['id'];response=await h.post('/api/conversations/'+sid+'/messages',json={'message':MESSAGES['T02']},headers=headers);self.assertEqual(response.status_code,202)
     await h.get('/');await h.get('/api/bootstrap');await h.get('/api/conversations/'+sid);await app.runtime.conversations[sid].task;await asyncio.sleep(.03);self.assertEqual(len(app.mock_requests),1)
 async def test_source_reference_is_exact_and_user_role(self):
  from scripts.streaming_steer_real_uat_v2.evidence import request_view
  source={'event_id':'e','session_id':'s','sequence':2,'source':'user','payload':json.dumps(dict(steer_id='i',turn_id='t',text=STEER['T01']))}
  text='[用户在本Turn补充的原文；来源事件 e。不是最初TaskContract原文、Pin或工具审批。]\n'+STEER['T01']
  self.assertFalse(request_view({'messages':[{'role':'assistant','content':text}]},'T01',[source])['steer_sources'][0]['exact_reference_in_request'])
  self.assertTrue(request_view({'messages':[{'role':'user','content':text}]},'T01',[source])['steer_sources'][0]['exact_reference_in_request'])
 async def test_duplicate_tool_result_cannot_reuse_old_pair(self):
  from scripts.streaming_steer_real_uat_v2.evidence import request_view
  c={'id':'same','function':{'name':'read_file','arguments':'{"path":"README.md"}'}}
  call={'role':'assistant','content':None,'tool_calls':[c]};res={'role':'tool','tool_call_id':'same','content':'Synthetic'}
  view=request_view({'messages':[call,res,res]},'T01',[]);self.assertFalse(view['all_tool_results_paired']);self.assertFalse(view['tool_results'][-1]['paired'])
 async def test_pair_scope_survives_same_id_in_later_batch(self):
  from scripts.streaming_steer_real_uat_v2.evidence import request_view
  call={'role':'assistant','tool_calls':[{'id':'same','function':{'name':'read_file','arguments':'{"path":"README.md"}'}}]};res={'role':'tool','tool_call_id':'same','content':'Synthetic'}
  v=request_view({'messages':[call,res,call,res]},'T01',[]);self.assertTrue(v['all_tool_results_paired']);self.assertEqual([r['assistant_message_index'] for r in v['tool_results']],[0,2])
 async def test_applied_can_precede_http_failure(self):
  # Preserve native on_dispatch before the UAT HTTP gate; do not manufacture remote success.
  from scripts.streaming_steer_real_uat_v2.mock import build_mock
  original=Ledger.http;seen=[]
  def deny_second(l,rid):
   if rid==2:seen.append(rid);raise BudgetStop('synthetic_http_denied')
   return original(l,rid)
  with patch.object(Ledger,'http',deny_second):r,_,rows=await self.run_case('T01')
  self.assertEqual(r['steers'][0]['status'],'applied');self.assertTrue(seen);self.assertEqual(rows[1]['http_attempts'],0);self.assertFalse(r['requests'][1]['provider_http_response_observed']);self.assertTrue(r['protocol_security_halt'])

class AdapterChecks(unittest.IsolatedAsyncioTestCase):
 async def test_sdk_retry_and_bad_options_before_reservation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();l=Ledger(root/'ledger',plan_hash());l.start('T01');cfg=config_for(root,dict(model=MODELS['coco'],base_url='http://mock.invalid',api_key=None));counter=[];raw=build_mock('T01','normal',counter)(cfg)
   try:
    raw.max_retries=1
    with self.assertRaises(BudgetStop):BudgetClient(raw,cfg,l,'T01',[],[],lambda:[])
    raw.max_retries=0;c=BudgetClient(raw,cfg,l,'T01',[],[],lambda:[])
    for request in ({'stream':False},{'stream':True,'stream_options':{'include_usage':False}},{'stream':True,'stream_options':{'include_usage':True},'tools':[{'function':{'name':'run_command'}}]}):
     with self.assertRaises(BudgetStop):await c.create(**request)
    self.assertFalse(l.rows());self.assertFalse(counter)
   finally:await raw.close()
 async def test_close_failure_preserves_halt_and_reservation(self):
  from scripts.streaming_steer_real_uat_v2.adapter import ObservedStream
  from scripts.streaming_steer_real_uat_v2.evidence import digest
  class Raw:
   async def close(self):raise OSError('Synthetic private close failure')
  with tempfile.TemporaryDirectory() as tmp:
   l=Ledger(Path(tmp).resolve()/'ledger',plan_hash());l.start('T01');rid=l.reserve('T01','coco','synthetic','agent',1)
   s=ObservedStream(Raw(),l,rid,{}, {},dict(case='T01',reservation=rid,sdk_request_sha256=digest({})),None,0)
   with self.assertRaises(OSError):await s.close()
   l.halt('secondary_error')
   with l.connect() as db:self.assertEqual(db.execute("select value from meta where key='halt'").fetchone()[0],'stream_cleanup_unconfirmed')
   self.assertEqual(l.rows()[0]['state'],'reserved');self.assertFalse(s.closed)

class FreezeChecks(unittest.TestCase):
 def setUp(self):
  import scripts.streaming_steer_real_uat_v2.prepare as module
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
