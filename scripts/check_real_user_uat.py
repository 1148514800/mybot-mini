"""UAT hard gates, independent fixtures and compression calibration; no live API."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as N
import httpx
from openai import AsyncOpenAI
from mybot.agent import AgentLoop,ContextBuilder
from mybot.agent.context_compactor import PROMPT,FIELDS
from mybot.provider_failover import ProviderFailoverClient
from mybot.tools import build_default_tool_registry
from mybot.workspace import init_workspace
from scripts.uat.budget import Ledger,BudgetClient,BudgetStop,LIMITS
from scripts.uat.fixtures import create,assess,changes
from scripts.uat.plan import config_for,MESSAGES,plan_hash
from scripts.check_session import response

class UATChecks(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.ledger=Ledger(self.root/'ledger.sqlite',plan_hash())
  self.cfg=config_for('U01',self.root,dict(model='deepseek-v4.1-flash',api_key='synthetic-key',base_url='https://offline.invalid/v1'))
 def raw(self,handler,**options):
  return AsyncOpenAI(api_key='synthetic-key',base_url='https://offline.invalid/v1',max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler),**options))
 def request(self):return dict(model=self.cfg.model,messages=[dict(role='user',content='offline')],tools=None,max_tokens=100)
 async def test_case_cap_and_durable_reopen(self):
  calls=[]
  def transport(r):calls.append(r);return reply()
  self.ledger.start('U01');client=BudgetClient(self.raw(transport),self.cfg,self.ledger,'U01')
  try:
   await client.create(**self.request());await client.create(**self.request())
   reopened=Ledger(self.ledger.path,plan_hash())
   with self.assertRaises(BudgetStop):reopened.reserve('U01','coco',self.cfg.model,'agent',1)
   with self.assertRaises(BudgetStop):await client.create(**self.request())
   self.assertEqual((len(calls),sum(r['http_attempts'] for r in reopened.rows())),(2,2))
  finally:await client.close()
 async def test_global_48_and_no_restart_or_rerun(self):
  for case,cap in LIMITS.items():
   self.ledger.start(case)
   for _ in range(cap):self.ledger.reserve(case,'coco','synthetic','agent',1)
   if case!='U06':self.ledger.finish(case)
  with self.assertRaisesRegex(BudgetStop,'global_budget'):self.ledger.reserve('U06','coco','synthetic','compaction',1)
  self.ledger.finish('U06')
  with self.assertRaises(BudgetStop):Ledger(self.ledger.path,plan_hash()).start('U01')
  self.assertEqual(len(self.ledger.rows()),48)
 async def test_backup_created_later_cannot_bypass_case_cap(self):
  calls=[]
  def fail(r):calls.append('primary');return httpx.Response(503,json={'error':{'message':'offline'}})
  def ok(r):calls.append('backup');return reply()
  self.ledger.start('U01');self.ledger.reserve('U01','coco','synthetic','agent',1)
  created=[]
  def backup(c):created.append(True);return BudgetClient(self.raw(ok),c,self.ledger,'U01')
  gateway=ProviderFailoverClient(BudgetClient(self.raw(fail),self.cfg,self.ledger,'U01'),self.cfg,replace(self.cfg,provider='coco2',model='glm-5.3-flash'),backup)
  try:
   with self.assertRaises(BudgetStop):await gateway.create(**self.request())
   self.assertEqual(calls,['primary']);self.assertEqual(created,[True]);self.assertEqual(len(self.ledger.rows()),2)
  finally:await gateway.close()
 async def test_successful_fallback_both_physical_rows(self):
  calls=[]
  def transport(r):calls.append(r);return httpx.Response(503,json={'error':{'message':'offline'}}) if len(calls)==1 else reply()
  self.ledger.start('U01')
  def factory(c):return BudgetClient(self.raw(transport),c,self.ledger,'U01')
  gateway=ProviderFailoverClient(factory(self.cfg),self.cfg,replace(self.cfg,provider='coco2',model='glm-5.3-flash'),factory)
  try:await gateway.create(**self.request())
  finally:await gateway.close()
  self.assertEqual([r['provider'] for r in self.ledger.rows()],['coco','coco2']);self.assertEqual(len(calls),2)
 async def test_compaction_cancel_keeps_reservation(self):
  started=asyncio.Event()
  async def transport(r):started.set();await asyncio.Event().wait()
  self.ledger.start('U06');client=BudgetClient(self.raw(transport),self.cfg,self.ledger,'U06')
  from mybot.runtime_accounting import RuntimeAccounting,CURRENT
  accounting=RuntimeAccounting();accounting.purpose='compaction';token=CURRENT.set(accounting)
  try:
   task=asyncio.create_task(client.create(**self.request()));await started.wait();task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
  finally:CURRENT.reset(token);await client.close()
  row=Ledger(self.ledger.path,plan_hash()).rows()[0]
  self.assertEqual((row['purpose'],row['state'],row['http_attempts']),('compaction','cancelled',1))
 async def test_sdk_redirect_extra_send_fails_closed(self):
  calls=[]
  def transport(r):calls.append(r);return httpx.Response(307,headers={'location':'https://offline.invalid/v1/redirect'})
  self.ledger.start('U01');client=BudgetClient(self.raw(transport,follow_redirects=True),self.cfg,self.ledger,'U01')
  try:
   with self.assertRaises(Exception):await client.create(**self.request())
   with self.assertRaises(BudgetStop):self.ledger.reserve('U01','coco','synthetic','agent',1)
  finally:await client.close()
  self.assertEqual(len(calls),1)
 async def test_no_reservation_no_transport_and_no_hidden_sdk_retry(self):
  calls=[]
  def transport(r):calls.append(r);return httpx.Response(500,json={'error':{'message':'offline'}})
  self.ledger.start('U01');client=BudgetClient(self.raw(transport),self.cfg,self.ledger,'U01')
  try:
   with self.assertRaises(Exception):await client.original.chat.completions.create(**self.request())
   self.assertEqual(calls,[])
   with self.assertRaises(Exception):await client.create(**self.request())
   self.assertEqual(len(calls),1)
  finally:await client.close()
 async def test_concurrent_reservations_atomic_and_plan_change_denied(self):
  self.ledger.start('U05')
  def reserve(_):
   try:return self.ledger.reserve('U05','coco','synthetic','agent',1)
   except BudgetStop:return None
  with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(reserve,range(32)))
  self.assertEqual(sum(r is not None for r in results),14)
  with self.assertRaises(BudgetStop):Ledger(self.ledger.path,'changed-plan')
 async def test_authentication_error_halts_all_cases(self):
  self.ledger.start('U01');client=BudgetClient(self.raw(lambda r:httpx.Response(401,json={'error':{'message':'offline'}})),self.cfg,self.ledger,'U01')
  try:
   with self.assertRaises(Exception):await client.create(**self.request())
   self.ledger.finish('U01')
   with self.assertRaises(BudgetStop):self.ledger.start('U02')
  finally:await client.close()
 async def test_fixture_oracles_baseline_fail_and_correct_implementation_pass(self):
  root=self.root/'cache';before=create('U04',root)
  self.assertFalse((await assess('U04',root))['passed'])
  path=root/'src/clockcache/cache.py';path.write_text(path.read_text().replace('self.clock() > expires_at','self.clock() >= expires_at'))
  self.assertTrue((await assess('U04',root))['passed']);self.assertTrue((await assess('U04',root,hidden=False))['passed'])
  self.assertEqual(changes(root,before),['src/clockcache/cache.py'])
 async def test_export_oracle_requires_actual_entry_integration(self):
  root=self.root/'csv';create('U05',root)
  self.assertFalse((await assess('U05',root))['passed'])
  (root/'src/orderexport/csv_export.py').write_text("import csv,io\ndef export_rows(orders):\n s=io.StringIO(newline='');w=csv.writer(s);w.writerow(['id','name','amount'])\n for o in orders:w.writerow([o.id,o.name,format(o.amount,'.2f')])\n return s.getvalue()\n")
  self.assertFalse((await assess('U05',root))['passed'])
  (root/'src/orderexport/business.py').write_text('from .csv_export import export_rows\ndef export_orders(orders):return export_rows(orders)\n')
  self.assertTrue((await assess('U05',root))['passed'])
 async def test_preview_web_lifecycle_cannot_consume_budget(self):
  from scripts.uat.server import make_app
  batch=self.root/'batch';root=batch/'workspaces'/'U01';create('U01',root)
  app=make_app('U01',batch,self.root/'absent-private-config',preview=True)
  async with app.app.router.lifespan_context(app.app):
   self.assertFalse(app.runtime.closed)
  self.assertTrue(app.runtime.closed);self.assertEqual(app.uat_ledger.rows(),[])
 async def test_u06_real_loop_calibration_and_raw_history(self):
  root=self.root/'long';create('U06',root);cfg=config_for('U06',root,dict(model='deepseek-v4.1-flash',api_key='synthetic-key',base_url='https://offline.invalid/v1'))
  requests=[]
  async def invoke(**request):
   requests.append(request)
   if request['messages'][0]['content']==PROMPT:
    sources=json.loads(request['messages'][-1]['content']);doc={k:[] for k in FIELDS}
    source=sources[0]['messages'][0];doc['current_goal']=[dict(turn=1,message=0,quote=source['content'][:100])]
    return response(json.dumps(doc,ensure_ascii=False))
   return response('已记录这些设计约束，尚未修改文件或运行测试。')
  agent=AgentLoop(N(chat=N(completions=N(create=invoke))),cfg,build_default_tool_registry(root),ContextBuilder(root))
  statuses=[]
  for text in MESSAGES['U06']:
   await agent.handle_message(text);statuses.append(agent.last_runtime_report['context']['context_compaction_status'])
  self.assertEqual(statuses[:4],['not_needed']*4);self.assertEqual(statuses[4:],['semantic_applied']*2)
  self.assertEqual(len(requests),8);self.assertEqual(len(agent.session.export_turns()),6)
  self.assertEqual([m['content'] for t in agent.session.export_turns() for m in t if m['role']=='user'],MESSAGES['U06'])
  Path('/tmp/mybot-uat/calibration.json').write_text(json.dumps({'statuses':statuses,'logical_physical_synthetic_requests':len(requests),'input_limit':18000,'output_reserved':512}))

def reply():return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':1,'model':'synthetic','choices':[{'index':0,'message':{'role':'assistant','content':'offline'},'finish_reason':'stop'}],'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}})
if __name__=='__main__':unittest.main(verbosity=2)
