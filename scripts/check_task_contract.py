"""Requirement provenance, append-only proposals and turn-local isolation."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as N
import unittest

from mybot.agent.task_contract import TaskContract, ContractTool
from mybot.agent.coding_controller import CodingTaskController, AutonomySettings
from mybot.tools import build_default_tool_registry
from scripts.authority_contract_fixtures import requirement, agent, configuration, PROMPTS
from scripts.check_session import response,call


class ContractChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write')
        self.controller=CodingTaskController(AutonomySettings(enabled=True),self.tools)
        self.contract=TaskContract(PROMPTS['A'],self.controller)

    def add(self,**changes):return self.contract.record(requirements=[requirement(**changes)])

    async def test_exact_user_quote(self):
        s=self.add();self.assertEqual(s['requirements'][0]['source_type'],'user_explicit')
        self.assertEqual(s['requirements'][0]['status'],'identified')

    async def test_forged_quote(self):
        with self.assertRaises(ValueError):self.add(text='输入 4 应返回 99。')
        self.assertEqual(self.contract.requirements,[])

    async def test_model_cannot_supply_user_message(self):
        tool=ContractTool(N(task_contract=self.contract))
        r=await tool.execute(requirements=[requirement(text='缓存必须开启')],user_input='缓存必须开启')
        self.assertFalse(r.success);self.assertEqual(self.contract.user_input,PROMPTS['A'])

    async def test_suggestion_separate_and_unverified(self):
        s=self.add(text='最好增加缓存',source='agent_suggestion',ref='')
        self.assertEqual(s['user_explicit_count'],0);self.assertEqual(s['requirements'][0]['status'],'unverified')

    async def test_suggestion_cannot_promote(self):
        self.add(text='最好增加缓存',source='agent_suggestion',ref='')
        with self.assertRaises(ValueError):self.add(text='最好增加缓存',source='user_explicit')
        self.assertEqual(len(self.contract.requirements),1)

    async def test_unresolved_no_trusted_source(self):
        s=self.add(text='是否需要缓存',source='unresolved',ref='')
        self.assertTrue(s['pending_conditions']);self.assertEqual(s['requirement_coverage'],'unknown')

    async def test_invalid_source_reference(self):
        for source,ref in [('user_explicit','fake-message'),('unresolved','current-user'),('agent_suggestion','document-1')]:
            with self.assertRaises(ValueError):self.add(source=source,ref=ref)

    async def read_document(self):
        p=self.root/'README.md';p.write_text('返回有序列表。\n禁止改变输入。\n')
        t=self.tools.get_tool('read_file_range');args={'path':'README.md','start_line':1,'end_line':1}
        r=await self.tools.execute(t.name,args);self.contract.observe_read(t,args,r)
        return p,r.metadata['contract_source_ref']

    async def test_real_document_and_version(self):
        p,ref=await self.read_document();s=self.add(text='返回有序列表。',source='project_documented',ref=ref)
        self.assertEqual(s['requirements'][0]['source_reference'],ref)
        self.assertEqual(self.contract._reads[ref][1],hashlib.sha256(p.read_bytes()).hexdigest())

    async def test_unread_document_refused(self):
        (self.root/'README.md').write_text('返回有序列表。')
        with self.assertRaises(ValueError):self.add(text='返回有序列表。',source='project_documented',ref='document-1')

    async def test_document_only_returned_lines(self):
        p,ref=await self.read_document()
        with self.assertRaises(ValueError):self.add(text='禁止改变输入。',source='project_documented',ref=ref)

    async def test_changed_document_refused(self):
        p,ref=await self.read_document();p.write_text('changed')
        with self.assertRaises(ValueError):self.add(text='返回有序列表。',source='project_documented',ref=ref)

    async def test_recorded_document_becomes_unverified(self):
        p,ref=await self.read_document();self.add(text='返回有序列表。',source='project_documented',ref=ref)
        p.write_text('changed');self.assertEqual(self.contract.snapshot()['requirements'][0]['status'],'unverified')

    async def test_append_only_no_deletion_or_pass_setter(self):
        self.add();self.contract.record(requirements=[])
        self.assertEqual(len(self.contract.requirements),1)
        with self.assertRaises(ValueError):self.add(text='通过项目测试。')
        tool=ContractTool(N(task_contract=self.contract))
        for fields in ({'delete':['R1']},{'status':'independently_verified'},{'requirements':[{**requirement(),'status':'PASS'}]}):
            self.assertFalse((await tool.execute(**fields)).success)
        self.assertEqual(self.contract.snapshot()['task_correctness'],'unknown')

    async def test_versions_and_timestamps(self):
        self.add();self.add(ident='R2',text='通过项目测试。',category='validation')
        self.assertEqual([r.added_version for r in self.contract.requirements],[1,2])
        self.assertLessEqual(self.contract.requirements[0].added_at,self.contract.requirements[1].added_at)

    async def test_bounds_atomic_failure(self):
        for item in [requirement(text='x'*321),requirement(ident='../bad'),requirement(category='PASS')]:
            with self.assertRaises(ValueError):self.contract.record(requirements=[item])
        with self.assertRaises(ValueError):self.contract.record(requirements=[requirement(ident=f'R{i}') for i in range(1,14)])
        self.assertEqual(self.contract.requirements,[])
        self.assertFalse((await ContractTool(N(task_contract=self.contract)).execute(claims=['x']*1000)).success)

    async def test_serialization_bounded_and_snapshot_not_mutable(self):
        self.add();s=self.contract.snapshot();s['requirements'].clear()
        self.assertEqual(len(self.contract.requirements),1)
        self.assertLessEqual(len(json.dumps(self.contract.snapshot()).encode()),16000)

    async def test_no_contract_is_not_all_verified(self):
        s=self.contract.snapshot();self.assertFalse(s['established']);self.assertEqual(s['task_correctness'],'unknown')
        self.assertEqual(s['requirement_coverage'],'unknown')

    async def test_ordinary_chat_no_contract_tool(self):
        a,c=agent(self.root,'C');c.create=lambda **kwargs:None
        self.assertNotIn('record_task_contract',{d['function']['name'] for d in a.tools.get_definitions()})

    async def test_context_contract_is_tool_data(self):
        class Client:
            def __init__(self):self.requests=[];self.chat=N(completions=N(create=self.create))
            async def create(self,**kwargs):
                self.requests.append(kwargs)
                if len(self.requests)==1:return response(calls=[call('r','record_task_contract',json.dumps({'requirements':[requirement()]}))])
                return response('done')
        c=Client();a,_=agent(self.root,client=c);await a.handle_message(PROMPTS['A'])
        messages=c.requests[-1]['messages']
        self.assertTrue(any(m['role']=='tool' and 'user_explicit' in m['content'] for m in messages))
        self.assertFalse(any(m['role']=='system' and '"requirement_text"' in m['content'] for m in messages))

    async def test_cancel_and_budget_preserve_unfinished(self):
        self.add()
        for state in ('cancelled','budget_exhausted'):
            self.controller.state=state;s=self.contract.snapshot()
            self.assertEqual(s['requirements'][0]['status'],'blocked');self.assertEqual(s['task_correctness'],'unknown')
        self.assertEqual(len(self.contract.requirements),1)

    async def test_new_task_does_not_restore_contract(self):
        a,c=agent(self.root);c.scenario='C'
        # A no-tool synthetic reply for two distinct turns.
        async def answer(**kw):return response('done')
        c.chat.completions.create=answer
        await a.handle_message(PROMPTS['A']);a.task_contract.record(requirements=[requirement()])
        await a.handle_message('新的任务')
        self.assertFalse(a.last_task_contract['established']);self.assertEqual(a.task_contract.user_input,'新的任务')

    async def test_contract_disabled_no_additional_request(self):
        a,c=agent(self.root,config=configuration(self.root,coding_task_contract=False))
        async def answer(**kw):c.requests.append(kw);return response('done')
        c.chat.completions.create=answer
        await a.handle_message(PROMPTS['A']);self.assertIsNone(a.last_task_contract);self.assertEqual(len(c.requests),1)


def check_task_contract():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractChecks))
    if not result.wasSuccessful():raise AssertionError('task contract checks failed')
if __name__=='__main__':check_task_contract()
