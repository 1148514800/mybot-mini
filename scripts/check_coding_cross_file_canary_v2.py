"""New native workflow and failure invariants. Only synthetic approvals, no Provider."""
import asyncio,json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from scripts.coding_cross_file_canary_v2.plan import *
from scripts.coding_cross_file_canary_v2.fixture import create,images,hashes,git
from scripts.coding_cross_file_canary_v2.integrity import IntegrityGate
from scripts.coding_cross_file_canary_v2.mock import make_mock
from scripts.coding_cross_file_canary_v2.score import acceptance,validate_fixture
from scripts.coding_cross_file_canary_v2.budget import Ledger,BudgetStop

class IntegrityChecks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();create(self.root/'workspace');self.g=IntegrityGate(self.root/'workspace',self.root/'integrity.json');self.g.initialize()
 def test_initial_clean(self):self.assertEqual(self.g.verify()['revision'],0);self.assertFalse(git(self.g.root,'status','--porcelain'))
 def test_only_public_files(self):self.assertEqual(set(images()),{'README.md','csvmini/__init__.py',*ALLOWED,'tests/test_csvmini.py','.gitignore'})
 def test_no_remote(self):self.assertEqual(git(self.g.root,'remote'),'')
 def test_owned_group(self):self.assertEqual((self.g.root/ALLOWED[0]).stat().st_gid,os.getegid())
 def test_unknown_allowed_file_change_rejected(self):
  (self.g.root/ALLOWED[0]).write_text('unknown')
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_public_test_change(self):
  (self.g.root/'tests/test_csvmini.py').write_text('pass')
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
  (self.g.root/'alias').symlink_to(self.g.root/ALLOWED[0])
  with self.assertRaises((ValueError,OSError)):self.g.verify()
 def test_forged_chain_length(self):
  p=json.loads(self.g.record.read_text());p['revision']=1;self.g.record.write_text(json.dumps(p))
  with self.assertRaises(BudgetStop):self.g.verify()
 def test_hidden_not_in_workspace(self):self.assertFalse((self.g.root/'hidden').exists());self.assertEqual(len(hashes()),7)

class BudgetChecks(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name).resolve()/'ledger';self.l=Ledger(self.path,plan_hash())
 def test_auth_early(self):
  from scripts.coding_cross_file_canary_v2.browser import run
  with self.assertRaises(RuntimeError):run(self.path.parent/'out','missing',live=True,authorization='GRANTED_2_REQUESTS')
  self.assertFalse((self.path.parent/'out').exists())
 def test_once_no_replay(self):
  self.l.start('C02');self.l.finish('C02','failed')
  with self.assertRaises(BudgetStop):Ledger(self.path,plan_hash()).start('C02')
 def test_eighteen_durable(self):
  self.l.start('C02')
  for i in range(18):r=self.l.reserve('C02','coco' if i%2 else 'coco2','synthetic','agent',1);self.l.http(r);self.l.settle(r,'returned')
  with self.assertRaises(BudgetStop):Ledger(self.path,plan_hash()).reserve('C02','coco2','synthetic','agent',1)
  self.assertEqual(len(self.l.rows()),18)
 def test_unknown_summary(self):
  self.l.start('C02')
  with self.assertRaises(BudgetStop):self.l.reserve('C02','coco','synthetic','summary',1)
  self.assertFalse(self.l.rows())
 def test_unsettled_blocks(self):
  self.l.start('C02');self.l.reserve('C02','coco','synthetic','agent',1)
  with self.assertRaises(BudgetStop):self.l.reserve('C02','coco2','synthetic','agent',1)
 def test_halt_cleanup(self):
  self.l.start('C02');self.l.halt('first');self.l.halt('secondary');self.l.finish('C02','failed')
  with self.l.connect() as d:self.assertEqual(d.execute("select value from meta where key='halt'").fetchone()[0],'first')
 def test_command_limits(self):
  c=config_for(self.path.parent,dict(model='x',base_url='http://mock.invalid'));self.assertEqual(c.coding_command['timeout_seconds'],30);self.assertEqual(c.coding_autonomy['max_model_requests'],18);self.assertFalse(c.coding_git_workflow['undo_enabled'])

