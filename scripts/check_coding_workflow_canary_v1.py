"""New native workflow and failure invariants. Only synthetic approvals, no Provider."""
import asyncio,json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from scripts.coding_workflow_canary_v1.plan import *
from scripts.coding_workflow_canary_v1.fixture import create,images,hashes,git
from scripts.coding_workflow_canary_v1.integrity import IntegrityGate
from scripts.coding_workflow_canary_v1.mock import make_mock
from scripts.coding_workflow_canary_v1.score import acceptance,validate_fixture
from scripts.coding_workflow_canary_v1.budget import Ledger,BudgetStop

class IntegrityChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();create(self.root/'workspace');self.g=IntegrityGate(self.root/'workspace',self.root/'integrity.json');self.g.initialize()
 def test_initial_clean(self):self.assertEqual(self.g.verify()['revision'],0);self.assertFalse(git(self.g.root,'status','--porcelain'))
 def test_only_public_files(self):self.assertEqual(set(images()),{'README.md','notesearch/__init__.py',ALLOWED,'tests/test_search.py','.gitignore'})
 def test_no_remote(self):self.assertEqual(git(self.g.root,'remote'),'')
 def test_owned_group(self):self.assertEqual((self.g.root/ALLOWED).stat().st_gid,os.getegid())
 def test_unknown_allowed_file_change_rejected(self):
  (self.g.root/ALLOWED).write_text('unknown')
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_public_test_change(self):
  (self.g.root/'tests/test_search.py').write_text('pass')
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_readme_change(self):
  (self.g.root/'README.md').write_text('changed')
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_git_change(self):
  (self.g.root/'.git/config').write_text('changed')
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_unknown_new_file(self):
  (self.g.root/'unexpected').write_text('changed')
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_symlink_rejected(self):
  (self.g.root/'alias').symlink_to(self.g.root/ALLOWED)
  with self.assertRaises((ValueError,OSError)):self.g.verify()
 def test_forged_chain_length(self):
  p=json.loads(self.g.record.read_text());p['revision']=1;self.g.record.write_text(json.dumps(p))
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_hidden_not_in_workspace(self):self.assertFalse((self.g.root/'hidden').exists());self.assertEqual(len(hashes()),6)

class BudgetChecks(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name).resolve()/'ledger';self.l=Ledger(self.path,plan_hash())
 def test_auth_early(self):
  from scripts.coding_workflow_canary_v1.browser import run
  with self.assertRaises(RuntimeError):run(self.path.parent/'out','missing',live=True,authorization='GRANTED_2_REQUESTS')
  self.assertFalse((self.path.parent/'out').exists())
 def test_once_no_replay(self):
  self.l.start('C01');self.l.finish('C01','failed')
  with self.assertRaises(BudgetStop):Ledger(self.path,plan_hash()).start('C01')
 def test_twelve_durable(self):
  self.l.start('C01')
  for i in range(12):r=self.l.reserve('C01','coco' if i%2 else 'coco2','synthetic','agent',1);self.l.http(r);self.l.settle(r,'returned')
  with self.assertRaises(BudgetStop):Ledger(self.path,plan_hash()).reserve('C01','coco2','synthetic','agent',1)
  self.assertEqual(len(self.l.rows()),12)
 def test_unknown_summary(self):
  self.l.start('C01')
  with self.assertRaises(BudgetStop):self.l.reserve('C01','coco','synthetic','summary',1)
  self.assertFalse(self.l.rows())
 def test_unsettled_blocks(self):
  self.l.start('C01');self.l.reserve('C01','coco','synthetic','agent',1)
  with self.assertRaises(BudgetStop):self.l.reserve('C01','coco2','synthetic','agent',1)
 def test_halt_cleanup(self):
  self.l.start('C01');self.l.halt('first');self.l.halt('secondary');self.l.finish('C01','failed')
  with self.l.connect() as d:self.assertEqual(d.execute("select value from meta where key='halt'").fetchone()[0],'first')
 def test_command_limits(self):
  c=config_for(self.path.parent,dict(model='x',base_url='http://mock.invalid'));self.assertEqual(c.coding_command['timeout_seconds'],30);self.assertEqual(c.coding_autonomy['max_model_requests'],12);self.assertFalse(c.coding_git_workflow['undo_enabled'])

