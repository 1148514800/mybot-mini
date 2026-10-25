"""Real process death at durable boundaries, native Patch and command execution."""
import asyncio
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from mybot.storage.history import open_store,SessionHistory,recover
from mybot.storage.event_schema import StoreError
from scripts.eventstore_fixtures import configuration,SyntheticClient
from mybot.web.runtime import ChatRuntime


class RecoveryChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.config=configuration(self.root)
    def crash(self,stage):
        child=subprocess.run([sys.executable,'-m','scripts.eventstore_crash_fixture',str(self.root),stage],capture_output=True,timeout=15)
        self.assertEqual(child.returncode,17,child.stderr.decode())
        self.store=open_store(self.config,'web');self.addCleanup(self.store.close)
        self.sid=(self.root/'session-id').read_text();self.history=SessionHistory(self.store,self.sid)
        return self.history
    async def check_stage(self,stage,status,changed=False):
        h=self.crash(stage);recover(self.store);self.assertEqual(h.status()['status'],status)
        self.assertEqual((self.config.workspace/'new.py').exists(),changed)
        events=self.store.events(h.sid)
        text=str(events)
        self.assertNotIn('preview_receipt',text);self.assertNotIn('commit_arguments',text)
        self.assertNotIn('verified',text);self.assertEqual(h.model_turns(),[])
        before=len(events);recover(self.store);self.assertEqual(len(self.store.events(h.sid)),before)
        return h
    async def test_before_task_started(self):await self.check_stage('created','idle')
    async def test_user_committed_without_turn_start(self):await self.check_stage('user_only','interrupted')
    async def test_model_waiting_process_dies(self):await self.check_stage('model','interrupted')
    async def test_read_dispatch_without_return(self):await self.check_stage('read_pending','interrupted')
    async def test_external_effect_dispatch_unknown(self):await self.check_stage('effect_pending','execution_uncertain')
    async def test_preview_completed_not_replayed(self):await self.check_stage('preview','interrupted')
    async def test_commit_completed_before_process_death(self):await self.check_stage('commit','execution_uncertain',True)
    async def test_filesystem_publish_before_event_finish(self):await self.check_stage('commit_gap','execution_uncertain',True)
    async def test_command_running_process_dies(self):
        try:
            await self.check_stage('command','execution_uncertain',True)
        finally:
            marker=self.root/'child-pid'
            if marker.exists():
                try:os.kill(int(marker.read_text()),signal.SIGTERM)
                except ProcessLookupError:pass
    async def test_real_test_passed_but_reply_not_committed(self):await self.check_stage('test_finished','execution_uncertain',True)
    async def test_no_requests_or_authorizations_on_runtime_restore(self):
        h=await self.check_stage('commit','execution_uncertain',True);clients=[]
        def factory(c):clients.append(SyntheticClient());return clients[-1]
        runtime=ChatRuntime(self.config,client_factory=factory);self.addAsyncCleanup(runtime.close)
        c=runtime.conversations[h.sid]
        self.assertIsNone(c.approval);self.assertIsNone(c.report);self.assertIsNone(c.contract)
        self.assertFalse(await runtime.start(c,'continue'));self.assertEqual(clients,[])
        other=runtime.new();self.assertFalse(await runtime.start(other,'new task'))
    async def test_review_requires_host_confirmation_and_keeps_interruption(self):
        h=await self.check_stage('commit','execution_uncertain',True)
        with self.assertRaises(StoreError):h.review()
        with self.assertRaises(StoreError):self.store.delete(h.sid)
        h.review(confirmed=True);self.assertEqual(h.status()['status'],'interrupted');self.assertFalse(self.store.workspace_uncertain())
        self.assertFalse(h.status()['execution_evidence_restored'])
    async def test_live_other_owner_is_not_marked_crashed(self):
        self.store=open_store(self.config,'web');self.addCleanup(self.store.close);h=SessionHistory(self.store);h.start('live')
        self.assertEqual(recover(self.store),[]);self.assertEqual(h.status()['status'],'running')
    async def test_complete_turn_round_trip_only_chat_projection(self):
        self.store=open_store(self.config,'web');h=SessionHistory(self.store);h.start('hello');h.finish('a historical verified claim')
        sid=h.sid;self.store.close();self.store=open_store(self.config,'web');self.addCleanup(self.store.close);recover(self.store)
        h=SessionHistory(self.store,sid);turn=h.model_turns()[0]
        self.assertEqual([m['role'] for m in turn],['user','assistant']);self.assertIn('不是当前执行证据',turn[1]['content'])
        self.assertEqual(h.status()['status'],'completed')
    async def test_cross_channel_unknown_effect_blocks_without_history_sharing(self):
        self.store=open_store(self.config,'cli');self.addCleanup(self.store.close);h=SessionHistory(self.store);h.start('CLI private text')
        h.begin('external',{},None,'external_side_effect')
        web=open_store(self.config,'web');self.addCleanup(web.close)
        self.assertEqual(web.sessions(),[]);self.assertTrue(web.workspace_uncertain())
        with self.assertRaises(StoreError):SessionHistory(web).start('web request')

    async def test_observer_never_saves_mcp_sensitive_arguments_or_output(self):
        from mybot.tools.base import ToolResult
        self.store=open_store(self.config,'web');self.addCleanup(self.store.close)
        h=SessionHistory(self.store);h.start('safe user request')
        token=h.begin('mcp_remote',{'token':'MCP_ARG_SENTINEL_9361','path':'/Users/private/secret'},None,'external_side_effect')
        h.complete(token,ToolResult(True,output='MCP_RESULT_SENTINEL_9361',metadata={'nonce':'a'*64,'preview_receipt':'b'*64}))
        h.finish('safe reply')
        raw=self.config.session_event_path.read_bytes()
        for value in (b'MCP_ARG_SENTINEL_9361',b'MCP_RESULT_SENTINEL_9361',b'/Users/private/secret',b'a'*64,b'b'*64):
            self.assertNotIn(value,raw)
    async def test_event_append_failure_prevents_dispatch_and_file_effect(self):
        from unittest.mock import patch
        from mybot.tools.base import Tool,ToolResult
        from mybot.tools.registry import ToolRegistry
        target=self.config.workspace/'must-not-exist.txt'
        class Mutator(Tool):
            name='synthetic_mutation';description='fixture';parameters={}
            async def execute(self,**params):target.write_text('changed');return ToolResult(True)
        self.store=open_store(self.config,'web');self.addCleanup(self.store.close)
        h=SessionHistory(self.store);h.start('test fail closed')
        registry=ToolRegistry(mutation_enabled=True);registry.register(Mutator(),capability='workspace_mutation');registry.execution_observer=h
        with patch.object(self.store,'append_many',side_effect=StoreError('synthetic disk failure')):
            with self.assertRaises(StoreError):await registry.execute('synthetic_mutation',{})
        self.assertFalse(target.exists());h.interrupt()

    async def test_cli_terminal_projection_preserves_controller_safety_precedence(self):
        from mybot.agent import AgentLoop,ContextBuilder
        from mybot.tools import build_default_tool_registry
        self.store=open_store(self.config,'cli');self.addCleanup(self.store.close)
        for state,outcome,expected in [('blocked','blocked','failed'),('budget_exhausted','budget_exhausted','stopped'),('execution_uncertain','output_truncated','execution_uncertain')]:
            h=SessionHistory(self.store)
            agent=AgentLoop(SyntheticClient(),self.config,build_default_tool_registry(self.config.workspace),ContextBuilder(self.config.workspace),history=h)
            async def terminal(text):
                agent.last_coding_report={'state':state};agent.last_runtime_report={'outcome':outcome}
                return 'synthetic terminal reply'
            agent._run_message=terminal
            await agent.handle_message('terminal status fixture')
            self.assertEqual(h.status()['status'],expected)


def check_session_recovery():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryChecks))
    if not result.wasSuccessful():raise AssertionError('recovery checks failed')
if __name__=='__main__':check_session_recovery()
