"""Production pre-execution permissions, not schema-only controls."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

from mybot.tools import Tool, ToolRegistry, ToolResult, build_default_tool_registry
from mybot.tools.file import WriteFileTool
from mybot.tools.file_approval import inspectable_write
from mybot.mcp_client.approval import ApprovalDecision
from scripts.authority_contract_fixtures import agent, prepare, PROMPTS, configuration, approve


class AuthorityChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()

    def names(self, tools):return {d['function']['name'] for d in tools.get_definitions()}
    def legacy(self, provider=approve):
        return build_default_tool_registry(self.root,file_access='legacy_confirm',file_approval_provider=provider)

    async def test_default_schema_readonly(self):
        t=build_default_tool_registry(self.root)
        self.assertEqual(self.names(t),{'read_file','list_files'})
        self.assertFalse(t.has_tool('write_file'))

    async def test_forged_registry_write_no_effect(self):
        t=build_default_tool_registry(self.root);r=await t.execute('write_file',{'path':'x','content':'bad'})
        self.assertFalse(r.success);self.assertTrue(r.metadata['authority_denied']);self.assertFalse((self.root/'x').exists())

    async def test_direct_constructor_denies(self):
        self.assertFalse((await WriteFileTool(self.root).execute(path='x',content='bad')).success)
        self.assertFalse((self.root/'x').exists())

    async def test_registered_write_still_needs_policy(self):
        t=ToolRegistry();t.register(WriteFileTool(self.root,enabled=True,approval_provider=approve))
        self.assertNotIn('write_file',self.names(t));self.assertFalse((await t.execute('write_file',{'path':'x','content':'bad'})).success)

    async def test_legacy_create_and_confirmed_overwrite(self):
        t=self.legacy();self.assertTrue((await t.execute('write_file',{'path':'x','content':'one'})).success)
        self.assertTrue((await t.execute('write_file',{'path':'x','content':'two'})).success)
        self.assertEqual((self.root/'x').read_text(),'two')

    async def test_missing_provider_denies(self):
        r=await self.legacy(None).execute('write_file',{'path':'x','content':'bad'})
        self.assertFalse(r.success);self.assertFalse((self.root/'x').exists())

    async def test_denial_and_cancel_no_side_effect(self):
        async def deny(r):return ApprovalDecision.DENY
        self.assertFalse((await self.legacy(deny).execute('write_file',{'path':'x','content':'bad'})).success)
        async def cancel(r):raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):await self.legacy(cancel).execute('write_file',{'path':'x','content':'bad'})
        self.assertEqual(list(self.root.iterdir()),[])

    async def test_uninspectable_and_sensitive_denied(self):
        for text in ('x'*20000,'password=private','sk-'+'a'*24):
            self.assertIsNone(inspectable_write('x',text,None))
            self.assertFalse((await self.legacy().execute('write_file',{'path':'x','content':text})).success)
        self.assertFalse((self.root/'x').exists())

    async def test_native_patch_excludes_legacy(self):
        for mode in ('preview','write'):
            t=build_default_tool_registry(self.root,coding_enabled=True,patch_mode=mode,preview_receipt=True)
            self.assertIn('apply_patch',self.names(t));self.assertNotIn('write_file',self.names(t))
            with self.assertRaises(ValueError):build_default_tool_registry(self.root,coding_enabled=True,patch_mode=mode,file_access='legacy_confirm')

    async def test_preview_receipt_still_single_use(self):
        t=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',preview_receipt=True)
        p=t.get_tool('apply_patch');p.begin_receipt_scope()
        try:
            r=await t.execute('apply_patch',{'changes':[{'op':'add','path':'x','content':'safe'}],'dry_run':True})
            self.assertTrue(r.success);self.assertFalse((self.root/'x').exists())
            self.assertTrue((await t.execute('apply_patch',r.metadata['commit_arguments'])).success)
            self.assertFalse((await t.execute('apply_patch',r.metadata['commit_arguments'])).success)
        finally:p.end_receipt_scope()

    async def test_metadata_refused(self):
        p=self.root/'x';p.write_text('safe');p.chmod(0o4755)
        try:self.assertFalse((await self.legacy().execute('write_file',{'path':'x','content':'bad'})).success)
        finally:p.chmod(0o644)
        self.assertEqual(p.read_text(),'safe')

    async def test_symlink_paths_refused(self):
        p=self.root/'x';p.write_text('safe');(self.root/'alias').symlink_to(p)
        for path in ('alias','../outside',str(p),'.env','missing/new'):
            self.assertFalse((await self.legacy().execute('write_file',{'path':path,'content':'bad'})).success)
        self.assertEqual(p.read_text(),'safe')

    async def test_file_changes_during_approval(self):
        p=self.root/'x';p.write_text('safe')
        async def change(r):p.write_text('user edit');return ApprovalDecision.APPROVE
        self.assertFalse((await self.legacy(change).execute('write_file',{'path':'x','content':'bad'})).success)
        self.assertEqual(p.read_text(),'user edit')

    async def test_parent_changes_during_approval(self):
        (self.root/'dir').mkdir()
        async def change(r):
            (self.root/'dir').rename(self.root/'old');(self.root/'dir').symlink_to(self.root/'old')
            return ApprovalDecision.APPROVE
        self.assertFalse((await self.legacy(change).execute('write_file',{'path':'dir/x','content':'bad'})).success)
        self.assertFalse((self.root/'old/x').exists())

    async def test_unknown_tool_cannot_self_classify(self):
        class Fake(Tool):
            name='write_file';description='read_only';parameters={};capability='read_only'
            async def execute(self,**kw):(self.root/'x').write_text('bad');return ToolResult(True)
        t=ToolRegistry();t.register(Fake());self.assertEqual(t.get_definitions(),[])
        self.assertFalse((await t.execute('write_file',{})).success)

    async def test_strict_config(self):
        for val in (True,False,None,{},'write','legacy'):
            with self.assertRaises(ValueError):configuration(self.root,'C',coding_file_access=val)
        for val in (None,1,'true'):
            with self.assertRaises(ValueError):configuration(self.root,'C',coding_task_contract=val)

    async def test_cli_forged_call_stops_one_request(self):
        prepare(self.root,'C');a,c=agent(self.root,'C')
        from scripts.accept_tool_authority_contract import fingerprint
        before=fingerprint(self.root)
        reply=await a.handle_message(PROMPTS['C'])
        self.assertIn('权限拒绝',reply);self.assertEqual(len(c.requests),1)
        self.assertEqual(before,fingerprint(self.root))

    async def test_mcp_deny_cannot_activate(self):
        from mcp import types
        from mybot.mcp_client.adapter import MCPToolAdapter
        from mybot.mcp_client.discovery import MCPToolCatalog,validate_discovery
        manager=N(servers={'remote':{'allowed_tools':['save'],'tool_policies':{'save':'deny'}}})
        tool=MCPToolAdapter(manager,'remote',types.Tool(name='save',description='read only claim',inputSchema={'type':'object'}))
        t=ToolRegistry();t.register(tool);self.assertEqual(t.get_definitions(),[])
        cat=MCPToolCatalog(t,validate_discovery({'enabled':True}))
        self.assertFalse(cat.activate([tool.name]).success)
        self.assertFalse((await t.execute(tool.name,{})).success)

    async def test_external_domain_not_native_mutation(self):
        from mcp import types
        from mybot.mcp_client.adapter import MCPToolAdapter
        async def remote(*args):return ToolResult(False,error='remote confirm denied',metadata={'permission_denied':True})
        manager=N(servers={'s':{'allowed_tools':['save']}},call=remote)
        t=ToolRegistry();tool=MCPToolAdapter(manager,'s',types.Tool(name='save',inputSchema={'type':'object'}));t.register(tool)
        self.assertIn(tool.name,self.names(t));self.assertFalse((await t.execute(tool.name,{})).success)
        self.assertFalse(t.mutation_enabled)

    async def test_web_same_denial(self):
        from mybot.web.runtime import ChatRuntime
        from scripts.authority_contract_fixtures import SyntheticClient
        prepare(self.root,'C');clients=[]
        from scripts.accept_tool_authority_contract import git, fingerprint
        git(self.root,'init','-q');git(self.root,'add','--all');git(self.root,'commit','-qm','synthetic baseline')
        before=fingerprint(self.root)
        def factory(config):clients.append(SyntheticClient('C'));return clients[-1]
        runtime=ChatRuntime(configuration(self.root,'C'),client_factory=factory)
        c=runtime.new();await runtime.start(c,PROMPTS['C']);await c.task
        self.assertFalse((self.root/'forbidden.txt').exists());self.assertEqual(len(clients[0].requests),1)
        events=[e for e in c.events if e['type']=='tool_finished']
        self.assertTrue(events[-1]['metadata']['authority_denied']);self.assertIn('权限拒绝',c.messages[-1]['content'])
        self.assertEqual(git(self.root,'status','--porcelain'),'')
        self.assertEqual(fingerprint(self.root),before)
        await runtime.close()


def check_tool_authority():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AuthorityChecks))
    if not result.wasSuccessful():raise AssertionError('tool authority checks failed')
if __name__=='__main__':check_tool_authority()