class WorkflowChecks(unittest.IsolatedAsyncioTestCase):
 async def run_case(self,mode='normal',approval='approve',stop=False):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();app=make_mock(root,8903,mode,approval_timeout=.15 if approval=='timeout' else 90)
   async with app.app.router.lifespan_context(app.app):
    c=app.runtime.new();await app.runtime.start(c,MESSAGE);seen=False
    for _ in range(4000):
     if c.task.done():break
     if c.approval.pending and not seen:
      seen=True
      if stop:await app.runtime.stop(c)
      elif approval!='timeout':c.approval.resolve(c.approval.pending['id'],approval=='approve')
     await asyncio.sleep(.005)
    await c.task;await asyncio.sleep(.03)
    result=json.loads((root/'private/settled.json').read_text());result['score']=await acceptance(root/'workspace');result['requests_count']=len(app.mock_requests)
    app.uat_gate.verify()
    with self.assertRaises(BudgetStop):await app.runtime.start(c,MESSAGE)
   result['cleanup']=json.loads((root/'private/cleanup.json').read_text());self.assertTrue(result['cleanup']['sdk_closed']);self.assertEqual(result['cleanup']['lease_released'],not result['cleanup']['cleanup_uncertain']);return result
 async def test_native_success(self):
  r=await self.run_case();self.assertEqual(r['controller']['state'],'verified');self.assertEqual(r['revision'],1);self.assertTrue(r['score']['strict_functional_pass']);self.assertEqual(r['controller']['tests_passed_after_last_patch'],5);self.assertEqual(r['requests_count'],6);self.assertTrue(r['native_patch_chain'][0]['preview_to_commit_consistent'])
 async def test_no_patch_not_success(self):self.assertFalse((await self.run_case('no_patch'))['score']['strict_functional_pass'])
 async def test_preview_only_not_committed(self):self.assertEqual((await self.run_case('preview_only'))['revision'],0)
 async def test_invalid_receipt(self):self.assertEqual((await self.run_case('invalid_receipt'))['revision'],0)
 async def test_wrong_sha(self):self.assertEqual((await self.run_case('wrong_sha'))['revision'],0)
 async def test_scope_denied(self):
  r=await self.run_case('scope');self.assertEqual(r['revision'],0);self.assertTrue(any(t.get('authority_denied') for t in r['tools']))
 async def test_denied_command(self):
  r=await self.run_case(approval='deny');self.assertNotEqual(r['controller']['state'],'verified');self.assertTrue(r['approvals'] and not r['approvals'][0]['approved'])
 async def test_timeout_command(self):self.assertNotEqual((await self.run_case(approval='timeout'))['controller']['state'],'verified')
 async def test_failing_public_test(self):
  r=await self.run_case('bad_fix');self.assertFalse(r['score']['strict_functional_pass']);self.assertNotEqual(r['controller']['state'],'verified')
 async def test_patch_without_test(self):self.assertEqual((await self.run_case('no_test'))['controller']['state'],'edited_unverified')
 async def test_new_patch_invalidates_test(self):
  r=await self.run_case('stale_after_test');self.assertEqual(r['revision'],2);self.assertEqual(r['controller']['verification'],'pending');self.assertNotEqual(r['controller']['state'],'verified')
 async def test_incomplete_tool_never_executed(self):
  r=await self.run_case('incomplete');self.assertEqual(r['revision'],0);self.assertFalse(r['tools']);self.assertEqual(r['streams'][0]['diagnostic']['error_code'],'stream_tool_arguments_invalid')
 async def test_stream_interruption(self):
  r=await self.run_case('broken_stream');self.assertFalse(r['streams'][0]['terminal_trusted']);self.assertEqual(r['revision'],0)
 async def test_budget_stops(self):self.assertLessEqual((await self.run_case('budget'))['requests_count'],12)
 async def test_stop_does_not_rollback_patch(self):
  r=await self.run_case(stop=True);self.assertEqual(r['revision'],1);self.assertNotEqual(r['controller']['state'],'verified');self.assertTrue(r['score']['strict_functional_pass'])

class FixtureChecks(unittest.IsolatedAsyncioTestCase):
 async def test_business_and_real_isolated_baseline(self):
  v=await validate_fixture();self.assertEqual(v['baseline_public']['status'],'fail');self.assertEqual(v['baseline_host']['status'],'fail');self.assertTrue(v['reference_public']['passed']);self.assertTrue(v['reference_host']['passed'])

