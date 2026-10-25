"""New offline UAT gates; actual SDK via MockTransport, never Live scoring."""
import asyncio,json,tempfile,unittest,subprocess,sys
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import httpx
from openai import AsyncOpenAI
from mybot.runtime_accounting import RuntimeAccounting,CURRENT
from mybot.provider_failover import ProviderFailoverClient
from scripts.persistent_uat.budget import Ledger,BudgetClient,BudgetStop
from scripts.persistent_uat.plan import plan_hash,LIMITS,MESSAGES,PINS,OLD,NEW,config_for,span
from scripts.persistent_uat import prepare as prep
from scripts.persistent_uat.server import make_app,require_authorization
from scripts.persistent_uat.evidence import information_loss,inclusion
from scripts.check_real_user_uat import reply

PROVIDER=dict(model='deepseek-v4.1-flash',api_key='synthetic-only-key',base_url='https://offline.invalid/v1')

class PersistentUATChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='persistent-uat-offline-');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.ledger=Ledger(self.root/'requests.sqlite',plan_hash());self.ledger.start('L01');self.cfg=config_for(self.root,PROVIDER)
        self.token=CURRENT.set(RuntimeAccounting());self.addCleanup(CURRENT.reset,self.token)
    def request(self):return dict(model=self.cfg.model,messages=[dict(role='user',content='OFFLINE MOCK')],max_tokens=100)
    def raw(self,handler,**kw):return AsyncOpenAI(api_key=PROVIDER['api_key'],base_url=PROVIDER['base_url'],max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler),**kw))
    async def test_not_granted_precedes_all_state_and_credentials(self):
        with patch('scripts.persistent_uat.server.credentials') as cred,patch('scripts.persistent_uat.server.verify_frozen') as verify,patch('scripts.persistent_uat.server.build_client') as build:
            with self.assertRaises(BudgetStop):make_app('L01',self.root/'absent',self.root/'no-key')
        cred.assert_not_called();verify.assert_not_called();build.assert_not_called()
    def test_only_exact_authorization_string(self):
        for value in (True,None,'GRANTED','GRANTED_34_REQUESTS','GRANTED_16_REQUESTS '):
            with self.assertRaises(BudgetStop):require_authorization(value)
    def test_durable_16_and_no_case_rerun(self):
        for case,count in LIMITS.items():
            if case!='L01':self.ledger.start(case)
            for _ in range(count):self.ledger.reserve(case,'coco','mock','agent',1)
            # Reservations without HTTP remain conservatively counted. Settle explicitly for this cap test.
            for row in self.ledger.rows():
                if row['state']=='reserved':self.ledger.settle(row['id'],'cancelled')
            self.ledger.finish(case)
        reopened=Ledger(self.ledger.path,plan_hash());self.assertEqual(len(reopened.rows()),16)
        with self.assertRaises(BudgetStop):reopened.start('L01')
        with reopened.connect() as db:db.execute("UPDATE cases SET status='running' WHERE id='L03'")
        with self.assertRaisesRegex(BudgetStop,'global_budget'):reopened.reserve('L03','coco','mock','agent',1)
    def test_case_budget_cannot_borrow(self):
        self.ledger.finish('L01');self.ledger.start('L02')
        for _ in range(4):self.ledger.reserve('L02','coco','mock','agent',1)
        with self.assertRaisesRegex(BudgetStop,'case_budget'):self.ledger.reserve('L02','coco2','mock','agent',1)
    def test_concurrent_reservations_atomic(self):
        def reserve(_):
            try:return self.ledger.reserve('L01','coco','mock','agent',1)
            except BudgetStop:return None
        with ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(reserve,range(30)))
        self.assertEqual(sum(x is not None for x in ids),10)
    def test_unknown_old_case_and_wrong_order_rejected(self):
        for case in ('T01','U01','L03'):
            with self.assertRaises(BudgetStop):self.ledger.start(case)
    def test_process_restart_does_not_reset(self):
        self.ledger.reserve('L01','coco','mock','agent',1)
        code="from scripts.persistent_uat.budget import Ledger;from scripts.persistent_uat.plan import plan_hash;import sys;s=Ledger(sys.argv[1],plan_hash());assert len(s.rows())==1"
        child=subprocess.run([sys.executable,'-c',code,str(self.ledger.path)],capture_output=True,timeout=15);self.assertEqual(child.returncode,0)
        reopened=Ledger(self.ledger.path,plan_hash())
        with self.assertRaises(BudgetStop):reopened.start('L02')
    def test_summary_attempt_counted_and_halts_without_send(self):
        with self.assertRaises(BudgetStop):self.ledger.reserve('L01','coco','mock','compaction',1)
        self.assertEqual((len(self.ledger.rows()),self.ledger.rows()[0]['http_attempts']),(1,0))
        with self.assertRaises(BudgetStop):self.ledger.reserve('L01','coco','mock','agent',1)
    async def test_reservation_committed_before_transport(self):
        observed=[]
        def handler(request):observed.append(Ledger(self.ledger.path,plan_hash()).rows());return reply()
        client=BudgetClient(self.raw(handler),self.cfg,self.ledger,'L01')
        try:await client.create(**self.request())
        finally:await client.close()
        self.assertEqual((observed[0][0]['state'],observed[0][0]['http_attempts']),('reserved',1))
    async def test_primary_backup_share_cap(self):
        sends=[]
        def handler(request):sends.append(1);return httpx.Response(503,json={'error':{'message':'mock'}}) if len(sends)==1 else reply()
        def factory(cfg):return BudgetClient(self.raw(handler),cfg,self.ledger,'L01')
        gateway=ProviderFailoverClient(factory(self.cfg),self.cfg,replace(self.cfg,provider='coco2',model='glm-5.3-flash'),factory)
        try:await gateway.create(**self.request())
        finally:await gateway.close()
        self.assertEqual([r['provider'] for r in self.ledger.rows()],['coco','coco2']);self.assertEqual(len(sends),2)
    async def test_backup_after_cap_has_no_second_send(self):
        for _ in range(9):self.ledger.reserve('L01','coco','mock','agent',1)
        sends=[]
        def handler(request):sends.append(1);return httpx.Response(503,json={'error':{'message':'mock'}})
        def factory(cfg):return BudgetClient(self.raw(handler),cfg,self.ledger,'L01')
        gateway=ProviderFailoverClient(factory(self.cfg),self.cfg,replace(self.cfg,provider='coco2',model='glm-5.3-flash'),factory)
        try:
            with self.assertRaises(BudgetStop):await gateway.create(**self.request())
        finally:await gateway.close()
        self.assertEqual(len(sends),1)
    async def test_redirect_second_send_is_blocked(self):
        sends=[]
        def handler(request):sends.append(1);return httpx.Response(307,headers={'location':'https://offline.invalid/again'})
        client=BudgetClient(self.raw(handler,follow_redirects=True),self.cfg,self.ledger,'L01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
        finally:await client.close()
        self.assertEqual(len(sends),1)
        with self.assertRaises(BudgetStop):self.ledger.reserve('L01','coco','mock','agent',1)
    async def test_unexpected_sdk_internal_retry_is_blocked_at_http(self):
        sends=[]
        def handler(request):sends.append(1);return httpx.Response(500,json={'error':{'message':'mock retry'}})
        original=self.raw(handler);retrying=original.with_options(max_retries=2)
        # Simulates a hidden retry path despite the outer client's max_retries=0.
        original.chat.completions.create=retrying.chat.completions.create
        client=BudgetClient(original,self.cfg,self.ledger,'L01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
        finally:await client.close()
        self.assertEqual(len(sends),1)
        with self.assertRaises(BudgetStop):self.ledger.reserve('L01','coco','mock','agent',1)
    async def test_environment_rechecked_before_http(self):
        sends=[];checks=[]
        def verify():
            checks.append(1)
            if len(checks)==2:self.ledger.halt('changed');raise BudgetStop('changed_before_http')
        self.ledger.verify=verify;client=BudgetClient(self.raw(lambda r:(sends.append(1),reply())[1]),self.cfg,self.ledger,'L01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
        finally:await client.close()
        self.assertEqual(sends,[]);self.assertEqual(self.ledger.rows()[0]['http_attempts'],0)
    async def test_no_reservation_no_send(self):
        sends=[];client=BudgetClient(self.raw(lambda r:(sends.append(1),reply())[1]),self.cfg,self.ledger,'L01')
        try:
            with self.assertRaises(Exception):await client.original.chat.completions.create(**self.request())
        finally:await client.close()
        self.assertEqual(sends,[])
    async def test_sdk_retry_mutation_refused(self):
        sends=[];client=BudgetClient(self.raw(lambda r:(sends.append(1),reply())[1]),self.cfg,self.ledger,'L01');client.original.max_retries=2
        try:
            with self.assertRaises(BudgetStop):await client.create(**self.request())
        finally:await client.close()
        self.assertEqual(sends,[])
    async def test_cancelled_request_remains_counted(self):
        entered=asyncio.Event()
        async def handler(request):entered.set();await asyncio.Event().wait()
        client=BudgetClient(self.raw(handler),self.cfg,self.ledger,'L01')
        try:
            task=asyncio.create_task(client.create(**self.request()));await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        finally:await client.close()
        self.assertEqual((self.ledger.rows()[0]['state'],self.ledger.rows()[0]['http_attempts']),('cancelled',1))
    async def test_authentication_failure_halts_next_case(self):
        client=BudgetClient(self.raw(lambda r:httpx.Response(401,json={'error':{'message':'mock'}})),self.cfg,self.ledger,'L01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
        finally:await client.close()
        self.ledger.finish('L01')
        with self.assertRaises(BudgetStop):self.ledger.start('L02')
    async def test_sdk_failure_no_implicit_retry(self):
        sends=[]
        def handler(request):sends.append(1);raise httpx.ConnectError('offline injected')
        client=BudgetClient(self.raw(handler),self.cfg,self.ledger,'L01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
        finally:await client.close()
        self.assertEqual(len(sends),1);self.assertEqual(self.ledger.rows()[0]['state'],'failed')
    def test_removed_or_replaced_ledger_refused(self):
        self.ledger.path.rename(self.root/'saved.sqlite')
        with self.assertRaises(BudgetStop):self.ledger.rows()
        self.assertFalse(self.ledger.path.exists())
    def test_public_messages_do_not_repeat_initial_pins(self):
        self.assertEqual(len(MESSAGES['L01']),9)
        for message in MESSAGES['L01'][1:]:
            for text in PINS:self.assertNotIn(text,message)
    async def test_full_web_restart_pin_flow_mocktransport_only(self):
        repo=self.root/'source';repo.mkdir();(repo/'mybot').mkdir();(repo/'mybot/sentinel.py').write_text('# frozen\n')
        subprocess.run(['git','init','-q',str(repo)],check=True);subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'-c','user.name=Offline','-c','user.email=offline@example.invalid','commit','-qm','freeze'],check=True)
        config=self.root/'providers.json';config.write_text(json.dumps({'llm':{'provider':'coco','providers':{'coco':PROVIDER,'coco2':{**PROVIDER,'model':'glm-5.3-flash'}}}}))
        batch=self.root/'batch';sends=[];sid=None;loss=[]
        def handler(request):sends.append(json.loads(request.content));return reply()
        def build(cfg):return self.raw(handler)
        with patch.object(prep,'REPO',repo):
            prep.prepare(batch,config);prep.freeze(batch,config);prep.verify_frozen(batch,config)
            with self.assertRaises(BudgetStop):prep.freeze(batch,config)
            for target in (config,batch/'prepared.json',batch/'workspace/README.md'):
                before=target.read_bytes();target.write_bytes(before+b' ')
                with self.assertRaises(BudgetStop):prep.verify_frozen(batch,config)
                target.write_bytes(before)

            with patch('scripts.persistent_uat.server.build_client',build):
                for case in LIMITS:
                    before=len(sends);app=make_app(case,batch,config,authorization='GRANTED_16_REQUESTS')
                    async with app.app.router.lifespan_context(app.app):
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8889') as http:
                            await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'Origin':'http://127.0.0.1:8889','X-Mybot-CSRF':boot['csrf']}
                            self.assertEqual(len(sends),before)
                            if case!='L03':c=(await http.post('/api/conversations',json={},headers=headers)).json();cid=c['id']
                            else:cid=sid;self.assertIsNone(app.runtime.conversations[cid].report);self.assertIsNone(app.runtime.conversations[cid].approval)
                            if case=='L01':sid=cid
                            async def pin(text,replace_pin=None):
                                state=(await http.get('/api/conversations/'+cid)).json();message=[m for m in state['messages'] if m['role']=='user'][-1]
                                start,end=span(message['content'],text);value=dict(message_id=message['id'],start=start,end=end,category='user_constraint',confirmed=True)
                                if replace_pin:value.update(replace_id=replace_pin['id'],expected_revision=replace_pin['revision'])
                                r=await http.post(f'/api/conversations/{cid}/pins',json=value,headers=headers);self.assertEqual(r.status_code,200)
                                return (await http.get('/api/conversations/'+cid)).json()['pins'][0]
                            old=new=None
                            for i,message in enumerate(MESSAGES[case]):
                                r=await http.post(f'/api/conversations/{cid}/messages',json={'message':message},headers=headers);self.assertEqual(r.status_code,202,r.text)
                                await app.runtime.conversations[cid].task
                                self.assertEqual(app.runtime.conversations[cid].status,'completed')
                                if case=='L01' and i==0:
                                    for text in PINS:await pin(text)
                                if case=='L02' and i==0:old=await pin(OLD)
                                if case=='L02' and i==1:
                                    await pin(NEW,old);state=(await http.get('/api/conversations/'+cid)).json();new=next(p for p in state['pins'] if p['status']=='active')
                                    r=await http.post(f'/api/conversations/{cid}/pins/{old["id"]}/revoke',json={'confirmed':True,'revision':old['revision']},headers=headers);self.assertEqual(r.status_code,409)
                                if case=='L02' and i==2:
                                    r=await http.post(f'/api/conversations/{cid}/pins/{new["id"]}/revoke',json={'confirmed':True,'revision':new['revision']},headers=headers);self.assertEqual(r.status_code,200)
                            if case=='L01':self.assertLessEqual(len(app.runtime.conversations[cid].session.export_turns()),6);self.assertEqual(len(app.runtime.conversations[cid].history.messages()),18)
                    if case=='L02':
                        files=sorted((batch/'private').glob('L02-request-*.json'));items=[json.loads(p.read_text()) for p in files];loss=[x['information_loss']['unrelated_user_unit_count'] for x in items]
                        self.assertEqual(loss,[0,0,3,5]);self.assertEqual([p['content'] for p in items[2]['pins']],[NEW]);self.assertEqual(items[3]['pins'],[])
            self.assertEqual(len(sends),14);self.assertEqual(len(Ledger(batch/'private/requests.sqlite',plan_hash()).rows()),14)
            # Frozen source/config/workspace changes are rejected without any new HTTP.
            (repo/'mybot/sentinel.py').write_text('# changed\n')
            with self.assertRaises(BudgetStop):prep.verify_frozen(batch,config)


def check_persistent_session_uat():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PersistentUATChecks))
    if not result.wasSuccessful():raise AssertionError('persistent UAT offline checks failed')
if __name__=='__main__':check_persistent_session_uat()