class WorkflowChecks(unittest.IsolatedAsyncioTestCase):
 async def run_case(self,mode='normal',approval='approve',stop=False):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();app=make_mock(root,8904,mode,approval_timeout=.15 if approval=='timeout' else 90)
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
  r=await self.run_case();self.assertEqual(r['controller']['state'],'verified');self.assertEqual(r['revision'],1);self.assertTrue(r['score']['strict_functional_pass']);self.assertEqual(r['controller']['tests_passed_after_last_patch'],8);self.assertEqual(r['requests_count'],7);self.assertTrue(r['native_patch_chain'][0]['preview_to_commit_consistent'])
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
 async def test_budget_stops(self):self.assertLessEqual((await self.run_case('budget'))['requests_count'],18)
 async def test_stop_does_not_rollback_patch(self):
  r=await self.run_case(stop=True);self.assertEqual(r['revision'],1);self.assertNotEqual(r['controller']['state'],'verified');self.assertTrue(r['score']['strict_functional_pass'])

class FixtureChecks(unittest.IsolatedAsyncioTestCase):
 async def test_business_and_real_isolated_baseline(self):
  v=await validate_fixture();self.assertEqual(v['baseline_public']['status'],'fail');self.assertEqual(v['baseline_host']['status'],'fail');self.assertTrue(v['reference_public']['passed']);self.assertTrue(v['reference_host']['passed'])

class FreezeChecks(unittest.TestCase):
 def setUp(self):
  import scripts.coding_cross_file_canary_v2.prepare as p
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
  (self.batch/'workspace'/ALLOWED[0]).write_text('unknown')
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
   app=make_mock(self.batch,8904)
   async with app.app.router.lifespan_context(app.app):
    c=app.runtime.new();await app.runtime.start(c,MESSAGE)
    while not c.task.done():
     if c.approval.pending:c.approval.resolve(c.approval.pending['id'],True)
     await asyncio.sleep(.01)
    await asyncio.sleep(.03);self.assertEqual(c.report['state'],'verified')
  asyncio.run(exercise());v=self.p.verify_frozen(self.batch,self.config);self.assertEqual(v['usage']['attempts'],1)
  with self.assertRaises(BudgetStop):Ledger(self.batch/'private/requests.sqlite',plan_hash()).start('C02')


class ScoringChecks(unittest.TestCase):
 def test_model_claim_not_success(self):
  from scripts.coding_cross_file_canary_v2.score import assess
  score=assess({},dict(public={'passed':True},host_acceptance={'passed':True},strict_functional_pass=True),mode='LIVE',shutdown={},native_cleanup={},browser_cleanup={},scope_verified=False)
  self.assertFalse(score['strict_success']);self.assertFalse(score['dimensions']['host_controller_verified'])
 def test_synthetic_approval_not_human(self):
  from scripts.coding_cross_file_canary_v2.score import assess
  score=assess({'approvals':[dict(kind='command',approved=True)]},dict(public={'passed':True},host_acceptance={'passed':True},strict_functional_pass=True),mode='MOCK',shutdown={},native_cleanup={},browser_cleanup={},scope_verified=True)
  self.assertEqual(score['command_approval'],'SYNTHETIC_APPROVAL');self.assertFalse(score['dimensions']['human_command_approval']);self.assertFalse(score['strict_success'])

class CrossFileWorkflowChecks(unittest.IsolatedAsyncioTestCase):
 run_case=WorkflowChecks.run_case
 async def test_sequential_cumulative_journal(self):
  r=await self.run_case('sequential');self.assertEqual(r['revision'],2);self.assertEqual(r['controller']['state'],'verified');self.assertTrue(r['score']['strict_functional_pass']);a,b=r['native_patch_chain'];self.assertEqual(a['changed_files'],[ALLOWED[0]]);self.assertEqual(b['changed_files'],[ALLOWED[1]]);self.assertEqual(len(b['native_journal']['files']),2);self.assertEqual(a['after_hashes'],b['before_hashes'])
 async def test_parser_only(self):
  r=await self.run_case('parser_only');self.assertFalse(r['score']['strict_functional_pass']);self.assertEqual(r['native_patch_chain'][0]['changed_files'],[ALLOWED[0]])
 async def test_report_only(self):
  r=await self.run_case('report_only');self.assertFalse(r['score']['strict_functional_pass']);self.assertEqual(r['native_patch_chain'][0]['changed_files'],[ALLOWED[1]])
 async def test_contract_legal(self):
  r=await self.run_case('contract_legal');t=[t for t in r['tools'] if t['tool']=='record_task_contract'];self.assertEqual(len(t),1);self.assertTrue(t[0]['success']);self.assertEqual(r['controller']['state'],'verified')
 async def test_contract_illegal_auxiliary(self):
  r=await self.run_case('contract_illegal');t=[t for t in r['tools'] if t['tool']=='record_task_contract'];self.assertEqual([x['success'] for x in t],[True,False]);self.assertEqual(r['controller']['state'],'verified');self.assertTrue(r['score']['strict_functional_pass'])