class FreezeChecks(unittest.TestCase):
 def setUp(self):
  import scripts.coding_workflow_canary_v1.prepare as p
  self.p=p;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.batch=self.root/'batch';self.config=self.root/'config';self.config.write_text('synthetic-only');self.probe=self.root/'probe';self.probe.write_text(json.dumps(dict(passed=True,profiles_removed=True,server_closed=True)));head=create(self.root/'operator')
  self.patches=[patch.object(p,'provider_snapshot',side_effect=lambda x:dict(hash=p.file_hash(x))),patch.object(p,'sources',return_value={'synthetic':'source-hash'}),patch.object(p,'REPO',self.root/'operator'),patch.object(p,'BASELINE',head),patch.object(p,'validate_fixture',return_value={'baseline_public':{'status':'fail'},'baseline_host':{'status':'fail'},'reference_public':{'passed':True},'reference_host':{'passed':True}})]
  for x in self.patches:x.start();self.addCleanup(x.stop)
  p.prepare(self.batch,self.config,self.probe)
 def test_zero_freeze(self):self.p.freeze(self.batch,self.config);self.assertEqual(self.p.verify_frozen(self.batch,self.config)['usage']['real_requests'],0)
 def test_prepare_unique(self):
  with self.assertRaises(BudgetStop):self.p.prepare(self.batch,self.config,self.probe)
 def test_freeze_unique(self):
  self.p.freeze(self.batch,self.config)
  with self.assertRaises(BudgetStop):self.p.freeze(self.batch,self.config)
 def test_unknown_drift_before_freeze(self):
  (self.batch/'workspace'/ALLOWED).write_text('unknown')
  with self.assertRaises(BudgetStop):self.p.freeze(self.batch,self.config)
 def test_provider_change(self):
  self.p.freeze(self.batch,self.config);self.config.write_text('changed')
  with self.assertRaises(BudgetStop):self.p.verify_frozen(self.batch,self.config)
 def test_source_change(self):
  self.p.freeze(self.batch,self.config)
  with patch.object(self.p,'sources',return_value={}),self.assertRaises(BudgetStop):self.p.verify_frozen(self.batch,self.config)
 def test_database_identity(self):
  self.p.freeze(self.batch,self.config);path=self.batch/'private/session-events.sqlite3';path.rename(path.with_suffix('.old'));path.write_bytes(path.with_suffix('.old').read_bytes());path.chmod(0o600)
  with self.assertRaises(BudgetStop):self.p.verify_frozen(self.batch,self.config)
 def test_legal_native_patch_after_freeze(self):
  self.p.freeze(self.batch,self.config)
  async def exercise():
   app=make_mock(self.batch,8903)
   async with app.app.router.lifespan_context(app.app):
    c=app.runtime.new();await app.runtime.start(c,MESSAGE)
    while not c.task.done():
     if c.approval.pending:c.approval.resolve(c.approval.pending['id'],True)
     await asyncio.sleep(.01)
    await asyncio.sleep(.03);self.assertEqual(c.report['state'],'verified')
  asyncio.run(exercise());v=self.p.verify_frozen(self.batch,self.config);self.assertEqual(v['usage']['attempts'],1)
  with self.assertRaises(BudgetStop):Ledger(self.batch/'private/requests.sqlite',plan_hash()).start('C01')

if __name__=='__main__':unittest.main()

class ScoringChecks(unittest.TestCase):
 def test_model_claim_not_success(self):
  from scripts.coding_workflow_canary_v1.score import assess
  score=assess({},dict(public={'passed':True},host_acceptance={'passed':True},strict_functional_pass=True),mode='LIVE',shutdown={},native_cleanup={},browser_cleanup={},scope_verified=False)
  self.assertFalse(score['strict_success']);self.assertFalse(score['dimensions']['host_controller_verified'])
 def test_synthetic_approval_not_human(self):
  from scripts.coding_workflow_canary_v1.score import assess
  score=assess({'approvals':[dict(kind='command',approved=True)]},dict(public={'passed':True},host_acceptance={'passed':True},strict_functional_pass=True),mode='MOCK',shutdown={},native_cleanup={},browser_cleanup={},scope_verified=True)
  self.assertEqual(score['command_approval'],'SYNTHETIC_APPROVAL');self.assertFalse(score['dimensions']['human_command_approval']);self.assertFalse(score['strict_success'])
