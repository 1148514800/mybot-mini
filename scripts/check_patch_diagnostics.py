"""OFFLINE/SYNTHETIC diagnostics through native tools and real Web HTTP/SSE."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from mybot.agent.loop import safe_read_metadata
from mybot.tools.file import ReadFileTool
from mybot.tools.base import ToolResult
from mybot.tools.patch import ApplyPatchTool, patch_diagnostics
from scripts import check_web_ui as web_checks

class DiagnosticChecks(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=web_checks.WebChecks.asyncSetUp
    post=web_checks.WebChecks.post
    new=web_checks.WebChecks.new
    run_chat=web_checks.WebChecks.run_chat
    coding_app=web_checks.WebChecks.coding_app
    async def test_web_ownership_diagnostic_no_secret(self):
        await self.coding_app()
        with patch('mybot.tools.patch.os.getegid',return_value=os.getegid()+10000):
            state=await self.run_chat('修复 OFFLINE/SYNTHETIC')
        events=state['events'];finished=[e for e in events if e['type']=='tool_finished' and e['tool']=='apply_patch']
        self.assertEqual(len(finished),1)
        meta=finished[0]['metadata']
        self.assertEqual(meta['safe_error_code'],'unsupported_ownership')
        self.assertEqual(meta['failure_phase'],'preflight');self.assertEqual(meta['operation_intent'],'preview')
        self.assertEqual(meta['guidance_code'],'check_workspace_metadata')
        self.assertNotIn(str(self.root),json.dumps(finished));self.assertNotIn('preview_receipt',json.dumps(finished))
        self.assertNotIn('return value',json.dumps(finished));self.assertNotEqual(state['report']['state'],'verified')
    async def test_argument_parsing_intent_unknown(self):
        from mybot.agent import AgentLoop,ContextBuilder
        from mybot.tools import build_default_tool_registry
        from scripts.check_web_ui import config
        from scripts.modernization_fixtures import Client
        cfg=config(self.root,True);agent=AgentLoop(Client(),cfg,build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',preview_receipt=True),ContextBuilder(self.root))
        result=await agent._execute('apply_patch','{"dry_run": false, "changes":[')
        self.assertEqual(result.metadata['operation_intent'],'unknown');self.assertEqual(result.metadata['failure_phase'],'argument_parsing')
        self.assertFalse(result.metadata['safe_to_retry']);self.assertFalse(result.metadata['applied'])
    async def test_write_failure_not_retryable(self):
        tool=ApplyPatchTool(self.root,patch_mode='write',preview_receipt=True)
        result=await tool.execute(dry_run=False,preview_receipt='0'*64)
        self.assertFalse(result.success);self.assertFalse(result.metadata['safe_to_retry'])
        self.assertEqual(result.metadata['operation_intent'],'write')
    async def test_successful_commit_has_no_failure_guidance(self):
        from scripts.check_tool_verification_reliability import changes
        tool=ApplyPatchTool(self.root,patch_mode='write',preview_receipt=True)
        tool.begin_receipt_scope()
        preview=await tool.execute(dry_run=True,changes=changes(self.root))
        self.assertTrue(preview.success)
        result=await tool.execute(dry_run=False,preview_receipt=preview.metadata['preview_receipt'])
        self.assertTrue(result.success);self.assertTrue(result.metadata['applied'])
        self.assertIsNone(result.metadata['guidance_code']);self.assertIsNone(result.metadata['safe_error_code'])
    async def test_unknown_exception_never_echoed(self):
        result=ToolResult(False,error='/private/host sk-secret receipt=abc',metadata={'failure_phase':'publication'})
        data=patch_diagnostics(result,False)
        self.assertEqual(data['safe_error_code'],'unknown');self.assertNotIn('/private',str(data));self.assertNotIn('sk-secret',str(data))
    async def test_read_path_and_ranges(self):
        from mybot.tools.read_file_range import ReadFileRangeTool
        tool=ReadFileRangeTool(self.root);args=dict(path='value.py',start_line=1,end_line=2)
        result=await tool.execute(**args);data=safe_read_metadata(tool,json.dumps(args),result)
        self.assertEqual(data['relative_path'],'value.py');self.assertEqual(data['requested_end_line'],2)
        self.assertEqual(data['returned_start_line'],1)
    async def test_unsafe_read_path_hidden(self):
        tool=ReadFileTool(self.root)
        for name in ('/etc/passwd','../secret','config/config.json','.env'):
            self.assertEqual(safe_read_metadata(tool,dict(path=name),ToolResult(True)),{})
    async def test_ui_contains_safe_guidance(self):
        text=(await self.http.get('/static/app.js')).text
        for key in ('safe_error_code','operation_intent','check_workspace_metadata','文件所有权或属组','relative_path'):self.assertIn(key,text)
    async def test_mcp_metadata_not_promoted(self):
        # Tool identity gate is native-only, even a remote name that resembles a reader.
        text=Path('mybot/agent/loop.py').read_text()
        self.assertIn('type(self.tools.get_tool(call.function.name)) in (ReadFileRangeTool, ReadFileTool)',text)
        self.assertNotIn('safe_meta.update(result.metadata)',text)

if __name__=='__main__':unittest.main(verbosity=2)
