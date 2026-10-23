"""New UAT v2 gates. OFFLINE/SYNTHETIC; SDK traffic uses MockTransport only."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
import httpx
from openai import AsyncOpenAI
from scripts.uat_v2.budget import Ledger,LIMITS,GLOBAL_LIMIT,BudgetClient,BudgetStop
from scripts.uat_v2.plan import plan_hash,config_for,MESSAGES
from scripts.uat_v2.calibrate import PROVIDER,calibrate
from scripts.uat_v2.fixtures import create,fingerprint
from scripts.uat_v2.preflight import require_environment,check_environment
from scripts.uat_v2.oracles import assess
from scripts.uat_v2.server import make_app,preview_app,bind_task_contract
from scripts.check_real_user_uat import reply
from mybot.provider_failover import ProviderFailoverClient

class TargetedChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='uat-v2-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.ledger=Ledger(self.root/'ledger.sqlite',plan_hash())
        self.cfg=config_for('T01',self.root,PROVIDER)
    def raw(self,handler,**options):
        return AsyncOpenAI(api_key='synthetic-only-key',base_url='https://offline.invalid/v1',max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler),**options))
    def request(self):return dict(model=self.cfg.model,messages=[dict(role='user',content='OFFLINE')],max_tokens=100)
    async def test_not_granted_before_credentials_or_client(self):
        with patch('scripts.uat_v2.server.credentials') as read,patch('scripts.uat_v2.server.build_gateway_client') as build:
            with self.assertRaisesRegex(BudgetStop,'not_granted'):make_app('T01',self.root,'absent')
        read.assert_not_called();build.assert_not_called();self.assertEqual(self.ledger.rows(),[])
    async def test_34_durable_global_and_no_reopen_rerun(self):
        for case,limit in LIMITS.items():
            self.ledger.start(case)
            for _ in range(limit):self.ledger.reserve(case,'coco','synthetic','agent',1)
            if case!='T03':self.ledger.finish(case)
        reopened=Ledger(self.ledger.path,plan_hash())
        with self.assertRaisesRegex(BudgetStop,'global_budget'):reopened.reserve('T03','coco','synthetic','agent',1)
        self.assertEqual(len(reopened.rows()),34)
        reopened.finish('T03')
        with self.assertRaises(BudgetStop):reopened.start('T01')
    async def test_no_transfer_unused_budget(self):
        self.ledger.start('T01');self.ledger.finish('T01');self.ledger.start('T02')
        for _ in range(14):self.ledger.reserve('T02','coco','synthetic','agent',1)
        with self.assertRaisesRegex(BudgetStop,'case_budget'):self.ledger.reserve('T02','coco','synthetic','agent',1)
    async def test_unknown_old_case_denied(self):
        with self.assertRaises(BudgetStop):self.ledger.start('U04')
        with self.assertRaises(BudgetStop):self.ledger.reserve('U05','coco','synthetic','agent',1)
    async def test_concurrent_cap_atomic(self):
        self.ledger.start('T01')
        def reserve(_):
            try:return self.ledger.reserve('T01','coco','synthetic','agent',1)
            except BudgetStop:return None
        with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(reserve,range(28)))
        self.assertEqual(sum(x is not None for x in rows),12)
        with self.assertRaises(BudgetStop):Ledger(self.ledger.path,'different-plan')
    async def test_reservation_committed_before_mock_send(self):
        self.ledger.start('T01');observed=[]
        def transport(request):observed.append(Ledger(self.ledger.path,plan_hash()).rows());return reply()
        client=BudgetClient(self.raw(transport),self.cfg,self.ledger,'T01')
        try:await client.create(**self.request())
        finally:await client.close()
        self.assertEqual(observed[0][0]['http_attempts'],1);self.assertEqual(observed[0][0]['state'],'reserved')
    async def test_failure_and_sdk_retries_zero(self):
        self.ledger.start('T01');calls=[]
        def transport(request):calls.append(1);return httpx.Response(500,json={'error':{'message':'synthetic'}})
        client=BudgetClient(self.raw(transport),self.cfg,self.ledger,'T01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
            self.assertEqual(len(calls),1);self.assertEqual(self.ledger.rows()[0]['state'],'failed')
        finally:await client.close()
    async def test_primary_backup_unified_reservations(self):
        self.ledger.start('T01');calls=[]
        def handler(request):calls.append(1);return httpx.Response(503,json={'error':{'message':'synthetic'}}) if len(calls)==1 else reply()
        def factory(cfg):return BudgetClient(self.raw(handler),cfg,self.ledger,'T01')
        gateway=ProviderFailoverClient(factory(self.cfg),self.cfg,replace(self.cfg,provider='coco2',model='glm-5.3-flash'),factory)
        try:await gateway.create(**self.request())
        finally:await gateway.close()
        self.assertEqual([r['provider'] for r in self.ledger.rows()],['coco','coco2'])
    async def test_delayed_backup_cannot_exceed_case_cap(self):
        self.ledger.start('T01')
        for _ in range(11):self.ledger.reserve('T01','coco','synthetic','agent',1)
        sends=[]
        def handler(request):sends.append(1);return httpx.Response(503,json={'error':{'message':'synthetic'}})
        def factory(cfg):return BudgetClient(self.raw(handler),cfg,self.ledger,'T01')
        gateway=ProviderFailoverClient(factory(self.cfg),self.cfg,replace(self.cfg,provider='coco2',model='glm-5.3-flash'),factory)
        try:
            with self.assertRaises(BudgetStop):await gateway.create(**self.request())
        finally:await gateway.close()
        self.assertEqual(len(sends),1);self.assertEqual(len(self.ledger.rows()),12)
    async def test_redirect_second_send_halts_batch(self):
        self.ledger.start('T01');calls=[]
        def transport(request):calls.append(1);return httpx.Response(307,headers={'location':'https://offline.invalid/again'})
        client=BudgetClient(self.raw(transport,follow_redirects=True),self.cfg,self.ledger,'T01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
        finally:await client.close()
        self.assertEqual(len(calls),1)
        with self.assertRaises(BudgetStop):self.ledger.reserve('T01','coco','synthetic','agent',1)
    async def test_no_reservation_no_transport(self):
        calls=[];client=BudgetClient(self.raw(lambda r:(calls.append(1),reply())[1]),self.cfg,self.ledger,'T01')
        try:
            with self.assertRaises(Exception):await client.original.chat.completions.create(**self.request())
        finally:await client.close()
        self.assertEqual(calls,[])
    async def test_summary_cancel_stays_counted(self):
        from mybot.runtime_accounting import RuntimeAccounting,CURRENT
        self.ledger.start('T03');started=asyncio.Event()
        async def handler(request):started.set();await asyncio.Event().wait()
        client=BudgetClient(self.raw(handler),self.cfg,self.ledger,'T03');accounting=RuntimeAccounting();accounting.purpose='compaction';token=CURRENT.set(accounting)
        try:
            task=asyncio.create_task(client.create(**self.request()));await started.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        finally:CURRENT.reset(token);await client.close()
        row=self.ledger.rows()[0];self.assertEqual((row['purpose'],row['state'],row['http_attempts']),('compaction','cancelled',1))
    async def test_authentication_failure_stops_next_case(self):
        self.ledger.start('T01');client=BudgetClient(self.raw(lambda r:httpx.Response(401,json={'error':{'message':'synthetic'}})),self.cfg,self.ledger,'T01')
        try:
            with self.assertRaises(Exception):await client.create(**self.request())
        finally:await client.close()
        self.ledger.finish('T01')
        with self.assertRaises(BudgetStop):self.ledger.start('T02')
    async def test_new_fixtures_preflight_and_initial_bugs(self):
        for case in ('T01','T02'):
            root=self.root/case;before=create(case,root);r=await require_environment(case,root)
            self.assertTrue(r['initial_bug_confirmed']);self.assertTrue(r['native_previews']);self.assertEqual(before,fingerprint(root))
    async def test_metadata_rejects_without_policy_changes(self):
        root=self.root/'T01';create('T01',root)
        import os
        with patch('mybot.tools.patch.os.getegid',return_value=os.getegid()+10000):r=await check_environment('T01',root)
        self.assertEqual(r['status'],'BLOCKED');self.assertIn('unsupported_ownership',r['issues'])
    async def test_independent_oracles_require_real_entry(self):
        from scripts.uat_v2.synthetic import FIXES
        root=self.root/'T02';create('T02',root)
        helper='src/parcel_totals/calculations.py';(root/helper).write_text(FIXES['T02'][helper])
        self.assertFalse((await assess('T02',root))['passed'])
        for name,text in FIXES['T02'].items():(root/name).write_text(text)
        self.assertTrue((await assess('T02',root))['passed']);self.assertTrue((await assess('T02',root,hidden=False))['passed'])
    async def test_five_turn_semantic_calibration(self):
        root=self.root/'T03';create('T03',root);r=await calibrate(root)
        self.assertTrue(r['passed']);self.assertEqual(r['per_turn_status'],['not_needed']*4+['semantic_applied'])
        self.assertEqual(r['summary_requests_synthetic'],1);self.assertTrue(r['files_unchanged']);self.assertTrue(r['no_summary_persisted'])
    async def test_hidden_and_reference_not_in_workspaces(self):
        for case in LIMITS:
            root=self.root/case;create(case,root)
            names=fingerprint(root)
            self.assertFalse(any('oracle' in n or 'synthetic' in n or 'reference' in n for n in names))
    async def test_freeze_binds_sources_config_fixtures_and_ledger(self):
        from scripts.uat_v2 import prepare as module
        import subprocess
        repo=self.root/'source';(repo/'mybot').mkdir(parents=True);sentinel=repo/'mybot/sentinel.py';sentinel.write_text('# frozen source\n')
        subprocess.run(['git','init','-q',str(repo)],check=True)
        subprocess.run(['git','-C',str(repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Offline Test','-c','user.email=offline@example.invalid','commit','-qm','source'],check=True)
        config=self.root/'private-config.json';config.write_text(json.dumps({'llm':{'provider':'coco','providers':{
            'coco':dict(PROVIDER),'coco2':{**PROVIDER,'model':'glm-5.3-flash'}}}}))
        batch=self.root/'new-batch'
        with patch.object(module,'REPO',repo):
            prepared=await module.prepare(batch,config);self.assertTrue(prepared['calibration']['passed'])
            self.assertNotIn('api_key',str(prepared['provider']))
            module.freeze(batch,config);module.verify_frozen(batch,config)
            with self.assertRaises(BudgetStop):module.freeze(batch,config)
            sentinel.write_text('# tampered\n')
            with self.assertRaises(BudgetStop):module.verify_frozen(batch,config)
            sentinel.write_text('# frozen source\n')
            path=batch/'workspaces/T01/src/tag_shelf.py';saved=path.read_text();path.write_text(saved+'# change\n')
            with self.assertRaises(BudgetStop):module.verify_frozen(batch,config)
            path.write_text(saved)
            with self.assertRaises(FileExistsError):await module.prepare(batch,config)
            config.write_text(config.read_text()+' ')
            with self.assertRaises(BudgetStop):module.verify_frozen(batch,config)
    async def test_invalid_authorization_spelling_rejected(self):
        from scripts.uat_v2.server import require_authorization
        for value in ('GRANTED',True,None,'GRANTED_48_REQUESTS','not_granted'):
            with self.assertRaises(BudgetStop):require_authorization(value)
    async def test_rehearsal_label_cannot_look_live(self):
        root=self.root/'T01';create('T01',root);app=preview_app('T01',root,8882)
        try:self.assertEqual(app.runtime.config.model,'OFFLINE-SYNTHETIC-v2')
        finally:await app.runtime.close()
    async def test_full_web_adapter_uses_mocktransport_not_live(self):
        from scripts.uat_v2 import prepare as module
        from scripts.uat_v2.calibrate import cited_response
        from mybot.agent.context_compactor import PROMPT
        import subprocess
        repo=self.root/'mock-source';(repo/'mybot').mkdir(parents=True);(repo/'mybot/sentinel.py').write_text('# source\n')
        subprocess.run(['git','init','-q',str(repo)],check=True);subprocess.run(['git','-C',str(repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Offline','-c','user.email=offline@example.invalid','commit','-qm','source'],check=True)
        private_config=self.root/'mock-config.json';providers={'coco':dict(PROVIDER),'coco2':{**PROVIDER,'model':'glm-5.3-flash'}}
        private_config.write_text(json.dumps({'llm':{'provider':'coco','providers':providers}}))
        batch=self.root/'mock-batch';sends=[]
        def handler(request):
            body=json.loads(request.content);sends.append(body)
            if body['messages'][0]['content']==PROMPT:
                content=cited_response(body).choices[0].message.content
                return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':1,'model':'synthetic','choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}],'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}})
            return reply()
        def gateway_factory(cfg):
            return ProviderFailoverClient(self.raw(handler),cfg,replace(cfg,provider='coco2',model='glm-5.3-flash'),lambda _:self.raw(handler))
        with patch.object(module,'REPO',repo):
            await module.prepare(batch,private_config);module.freeze(batch,private_config)
            # This authorization value is a unit-test input, with SDK HTTP fully
            # intercepted; it is never authority for the real prepared batch.
            with patch('scripts.uat_v2.server.build_gateway_client',gateway_factory):
                app=make_app('T03',batch,private_config,authorization='GRANTED_34_REQUESTS',port=8882)
                async with app.app.router.lifespan_context(app.app):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8882') as http:
                        await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'Origin':'http://127.0.0.1:8882','X-Mybot-CSRF':boot['csrf']}
                        identifier=(await http.post('/api/conversations',json={},headers=headers)).json()['id']
                        for text in MESSAGES['T03']:
                            r=await http.post(f'/api/conversations/{identifier}/messages',json={'message':text},headers=headers)
                            self.assertEqual(r.status_code,202);await app.runtime.conversations[identifier].task;await asyncio.sleep(.11)
                        c=app.runtime.conversations[identifier]
                        self.assertEqual(c.resources['context']['context_compaction_status'],'semantic_applied')
                        self.assertEqual(len(c.session.export_turns()),5)
                rows=app.uat_ledger.rows();self.assertEqual(len(rows),6);self.assertEqual(sum(r['http_attempts'] for r in rows),6)
                self.assertEqual(sum(r['purpose']=='compaction' for r in rows),1);self.assertEqual(len(sends),6)
                self.assertTrue((batch/'private/T03-activity.jsonl').is_file());self.assertTrue((batch/'private/T03-final.json').is_file())
                self.assertTrue(app.runtime.closed)
                with self.assertRaises(BudgetStop):app.uat_ledger.start('T03')
    async def test_new_tasks_real_tools_synthetic_model_end_to_end(self):
        from scripts.uat_v2.fixtures import ALLOWED
        for case in ('T01','T02'):
            root=self.root/case;before=create(case,root);app=preview_app(case,root,8882)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8882') as http:
                    await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'Origin':'http://127.0.0.1:8882','X-Mybot-CSRF':boot['csrf']}
                    identifier=(await http.post('/api/conversations',json={},headers=headers)).json()['id']
                    await http.post(f'/api/conversations/{identifier}/messages',json={'message':'OFFLINE/SYNTHETIC rehearsal'},headers=headers)
                    c=app.runtime.conversations[identifier]
                    for _ in range(300):
                        pending=c.approval.public_pending() if c.approval else None
                        if pending or c.task.done():break
                        await asyncio.sleep(.01)
                    self.assertIsNotNone(pending,str((case,c.status,c.report,[(e.get('tool'),e.get('success'),e.get('metadata')) for e in c.events if e['type']=='tool_finished'])))
                    display=json.loads(pending['display']);self.assertEqual(display['cwd'],'.')
                    self.assertTrue(display['os_sandbox']);self.assertEqual(display['execution_mode'],'macos_readonly')
                    self.assertEqual(display['argv'][1:],['-m','unittest','discover','-s','tests','-v'])
                    approved=await http.post(f'/api/conversations/{identifier}/approval',json={'id':pending['id'],'allow':True},headers=headers)
                    self.assertEqual(approved.status_code,200);await c.task
                    self.assertEqual(c.report['state'],'verified');self.assertEqual(c.report['current_revision'],1)
                    self.assertGreater(c.report['tests_passed_after_last_patch'],0)
                    events=[e for e in c.events if e['type']=='tool_finished']
                    self.assertTrue(any(e['metadata'].get('receipt_created') for e in events))
                    self.assertTrue(any(e['metadata'].get('receipt_commit_success') for e in events))
                self.assertTrue((await assess(case,root))['passed'])
                after=fingerprint(root);changed={k for k in before.keys()|after.keys() if before.get(k)!=after.get(k)}
                self.assertEqual(changed,set(ALLOWED[case]))
            finally:await app.runtime.close()
    async def test_one_conversation_exact_frozen_message_no_retry(self):
        root=self.root/'T03';create('T03',root);app=preview_app('T03',root,8882);bind_task_contract(app,'T03')
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8882') as http:
                await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'Origin':'http://127.0.0.1:8882','X-Mybot-CSRF':boot['csrf']}
                identifier=(await http.post('/api/conversations',json={},headers=headers)).json()['id']
                self.assertEqual((await http.post('/api/conversations',json={},headers=headers)).status_code,409)
                self.assertEqual((await http.post(f'/api/conversations/{identifier}/clear',json={},headers=headers)).status_code,409)
                endpoint=f'/api/conversations/{identifier}/messages'
                self.assertEqual((await http.post(endpoint,json={'message':'changed'},headers=headers)).status_code,409)
                self.assertEqual((await http.post(endpoint,json={'message':MESSAGES['T03'][0]},headers=headers)).status_code,202)
                await app.runtime.conversations[identifier].task
                self.assertEqual((await http.post(endpoint,json={'message':MESSAGES['T03'][0]},headers=headers)).status_code,409)
        finally:await app.runtime.close()

if __name__=='__main__':unittest.main(verbosity=2)