class NativeMultiFileChecks(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from mybot.tools.patch import ApplyPatchTool
  from mybot.agent.git_workflow import GitBaseline,GitWorkflowSettings
  from mybot.agent.change_journal import ChangeJournal
  from scripts.coding_cross_file_canary_v2.fixture import REFERENCES
  self.references=REFERENCES;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();create(self.root/'workspace');self.g=IntegrityGate(self.root/'workspace',self.root/'integrity.json');self.g.initialize()
  self.tool=ApplyPatchTool(self.g.root,patch_mode='write',preview_receipt=True);self.tool.begin_receipt_scope();self.addCleanup(self.tool.end_receipt_scope)
  self.journal=ChangeJournal(await GitBaseline.capture(self.g.root),self.tool,GitWorkflowSettings(enabled=True));self.tool.observer=self.journal
  self.ledger=Ledger(self.root/'ledger',plan_hash());self.ledger.start('C02')
 def halted(self):
  with self.ledger.connect() as db:return bool(db.execute("select 1 from meta where key='halt'").fetchone())
 def changes(self,paths=ALLOWED):
  import hashlib
  return [dict(op='update',path=n,expected_sha256=hashlib.sha256((self.g.root/n).read_bytes()).hexdigest(),edits=[dict(old_text=(self.g.root/n).read_text(),new_text=self.references[n])]) for n in paths]
 async def preview(self):
  r=await self.tool.execute(dry_run=True,changes=self.changes());self.assertTrue(r.success);return r.metadata['commit_arguments']
 async def commit(self,args):
  from scripts.coding_cross_file_canary_v2.server import native_scope_execute
  class Registry:
   def get_tool(s,name):return self.tool
   def denied(s):raise AssertionError('unexpected scope denial')
  async def original(name,params):
   self.last_result=await self.tool.execute(**params);return self.last_result
  return await native_scope_execute(original,Registry(),self.g,self.ledger,[],'apply_patch',args)
 async def test_wrong_receipt_after_real_preview(self):
  await self.preview();r=await self.commit(dict(dry_run=False,preview_receipt='0'*64));self.assertFalse(r.success);self.assertEqual(self.g.verify()['revision'],0)
 async def test_external_change_after_preview(self):
  args=await self.preview();(self.g.root/ALLOWED[0]).write_text('external')
  with self.assertRaises(BudgetStop):await self.commit(args)
  self.assertEqual((self.g.root/ALLOWED[0]).read_text(),'external');self.assertTrue(self.halted())
 async def test_one_stale_sha_prevents_both_publications(self):
  changes=self.changes();changes[1]['expected_sha256']='0'*64;r=await self.tool.execute(dry_run=True,changes=changes);self.assertFalse(r.success);self.assertEqual(self.g.verify()['revision'],0)
 async def test_partial_publish_recovery_is_not_success(self):
  args=await self.preview();original=self.tool._publish;count=0
  def fail_second(item):
   nonlocal count
   count+=1
   if count==2:raise OSError('synthetic second publication failure')
   return original(item)
  with patch.object(self.tool,'_publish',side_effect=fail_second):
   with self.assertRaises(BudgetStop):await self.commit(args)
  self.assertEqual(self.journal.revision,0);self.assertFalse(self.last_result.success);self.assertIn(self.last_result.metadata['status'],('commit_failed_rolled_back','partial_failure_possible','rollback_conflict'));self.assertTrue(self.halted())
 async def test_uncertain_journal_commit_halts(self):
  args=await self.preview()
  with patch.object(self.journal,'after_success',side_effect=OSError('synthetic journal failure')):
   with self.assertRaises(BudgetStop):await self.commit(args)
  self.assertTrue(self.halted());self.assertFalse(self.journal.valid)
 async def test_broken_revision_hash_map(self):
  await self.commit(await self.preview());p=json.loads(self.g.record.read_text());p['native_patch_chain'][0]['before_hashes'][ALLOWED[1]]='0'*64;self.g.record.write_text(json.dumps(p))
  with self.assertRaises(BudgetStop):self.g.verify()
 async def test_journal_file_set_mismatch(self):
  await self.commit(await self.preview());p=json.loads(self.g.record.read_text());p['native_patch_chain'][0]['native_journal']['files'].pop();self.g.record.write_text(json.dumps(p))
  with self.assertRaises(BudgetStop):self.g.verify()
 async def test_receipt_hash_proof_mismatch(self):
  args=await self.preview();before=self.g.verify();r=await self.tool.execute(**args);r.metadata['after_sha256'][ALLOWED[1]]='0'*64
  with self.assertRaises(BudgetStop):self.g.accept_native_patch(before,self.journal,r)
 async def test_each_module_has_independent_real_bug(self):
  from mybot.evaluation.coding_judge import run_suite
  from mybot.evaluation.coding_fixtures import Image
  for fixed in ALLOWED:
   candidate=images(hidden=True);candidate[fixed]=Image(self.references[fixed].encode(),0o644);r=await run_suite(candidate,18,hidden=True,timeout=10,output_limit=8192);self.assertFalse(r['passed'])



class PhysicalSDKBudgetChecks(unittest.IsolatedAsyncioTestCase):
 async def test_eighteenth_failure_blocks_actual_fallback_http(self):
  import httpx
  from dataclasses import replace
  from openai import AsyncOpenAI
  from mybot.provider_failover import ProviderFailoverClient
  from mybot.runtime_accounting import RuntimeAccounting
  from scripts.coding_cross_file_canary_v2.adapter import BudgetClient
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();l=Ledger(root/'ledger',plan_hash());l.start('C02')
   for _ in range(17):
    rid=l.reserve('C02','coco','synthetic','agent',1);l.http(rid);l.settle(rid,'returned')
   cfg=config_for(root,dict(model='deepseek-v4.1-flash',base_url='http://mock.invalid',api_key='synthetic'));backup=replace(cfg,provider='coco2',model='glm-5.3-flash');sends=[];streams=[];requests=[]
   async def handle(request):
    sends.append(request);return httpx.Response(503,json={'error':{'message':'synthetic'}})
   def wrap(settings):return BudgetClient(AsyncOpenAI(api_key='synthetic',base_url='http://mock.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle))),settings,l,'C02',streams,requests,lambda:[])
   client=ProviderFailoverClient(wrap(cfg),cfg,backup,wrap)
   try:
    with self.assertRaises(BudgetStop):await RuntimeAccounting().request(client,cfg,dict(model=cfg.model,messages=[dict(role='user',content='synthetic')],stream=True,stream_options={'include_usage':True}))
   finally:await client.close()
   self.assertEqual(len(sends),1);self.assertEqual(len(l.rows()),18);self.assertEqual(sum(r['http_attempts'] for r in l.rows()),18);self.assertEqual(l.rows()[-1]['state'],'failed');self.assertFalse(any(r['state']=='reserved' for r in l.rows()))

class HostBehaviorChecks(unittest.IsolatedAsyncioTestCase):
 async def test_legitimate_direct_import_dependency_accepted(self):
  from scripts.coding_cross_file_canary_v2.fixture import REFERENCES
  from mybot.evaluation.coding_fixtures import Image
  from mybot.evaluation.coding_judge import run_suite
  candidate=images(fixed=True,hidden=True);alternate=REFERENCES[ALLOWED[1]].replace('from . import parser','from .parser import parse_records').replace('parser.parse_records(csv_text)','parse_records(csv_text)');candidate[ALLOWED[1]]=Image(alternate.encode(),0o644)
  self.assertTrue((await run_suite(candidate,18,hidden=True,timeout=10,output_limit=8192))['passed'])

class CrossFileScoringChecks(unittest.TestCase):
 def test_one_owned_file_never_strict_even_with_functional_claim(self):
  from scripts.coding_cross_file_canary_v2.score import assess
  evidence=dict(native_patch_chain=[dict(changed_files=[ALLOWED[0]],before_hashes={n:'before' for n in ALLOWED},after_hashes={ALLOWED[0]:'after',ALLOWED[1]:'before'})])
  r=assess(evidence,dict(public={'passed':True},host_acceptance={'passed':True},strict_functional_pass=True),mode='LIVE',shutdown={},native_cleanup={},browser_cleanup={},scope_verified=True)
  self.assertFalse(r['dimensions']['both_files_legally_modified']);self.assertFalse(r['strict_success'])
 def test_old_grant_not_admitted(self):
  from scripts.coding_cross_file_canary_v2.browser import run
  with tempfile.TemporaryDirectory() as tmp:
   for auth in ('GRANTED_12_REQUESTS','GRANTED_6_REQUESTS','NOT_GRANTED'):
    with self.assertRaises(RuntimeError):run(Path(tmp)/'never-created','not-a-browser',live=True,authorization=auth)
   self.assertFalse((Path(tmp)/'never-created').exists())

if __name__=='__main__':unittest.main()
