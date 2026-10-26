"""Independent source-aware UAT preparation gates; HTTP only MockTransport/ASGI."""
import asyncio,json,tempfile,unittest,subprocess
from pathlib import Path
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import httpx
from openai import AsyncOpenAI
from mybot.runtime_accounting import RuntimeAccounting,CURRENT
from mybot.provider_failover import ProviderFailoverClient
from mybot.storage.history import open_store,SessionHistory
from mybot.agent.session import Session
from mybot.agent.token_counter import TokenCounter
from mybot.agent.pinned_context import PIN_LABEL
from mybot.storage.context_projection import LIFECYCLE_LABEL
from scripts.source_aware_uat.plan import LIMITS,MESSAGES,PIN_TEXT,units,pins,span,plan_hash,config_for,contract
from scripts.source_aware_uat.budget import Ledger,BudgetClient,BudgetStop
from scripts.source_aware_uat.evidence import preservation,inclusion,expected_view
from scripts.source_aware_uat.server import make_app,require_authorization
from scripts.source_aware_uat import prepare as prep
from scripts.check_real_user_uat import reply

PROVIDER=dict(model='deepseek-v4.1-flash',api_key='synthetic-only-source-aware-key',base_url='https://offline.invalid/v1')

class SourceUATChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='source-aware-uat-check-');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.ledger=Ledger(self.root/'requests.sqlite',plan_hash());self.ledger.start('S01');self.cfg=config_for(self.root,PROVIDER);self.token=CURRENT.set(RuntimeAccounting());self.addCleanup(CURRENT.reset,self.token)
    def raw(self,handler,**options):return AsyncOpenAI(api_key=PROVIDER['api_key'],base_url=PROVIDER['base_url'],max_retries=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler),**options))
    def request(self):return dict(model=self.cfg.model,messages=[dict(role='user',content='OFFLINE MOCK')],tools=None,max_tokens=100)
    def next_case(self,case):self.ledger.finish('S01');self.ledger.start(case)
    async def test_not_granted_before_credentials_verify_and_ledger(self):
        with patch('scripts.source_aware_uat.server.credentials') as c,patch('scripts.source_aware_uat.server.verify_frozen') as v,patch('scripts.source_aware_uat.server.build_client') as b:
            with self.assertRaises(BudgetStop):make_app('S01',self.root/'absent',self.root/'absent-config')
        c.assert_not_called();v.assert_not_called();b.assert_not_called();self.assertFalse((self.root/'absent').exists())
    def test_exact_new_authorization_not_old_allowance(self):
        for value in (None,True,'NOT_GRANTED','GRANTED_16_REQUESTS','GRANTED_10_REQUESTS ','GRANTED'):
            with self.assertRaises(BudgetStop):require_authorization(value)
    def test_plan_nine_messages_and_exact_spans(self):
        self.assertEqual(sum(map(len,MESSAGES.values())),9);self.assertEqual(LIMITS,{'S01':4,'S02':4,'S03':2});self.assertEqual(contract()['authorization'],'NOT_GRANTED')
        for case in LIMITS:
            for item in pins(case)+units(case):self.assertEqual(MESSAGES[case][item['source_turn']-1][slice(*item['source_span'])],item['content'])
    def test_durable_global_ten_no_reruns(self):
        for c,cap in LIMITS.items():
            if c!='S01':self.ledger.start(c)
            for _ in range(cap):rid=self.ledger.reserve(c,'coco','mock','agent',1);self.ledger.settle(rid,'cancelled')
            self.ledger.finish(c)
        reopened=Ledger(self.ledger.path,plan_hash());self.assertEqual(len(reopened.rows()),10)
        with self.assertRaises(BudgetStop):reopened.start('S01')
        with reopened.connect() as db:db.execute("UPDATE cases SET status='running' WHERE id='S03'")
        with self.assertRaisesRegex(BudgetStop,'global_budget'):reopened.reserve('S03','coco','mock','agent',1)
    def test_case_cannot_borrow_unused_capacity(self):
        self.next_case('S02')
        for _ in range(4):rid=self.ledger.reserve('S02','coco','mock','agent',1);self.ledger.settle(rid,'cancelled')
        with self.assertRaisesRegex(BudgetStop,'case_budget'):self.ledger.reserve('S02','coco2','mock','agent',1)
    def test_unique_order_and_unsettled_blocks_all(self):
        with self.assertRaises(BudgetStop):self.ledger.start('S03')
        self.ledger.reserve('S01','coco','mock','agent',1)
        with self.assertRaisesRegex(BudgetStop,'unsettled'):self.ledger.reserve('S01','coco','mock','agent',1)
        with self.assertRaises(BudgetStop):self.ledger.finish('S01')
        with self.assertRaises(BudgetStop):Ledger(self.ledger.path,plan_hash()).start('S02')
    def test_concurrent_only_one_unsettled_reservation(self):
        def reserve(_):
            try:return self.ledger.reserve('S01','coco','mock','agent',1)
            except BudgetStop:return None
        with ThreadPoolExecutor(max_workers=8) as pool:values=list(pool.map(reserve,range(12)))
        self.assertEqual(sum(x is not None for x in values),1)
    def test_unexpected_summary_counted_before_halt_without_http(self):
        with self.assertRaisesRegex(BudgetStop,'unexpected_summary'):self.ledger.reserve('S01','coco','mock','compaction',1)
        self.assertEqual((len(self.ledger.rows()),self.ledger.rows()[0]['http_attempts']),(1,0))
        with self.assertRaises(BudgetStop):self.ledger.reserve('S01','coco','mock','agent',1)
    def test_plan_mismatch_and_inode_replacement_refused(self):
        with self.assertRaises(BudgetStop):Ledger(self.ledger.path,'different-plan')
        self.ledger.path.rename(self.root/'saved.sqlite')
        with self.assertRaises(BudgetStop):self.ledger.rows()
    async def test_http_without_reservation_never_reaches_transport(self):
        sends=[];c=BudgetClient(self.raw(lambda r:(sends.append(1),reply())[1]),self.cfg,self.ledger,'S01')
        try:
            with self.assertRaises(Exception):await c.original.chat.completions.create(**self.request())
        finally:await c.close()
        self.assertEqual(sends,[])
    async def test_sdk_retry_option_refused_and_later_mutation_refused(self):
        raw=self.raw(lambda r:reply());raw.max_retries=1
        with self.assertRaises(BudgetStop):BudgetClient(raw,self.cfg,self.ledger,'S01')
        await raw.close();raw=self.raw(lambda r:reply());c=BudgetClient(raw,self.cfg,self.ledger,'S01');raw.max_retries=1
        try:
            with self.assertRaises(BudgetStop):await c.create(**self.request())
        finally:await c.close()
        self.assertEqual(self.ledger.rows(),[])
    async def test_unexpected_inner_retry_cannot_send_twice(self):
        sends=[];raw=self.raw(lambda r:(sends.append(1),httpx.Response(500,json={'error':{'message':'mock retry'}}))[1]);inner=raw.with_options(max_retries=2);raw.chat.completions.create=inner.chat.completions.create;c=BudgetClient(raw,self.cfg,self.ledger,'S01')
        try:
            with self.assertRaises(Exception):await c.create(**self.request())
        finally:await c.close()
        self.assertEqual(sends,[1]);self.assertEqual(self.ledger.rows()[0]['http_attempts'],1)
        with self.assertRaises(BudgetStop):self.ledger.reserve('S01','coco','mock','agent',1)
    async def test_redirect_cannot_hide_second_http(self):
        sends=[];c=BudgetClient(self.raw(lambda r:(sends.append(1),httpx.Response(307,headers={'location':'https://offline.invalid/again'}))[1],follow_redirects=True),self.cfg,self.ledger,'S01')
        try:
            with self.assertRaises(Exception):await c.create(**self.request())
        finally:await c.close()
        self.assertEqual(sends,[1]);self.assertEqual(self.ledger.rows()[0]['http_attempts'],1)
    async def test_failed_http_uses_one_budget_slot(self):
        c=BudgetClient(self.raw(lambda r:httpx.Response(503,json={'error':{'message':'mock'}})),self.cfg,self.ledger,'S01')
        try:
            with self.assertRaises(Exception):await c.create(**self.request())
        finally:await c.close()
        row=self.ledger.rows()[0];self.assertEqual((row['state'],row['http_attempts']),('failed',1))
    async def test_authentication_failure_halts(self):
        c=BudgetClient(self.raw(lambda r:httpx.Response(401,json={'error':{'message':'mock'}})),self.cfg,self.ledger,'S01')
        try:
            with self.assertRaises(Exception):await c.create(**self.request())
        finally:await c.close()
        with self.assertRaises(BudgetStop):self.ledger.reserve('S01','coco','mock','agent',1)
    async def test_failover_two_physical_http_attempts_same_ledger(self):
        sends=[];backup=replace(self.cfg,provider='coco2',model='glm-5.3-flash')
        c=ProviderFailoverClient(BudgetClient(self.raw(lambda r:(sends.append('DeepSeek'),httpx.Response(503,json={'error':{'message':'mock'}}))[1]),self.cfg,self.ledger,'S01'),self.cfg,backup,lambda cfg:BudgetClient(self.raw(lambda r:(sends.append('GLM'),reply())[1]),cfg,self.ledger,'S01'))
        try:await CURRENT.get().request(c,self.cfg,self.request())
        finally:await c.close()
        self.assertEqual(sends,['DeepSeek','GLM']);self.assertEqual([r['provider'] for r in self.ledger.rows()],['coco','coco2']);self.assertEqual(sum(r['http_attempts'] for r in self.ledger.rows()),2)
    async def test_backup_cannot_break_case_four(self):
        self.next_case('S02')
        for _ in range(3):rid=self.ledger.reserve('S02','coco','mock','agent',1);self.ledger.settle(rid,'cancelled')
        sends=[];backup=replace(self.cfg,provider='coco2',model='glm-5.3-flash');c=ProviderFailoverClient(BudgetClient(self.raw(lambda r:(sends.append('primary'),httpx.Response(503,json={'error':{'message':'mock'}}))[1]),self.cfg,self.ledger,'S02'),self.cfg,backup,lambda cfg:BudgetClient(self.raw(lambda r:(sends.append('backup'),reply())[1]),cfg,self.ledger,'S02'))
        try:
            with self.assertRaises(Exception):await c.create(**self.request())
        finally:await c.close()
        self.assertEqual(sends,['primary']);self.assertEqual(len(self.ledger.rows()),4)
    async def test_pretransport_integrity_rechecked(self):
        checks=[];sends=[]
        def verify():
            checks.append(1)
            if len(checks)==2:raise BudgetStop('environment_changed')
        self.ledger.verify=verify;c=BudgetClient(self.raw(lambda r:(sends.append(1),reply())[1]),self.cfg,self.ledger,'S01')
        try:
            with self.assertRaises(Exception):await c.create(**self.request())
        finally:await c.close()
        self.assertEqual(sends,[]);self.assertEqual(self.ledger.rows()[0]['http_attempts'],0)
    def metric_fixture(self,case='S01',revoke_new=False):
        cfg=config_for(self.root,PROVIDER);store=open_store(cfg,'web');self.addCleanup(store.close);h=SessionHistory(store);session=Session()
        for i,text in enumerate(MESSAGES[case][:2]):
            mid=h.start(text);session.add_turn(h.identify_turn([dict(role='user',content=text),dict(role='assistant',content='mock suggestion')]));h.finish('mock suggestion')
            spec=pins(case)[i];kw={}
            if i:kw=dict(replace_id=old['id'],expected_revision=old['revision'])
            ident=h.pins.add(mid,*spec['source_span'],'user_constraint',confirmed=True,**kw);old=next(p for p in h.pins.list() if p['id']==ident)
        if revoke_new:h.pins.revoke(old['id'],old['revision'],confirmed=True)
        return h,session
    def test_partial_source_mask_preserves_five_not_whole_turn_loss(self):
        h,s=self.metric_fixture();before=h.messages();turns=h.context_turns(s.export_turns());req={'messages':[m for t in turns for m in t]};v=preservation('S01',h,s,req,h.projection_diagnostics);self.assertEqual((v['preserved'],v['missing'],v['rate']),(5,0,1));self.assertEqual(before,h.messages());self.assertEqual(v['projection']['redacted_source_spans'],1)
    def test_revocation_preserves_five_sources(self):
        h,s=self.metric_fixture(revoke_new=True);t=h.context_turns(s.export_turns());v=preservation('S01',h,s,{'messages':[m for x in t for m in x]},h.projection_diagnostics);self.assertEqual((v['preserved'],v['missing']),(5,0));self.assertEqual(v['projection']['redacted_source_spans'],2)
    def test_assistant_only_echo_never_credits_user_preservation(self):
        h,s=self.metric_fixture();v=preservation('S01',h,s,{'messages':[dict(role='assistant',content=''.join(u['content'] for u in units('S01')))]});self.assertEqual((v['preserved'],v['missing']),(0,5));self.assertTrue(all(x['assistant_echo_present'] for x in v['units']))
    def test_same_unit_in_unmapped_user_sentence_not_credited(self):
        h,s=self.metric_fixture();v=preservation('S01',h,s,{'messages':[dict(role='user',content=''.join(u['content'] for u in units('S01')))]});self.assertEqual(v['preserved'],0)
    def test_lost_host_source_id_not_guessed_from_text(self):
        h,s=self.metric_fixture();t=h.context_turns(s.export_turns());s.restore([list(x) for x in s.export_turns()]);v=preservation('S01',h,s,{'messages':[m for x in t for m in x]});self.assertEqual(v['preserved'],0)
    def test_duplicate_sdk_views_ambiguous_not_pass(self):
        h,s=self.metric_fixture();t=h.context_turns(s.export_turns());v=preservation('S01',h,s,{'messages':[m for x in t+t for m in x]});self.assertEqual(v['preserved'],0);self.assertEqual(v['unknown'],5)
    def test_budget_omission_reported_separately_from_mask(self):
        h,s=self.metric_fixture();v=preservation('S01',h,s,{'messages':[]},{'history_turns_omitted':2,'redacted_source_spans':1});self.assertEqual(v['missing'],5);self.assertTrue(all('token_or_context_budget_history_omission' in u['possible_missing_causes'] for u in v['units']))
    def test_lifecycle_host_reference_role_enforced(self):
        h,s=self.metric_fixture();h.context_turns(s.export_turns());request={'messages':h.lifecycle_reference};self.assertEqual(inclusion(request)['lifecycle'][0]['inactive_total'],1);request['messages'][0]['role']='system'
        with self.assertRaises(ValueError):inclusion(request)
    def test_prepare_freeze_verify_only_private_mock_assets(self):
        repo=self.root/'repo';repo.mkdir();(repo/'mybot').mkdir();target=repo/'mybot/sentinel.py';target.write_text('# mock source\n');subprocess.run(['git','init','-q',str(repo)],check=True);subprocess.run(['git','-C',str(repo),'add','.'],check=True);subprocess.run(['git','-C',str(repo),'-c','user.name=Offline','-c','user.email=offline@example.invalid','commit','-qm','mock'],check=True);head=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        cfg=self.root/'mock-config.json';cfg.write_text(json.dumps({'llm':{'provider':'coco','providers':{'coco':PROVIDER,'coco2':{**PROVIDER,'model':'glm-5.3-flash'}}}}));proof=self.root/'mock-probe.json';proof.write_text(json.dumps(dict(passed=True,profiles_removed=True,server_closed=True)))
        batch=self.root/'mock-batch'
        with patch.object(prep,'REPO',repo),patch.object(prep,'BASELINE',head):
            prep.prepare(batch,cfg,proof);prep.freeze(batch,cfg);v=prep.verify_frozen(batch,cfg);self.assertEqual(v['usage'],dict(real_requests=0,attempts=0,unsettled=0,http_attempts=0))
            with self.assertRaises(BudgetStop):prep.prepare(batch,cfg,proof)
            with self.assertRaises(BudgetStop):prep.freeze(batch,cfg)
            for p in (target,cfg,batch/'workspace/README.md',batch/'prepared.json',batch/'browser-isolation.json'):
                original=p.read_bytes();p.write_bytes(original+b' ')
                with self.assertRaises(BudgetStop):prep.verify_frozen(batch,cfg)
                p.write_bytes(original)
            path=batch/'private/requests.sqlite';path.rename(path.with_name('saved.sqlite'))
            with self.assertRaises((BudgetStop,OSError)):prep.verify_frozen(batch,cfg)
    async def test_all_nine_frozen_web_turns_mock_sdk_and_sources(self):
        batch=self.root/'mock-web-batch';batch.mkdir();(batch/'private').mkdir(mode=0o700);(batch/'workspace').mkdir();provider_cfg=self.root/'unused-config';sends=[]
        def handler(r):sends.append(json.loads(r.content));return reply()
        def build(cfg):return self.raw(handler)
        def verify(*a,**k):return dict(usage=dict(unsettled=0))
        captured=[]
        with patch('scripts.source_aware_uat.server.verify_frozen',verify),patch('scripts.source_aware_uat.server.credentials',return_value={'coco':PROVIDER,'coco2':{**PROVIDER,'model':'glm-5.3-flash'}}),patch('scripts.source_aware_uat.server.build_client',build):
            for case in LIMITS:
                app=make_app(case,batch,provider_cfg,authorization='GRANTED_10_REQUESTS')
                async with app.app.router.lifespan_context(app.app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8898') as http:
                        await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'Origin':'http://127.0.0.1:8898','X-Mybot-CSRF':boot['csrf']};cid=(await http.post('/api/conversations',json={},headers=headers)).json()['id'];old=None
                        async def pin(spec,replace_pin=None):
                            state=(await http.get('/api/conversations/'+cid)).json();user=[m for m in state['messages'] if m['role']=='user'][spec['source_turn']-1];value=dict(message_id=user['id'],start=spec['source_span'][0],end=spec['source_span'][1],category='user_constraint',confirmed=True)
                            if replace_pin:value.update(replace_id=replace_pin['id'],expected_revision=replace_pin['revision'])
                            r=await http.post(f'/api/conversations/{cid}/pins',json=value,headers=headers);self.assertEqual(r.status_code,200,r.text);return next(p for p in (await http.get('/api/conversations/'+cid)).json()['pins'] if p['content']==spec['content'] and p['status']=='active')
                        for i,msg in enumerate(MESSAGES[case]):
                            r=await http.post(f'/api/conversations/{cid}/messages',json={'message':msg},headers=headers);self.assertEqual(r.status_code,202,r.text);await app.runtime.conversations[cid].task;self.assertEqual(app.runtime.conversations[cid].status,'completed')
                            actual=sends[-1];without_refs={**actual,'messages':[m for m in actual['messages'] if not (m.get('content') or '').startswith((PIN_LABEL,LIFECYCLE_LABEL))]};ctx=app.runtime.conversations[cid].resources['context'];captured.append(dict(case=case,turn=i+1,input_estimated_tokens=ctx['estimated_input_tokens'],request_chars=ctx['request_chars'],request_utf8_bytes=ctx['request_utf8_bytes'],output_reserved_tokens=ctx['output_reserved_tokens'],reference_overhead_estimated_tokens=TokenCounter.measure(actual)['estimated_input_tokens']-TokenCounter.measure(without_refs)['estimated_input_tokens'],context=ctx))
                            if i==0:
                                old=await pin(pins(case)[0])
                                if case=='S03':await pin(pins(case)[1])
                            if i==1 and case!='S03':old=await pin(pins(case)[1],old)
                            if case=='S02' and i==2:
                                r=await http.post(f'/api/conversations/{cid}/pins/{old["id"]}/revoke',json=dict(confirmed=True,revision=old['revision']),headers=headers);self.assertEqual(r.status_code,200)
                last=sorted((batch/'private').glob(case+'-request-*.json'))[-1];e=json.loads(last.read_text());self.assertEqual(e['source_preservation']['rate'],1);self.assertEqual(e['source_preservation']['preserved'],len(units(case)));self.assertTrue(e['lifecycle']);captured[-1]['final_source_preservation']=e['source_preservation'];captured[-1]['final_pins']=e['pins'];captured[-1]['final_lifecycle']=e['lifecycle'];captured[-1]['request_sha256']=e['request_sha256'];self.assertEqual(sum(len(x['active_by_category']['user_constraint']) for x in e['lifecycle']),0 if case=='S02' else 2 if case=='S03' else 1)
        ledger=Ledger(batch/'private/requests.sqlite',plan_hash());self.assertEqual((len(sends),len(ledger.rows()),sum(x['http_attempts'] for x in ledger.rows())),(9,9,9));self.assertEqual([x['state'] for x in ledger.rows()],['returned']*9);type(self).mock_flow_evidence=captured

def check_source_aware_uat(output=None):
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceUATChecks))
    if not result.wasSuccessful():raise AssertionError('source-aware UAT preparation failed')
    if output is not None:
        from scripts.uat.server import private_json
        private_json(Path(output),dict(status='MOCK_PREFLIGHT_PASS',tests=result.testsRun,real_model_requests=0,sdk_http_sends_in_frozen_flow=9,flow=SourceUATChecks.mock_flow_evidence,semantics='mechanism only; synthetic replies never graded as real model adherence'))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path);a=p.parse_args();check_source_aware_uat(a.evidence)
