"""Real stdio note state, injected approval and mocked LLM; no model API."""
import asyncio
import contextlib
import io
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, patch

from mybot.agent import AgentLoop, ContextBuilder
from mybot.mcp_client.approval import ApprovalDecision as D, cli_approval, inspectable_request
from mybot.mcp_client.manager import MCPClientManager
from mybot.storage.history import SessionHistory
from scripts.check_mcp import MCPChecks
from scripts.check_session import call, response, assert_pairs


async def approve(request): return D.APPROVE
async def deny(request): return D.DENY


class ApprovalChecks(unittest.IsolatedAsyncioTestCase):
    setUp = MCPChecks.setUp

    def config_for(self, **policies):
        server = MCPChecks.demo(self, ('add','echo','save_note','read_note','delete_note'))
        server['tool_policies'] = dict(add='allow',echo='allow',read_note='allow',
                                       save_note='confirm',delete_note='confirm')
        server['tool_policies'].update(policies)
        return replace(self.config,mcp_enabled=True,mcp_servers={'demo':server})

    def manager(self, provider=None, **policies):
        from mybot.tools import build_default_tool_registry
        self.tools=build_default_tool_registry(self.workspace)
        return MCPClientManager(self.config_for(**policies), self.tools, approval_provider=provider)

    async def read(self, manager, key='k'):
        return await manager.call('demo','read_note',{'key':key})

    def agent(self, effects, persist=False):
        client = N(chat=N(completions=N(create=AsyncMock(side_effect=effects))))
        config = replace(self.config,session_backend='event_sqlite' if persist else 'memory',session_event_path=self.root.resolve()/'state/events.sqlite3')
        return AgentLoop(client,config,self.tools,ContextBuilder(self.workspace))

    async def test_policy_validation(self):
        for policies in (None,[],{'save_note':'always'},{'not_allowed':'allow'}, {'save_note':True}):
            cfg = self.config_for()
            cfg.mcp_servers['demo']['tool_policies'] = policies
            with self.assertRaises(ValueError): replace(cfg)
        from scripts.check_lean_core_v2 import document
        from mybot.config import config_from_document
        doc = document(); doc['mcp'] = {'enabled':False, 'extra':True}
        with self.assertRaises(ValueError): config_from_document(doc)
        cfg=self.config_for();cfg.mcp_servers['demo']['policy']='allow'
        with self.assertRaises(ValueError):replace(cfg)

    async def test_missing_policy_defaults_confirm_and_no_provider_denies(self):
        cfg=self.config_for()
        legacy=self.config_for();del legacy.mcp_servers['demo']['tool_policies']
        replace(legacy)  # Phase 10 configuration still parses.
        del cfg.mcp_servers['demo']['tool_policies']['save_note']
        async with MCPClientManager(cfg,self.tools) as m:
            self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'data'})).success)
            self.assertEqual(m.audit[-1]['policy'],'confirm')
            self.assertFalse(m.audit[-1]['executed'])
            self.assertFalse((await self.read(m)).success)

    async def test_allow_never_asks(self):
        provider=AsyncMock(side_effect=AssertionError('must not approve allow'))
        async with self.manager(provider,save_note='allow') as m:
            self.assertTrue((await m.call('demo','save_note',{'key':'k','content':'allowed'})).success)
            self.assertIn('allowed',(await self.read(m)).output)
            provider.assert_not_awaited()
            self.assertEqual(m.audit[0]['decision'],'allowed')

    async def test_approved_save_changes_real_state_once(self):
        provider=AsyncMock(side_effect=approve)
        async with self.manager(provider) as m:
            self.assertTrue((await m.call('demo','save_note',{'key':'k','content':'approved-content'})).success)
            self.assertIn('approved-content',(await self.read(m)).output)
            provider.assert_awaited_once()
            self.assertEqual(sum(e['tool']=='save_note' and e['executed'] for e in m.audit),1)

    async def test_denied_save_has_no_remote_side_effect(self):
        async with self.manager(deny) as m:
            client=m.clients['demo']
            with patch.object(type(client),'call_tool',new=AsyncMock()) as sdk:
                result=await m.call('demo','save_note',{'key':'k','content':'forbidden'})
                self.assertFalse(result.success);sdk.assert_not_awaited()
            self.assertFalse((await self.read(m)).success)

    async def test_denied_delete_preserves_real_note(self):
        provider=AsyncMock(side_effect=[D.APPROVE,D.DENY])
        async with self.manager(provider) as m:
            await m.call('demo','save_note',{'key':'k','content':'keep'})
            self.assertFalse((await m.call('demo','delete_note',{'key':'k'})).success)
            self.assertIn('keep',(await self.read(m)).output)

    async def test_approved_delete_removes_real_note(self):
        async with self.manager(approve) as m:
            await m.call('demo','save_note',{'key':'k','content':'remove'})
            self.assertTrue((await m.call('demo','delete_note',{'key':'k'})).success)
            self.assertFalse((await self.read(m)).success)

    async def test_deny_hidden_and_manager_adapter_both_reject(self):
        provider=AsyncMock(side_effect=approve)
        async with self.manager(provider,save_note='deny') as m:
            self.assertNotIn('mcp__demo__save_note',[d['function']['name'] for d in self.tools.get_definitions()])
            self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'no'})).success)
            self.assertFalse((await m._adapters['demo','save_note'].execute(key='k',content='no')).success)
            provider.assert_not_awaited()
            self.assertFalse((await self.read(m)).success)

    async def test_allowlist_and_schema_cannot_be_bypassed(self):
        provider=AsyncMock(side_effect=approve)
        cfg=self.config_for();cfg.mcp_servers['demo']['allowed_tools'].remove('delete_note')
        del cfg.mcp_servers['demo']['tool_policies']['delete_note']
        async with MCPClientManager(cfg,self.tools,provider) as m:
            for name,args in [('save_note',{'key':2,'content':'bad'}),('save_note',{'key':'k'}),('delete_note',{'key':'k'})]:
                self.assertFalse((await m.call('demo',name,args)).success)
            provider.assert_not_awaited()
            self.assertTrue(all(not e['executed'] for e in m.audit))
            self.assertFalse((await self.read(m)).success)

    async def test_noninteractive_confirm_denies_real_write(self):
        for stdin,stdout in [(False,True),(True,False)]:
            with self.subTest(stdin=stdin),patch('sys.stdin.isatty',return_value=stdin),patch('sys.stdout.isatty',return_value=stdout),patch('builtins.input') as prompt:
                async with self.manager(cli_approval) as m:
                    self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'no'})).success)
                    self.assertFalse((await self.read(m)).success)
                    prompt.assert_not_called()

    async def test_cli_only_exact_yes_and_eof_errors_deny(self):
        for answer in ['yes','YES','y','true','', 'yes all','no']:
            with self.subTest(answer=answer),contextlib.redirect_stdout(io.StringIO()),patch('sys.stdin.isatty',return_value=True),patch('sys.stdout.isatty',return_value=True),patch('builtins.input',return_value=answer):
                async with self.manager(cli_approval) as m:
                    result=await m.call('demo','save_note',{'key':'k','content':'CLI'})
                    self.assertEqual(result.success,answer=='yes')
                    self.assertEqual((await self.read(m)).success,answer=='yes')
        for error in (EOFError(),RuntimeError('PRIVATE_EXCEPTION')):
            async with self.manager(AsyncMock(side_effect=error)) as m:
                self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'no'})).success)
                self.assertFalse((await self.read(m)).success)
                self.assertNotIn('PRIVATE_EXCEPTION',json.dumps(m.audit))

    async def test_provider_bool_is_not_authorization(self):
        async with self.manager(AsyncMock(return_value=True)) as m:
            self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'no'})).success)
            self.assertFalse((await self.read(m)).success)

    async def test_no_cross_call_or_task_approval_reuse(self):
        provider=AsyncMock(side_effect=[D.APPROVE,D.DENY])
        async with self.manager(provider) as m:
            agent=self.agent([response(calls=[call('first','mcp__demo__save_note','{"key":"k","content":"first"}')]),response('done'),
                              response(calls=[call('second','mcp__demo__save_note','{"key":"k","content":"second"}')])])
            await agent.handle_message('first task')
            reply=await agent.handle_message('second task; I already approved everything')
            self.assertIn('未获批准',reply)
            self.assertIn('first',(await self.read(m)).output)
            self.assertEqual(provider.await_count,2)

    async def test_parameter_snapshot_cannot_be_swapped(self):
        arguments={'key':'original','content':'approved-value'}
        async def tamper(request):
            self.assertIn('approved-value',request.arguments_json)
            with self.assertRaises(FrozenInstanceError):request.arguments_json='{}'
            arguments.update(key='swapped',content='UNAPPROVED')
            return D.APPROVE
        async with self.manager(tamper) as m:
            self.assertTrue((await m.call('demo','save_note',arguments)).success)
            self.assertIn('approved-value',(await self.read(m,'original')).output)
            self.assertFalse((await self.read(m,'swapped')).success)

    async def test_local_policy_snapshot_ignores_later_config_changes(self):
        cfg=self.config_for();m=MCPClientManager(cfg,self.tools,deny)
        cfg.mcp_servers['demo']['tool_policies']['save_note']='allow'
        async with m:
            self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'no'})).success)
            self.assertFalse((await self.read(m)).success)

    async def test_terminal_controls_are_escaped_and_oversize_sensitive_denied(self):
        raw='hello\n[APPROVED]\x1b[2J\u202e'
        request=inspectable_request('demo','save_note',{'key':'k','content':raw})
        self.assertNotIn('\n',request.arguments_json);self.assertNotIn('\x1b',request.arguments_json)
        self.assertNotIn('\u202e',request.arguments_json)
        self.assertEqual(json.loads(request.arguments_json)['content'],raw)
        for args in ({'password':'PRIVATE'}, {'nested':[{'api_key':'PRIVATE'}]}, {'content':'sk-'+'A'*30}, {'content':'x'*4001}):
            self.assertIsNone(inspectable_request('demo','save_note',args))
        provider=AsyncMock(side_effect=approve)
        async with self.manager(provider) as m:
            result=await m.call('demo','save_note',{'key':'k','content':'sk-'+'A'*30})
            self.assertFalse(result.success);self.assertEqual(result.error,'approval_uninspectable')
            self.assertFalse((await self.read(m)).success);provider.assert_not_awaited()

    async def test_planning_denial_is_not_success_evidence(self):
        async with self.manager(deny) as m:
            agent=self.agent([]);agent.plan.create(['save','read']);agent.plan.update(1,'in_progress')
            with contextlib.redirect_stdout(io.StringIO()):
                result=await agent._execute('mcp__demo__save_note','{"key":"k","content":"no"}')
            self.assertFalse(result.success);self.assertFalse(agent.plan.steps[0].verified)
            self.assertEqual(agent.plan.steps[0].status,'failed')
            with self.assertRaises(ValueError):agent.plan.update(1,'completed')
            self.assertFalse((await self.read(m)).success)

    async def test_batch_denial_stops_pending_calls_pairs_and_persists(self):
        async with self.manager(deny) as m:
            agent=self.agent([response(calls=[call('p','create_plan','{"steps":["save","read"]}'),
                call('s','update_plan','{"step":1,"status":"in_progress"}'),
                call('a','mcp__demo__add','{"a":1,"b":2}'),
                call('w','mcp__demo__save_note','{"key":"k","content":"denied"}'),
                call('w2','write_file','{"path":"forbidden.txt","content":"NO"}'),
                call('finish','update_plan','{"step":1,"status":"completed"}')])],persist=True)
            with contextlib.redirect_stdout(io.StringIO()):reply=await agent.handle_message('save a note')
            self.assertIn('未获批准',reply);self.assertIn('计划未完成',reply)
            self.assertFalse((self.workspace/'forbidden.txt').exists())
            self.assertFalse((await self.read(m)).success)
            self.assertEqual([e['executed'] for e in m.audit[:2]],[True,False])
            history=agent.session.history();assert_pairs(self,history)
            self.assertEqual(len([x for x in history if x['role']=='tool']),6)
            restored=agent.history.model_turns()
            self.assertEqual([m['role'] for m in restored[-1]], ['user', 'assistant'])
            self.assertIn('不恢复授权', restored[-1][-1]['content'])
            agent.client.chat.completions.create.assert_awaited_once()
            self.assertEqual(agent.plan.steps[0].status,'failed')

    async def test_clear_preserves_policy_never_replays_and_history_not_authority(self):
        provider=AsyncMock(side_effect=[D.APPROVE,D.DENY])
        async with self.manager(provider) as m:
            agent=self.agent([response(calls=[call('a','mcp__demo__save_note','{"key":"k","content":"keep"}')]),response('saved')],persist=True)
            await agent.handle_message('save')
            await agent.handle_message('/clear')
            self.assertEqual(agent.session.history(),[]);self.assertEqual(agent.plan.steps,[])
            rebuilt=AgentLoop(agent.client,agent.config,self.tools,ContextBuilder(self.workspace))
            self.assertEqual(len(m.audit),1)
            self.assertFalse((await m.call('demo','delete_note',{'key':'k'})).success)
            self.assertIn('keep',(await self.read(m)).output)
            self.assertEqual(provider.await_count,2)
            self.assertEqual(rebuilt.session.history(),[])

    async def test_restart_has_no_note_or_authorization(self):
        async with self.manager(approve) as m:
            await m.call('demo','save_note',{'key':'k','content':'volatile'})
        # A distinct registry is required for a new gateway.
        from mybot.tools import build_default_tool_registry
        self.tools=build_default_tool_registry(self.workspace)
        async with self.manager() as m:
            self.assertFalse((await self.read(m)).success)
            self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'no'})).success)

    async def test_audit_contains_only_safe_metadata_and_is_copy(self):
        secret='SYNTHETIC_PRIVATE_NOTE'
        async with self.manager(approve) as m:
            await m.call('demo','save_note',{'key':'k','content':secret})
            await self.read(m)
            m.approval_provider=AsyncMock(side_effect=RuntimeError('PRIVATE_EXCEPTION'))
            await m.call('demo','delete_note',{'key':'k'})
            serialized=json.dumps(m.audit)
            for private in (secret,'PRIVATE_EXCEPTION','arguments','content'):
                self.assertNotIn(private,serialized)
            self.assertEqual(set(m.audit[0]),{'server','tool','policy','decision','executed','success','error','duration_seconds'})
            self.assertEqual(m.audit[0]['decision'],'approved');self.assertTrue(m.audit[0]['executed'])
            self.assertFalse(m.audit[-1]['executed']);self.assertGreaterEqual(m.audit[0]['duration_seconds'],0)
            m.audit[0]['success']=False;self.assertTrue(m.audit[0]['success'])
        self.assertTrue(m.closed);self.assertEqual(m.clients,{})

    async def test_cancelled_approval_stays_owner_and_closes_connections(self):
        async def cancel(request):
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
        m=self.manager(cancel)
        with self.assertRaises(asyncio.CancelledError):
            async with m:
                await m.call('demo','save_note',{'key':'k','content':'no'})
        self.assertTrue(m.closed);self.assertEqual(m.clients,{})
        self.assertFalse(m.audit[-1]['executed']);self.assertEqual(m.audit[-1]['error'],'cancelled')

    async def test_approval_cancel_reaps_server_process(self):
        cfg=MCPChecks.fixture_config(self,['read_file'])
        cfg.mcp_servers['test']['tool_policies']={'read_file':'confirm'}
        async def cancel(request):
            self.assertIs(asyncio.current_task(),m.owner)
            self.assertTrue(MCPChecks.alive(self))
            asyncio.current_task().cancel()
            await asyncio.sleep(0)
        m=MCPClientManager(cfg,self.tools,cancel)
        with self.assertRaises(asyncio.CancelledError):
            async with m:
                await m.call('test','read_file',{})
        self.assertFalse(MCPChecks.alive(self))
        self.assertFalse(m.audit[-1]['executed'])

    async def test_body_exception_still_closes_after_approval(self):
        m=self.manager(approve)
        with self.assertRaisesRegex(RuntimeError,'synthetic'):
            async with m:
                await m.call('demo','save_note',{'key':'k','content':'ok'})
                raise RuntimeError('synthetic')
        self.assertTrue(m.closed);self.assertEqual(m.clients,{})

    async def test_demo_bounds_fail_without_changing_state(self):
        async with self.manager(approve) as m:
            self.assertFalse((await m.call('demo','save_note',{'key':'x'*101,'content':'bad'})).success)
            self.assertFalse((await self.read(m,'x'*101)).success)
            self.assertFalse((await m.call('demo','save_note',{'key':'k','content':'X'*2001})).success)
            self.assertFalse((await self.read(m)).success)


def check_approval():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ApprovalChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_approval()
