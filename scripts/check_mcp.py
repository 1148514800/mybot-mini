"""Real SDK stdio processes + mocked LLM, no real model/API or private workspace."""
import asyncio
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch, AsyncMock

from mcp import types
from mybot.config import GatewayConfig, PROJECT_DIR
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.context_manager import ContextManager
from mybot.mcp_client.manager import MCPClientManager, MCPStartupError
from mybot.mcp_client.adapter import MCPToolAdapter, check_schema
from mybot.tools import build_default_tool_registry, ToolResult
from scripts.check_session import call, response, assert_pairs


FIXTURE = '''
import asyncio, os, sys
from pathlib import Path
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
Path(sys.argv[1]).write_text(str(os.getpid()))
mode = sys.argv[2]
empty = {"type":"object","properties":{},"additionalProperties":False}
schema = {"type":"object","properties":{"kind":{"type":"string","enum":["a","b"]},"values":{"type":"array","items":{"type":"integer"},"minItems":1},"options":{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"],"additionalProperties":False}},"required":["kind","values","options"],"additionalProperties":False}
async def listing(ctx,params):
    if mode == 'bad-schema':
        return types.ListToolsResult(tools=[types.Tool(name='bad',inputSchema={"type":"object","$ref":"https://invalid.example/schema"})])
    names = ['fail','delay','crash','image','many','structured','long','typed','read_file']
    return types.ListToolsResult(tools=[types.Tool(name=n,description='Synthetic test tool',inputSchema=schema if n=='typed' else empty) for n in names])
async def calling(ctx,params):
    n=params.name
    text=lambda value: types.TextContent(text=value)
    if n=='fail': return types.CallToolResult(content=[text('PRIVATE_REMOTE_ERROR')],isError=True)
    if n=='delay': await asyncio.sleep(30)
    if n=='crash': os._exit(0)
    if n=='image': return types.CallToolResult(content=[text('partial'),types.ImageContent(data='AA==',mimeType='image/png')])
    if n=='many': return types.CallToolResult(content=[text('one'),text('two')])
    if n=='structured': return types.CallToolResult(content=[],structuredContent={"ok":True,"values":[1,2]})
    if n=='long': return types.CallToolResult(content=[text('X'*30000)])
    return types.CallToolResult(content=[text('ok')])
async def main():
    if mode=='hang': await asyncio.sleep(30)
    server=Server('fixture',on_list_tools=listing,on_call_tool=calling)
    async with stdio_server() as streams:
        await server.run(*streams,server.create_initialization_options())
asyncio.run(main())
'''


class MCPChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name).resolve();self.workspace=self.root/'workspace';self.workspace.mkdir()
        self.fixture=self.root/'fixture.py';self.fixture.write_text(FIXTURE)
        self.pid=self.root/'pid'
        self.config=GatewayConfig(mcp_enabled=False,mcp_servers={},skills_enabled=False,context_enabled=False,
                                  session_persist=False,debug=False,workspace=self.workspace)
        self.tools=build_default_tool_registry(self.workspace)

    def demo(self,allowed=('add','echo'),**overrides):
        return dict(command=sys.executable,args=['-m','scripts.mcp_demo_server'],allowed_tools=list(allowed),tool_policies={n:'allow' for n in allowed},timeout_seconds=5,**overrides)

    def fixture_config(self,allowed,mode='normal',timeout=3):
        return replace(self.config,mcp_enabled=True,mcp_servers={'test':{'command':sys.executable,'args':[str(self.fixture),str(self.pid),mode],'allowed_tools':list(allowed),'tool_policies':{n:'allow' for n in allowed},'timeout_seconds':timeout}})

    def alive(self):
        if not self.pid.exists():return False
        try:os.kill(int(self.pid.read_text()),0);return True
        except ProcessLookupError:return False

    async def test_disabled_does_not_start(self):
        with patch('mybot.config._CONFIG',{}):
            cfg=GatewayConfig(session_persist=False)
        self.assertFalse(cfg.mcp_enabled);self.assertEqual(cfg.mcp_servers,{})
        with patch('mybot.mcp_client.transport.stdio_client',side_effect=AssertionError('must not spawn')):
            async with MCPClientManager(self.config,self.tools) as manager:
                self.assertEqual(manager.clients,{})
        self.assertEqual(len(self.tools.get_definitions()),3)

    async def test_invalid_config(self):
        invalid=[{'mcp_enabled':1},{'mcp_servers':[]},{'mcp_servers':{'bad__name':self.demo()}},
                 {'mcp_servers':{'a':dict(self.demo(),command='')}},{'mcp_servers':{'a':dict(self.demo(),args='x')}},
                 {'mcp_servers':{'a':dict(self.demo(),allowed_tools=None)}},{'mcp_servers':{'a':dict(self.demo(),allowed_tools=['add','add'])}},
                 {'mcp_servers':{'a':dict(self.demo(),timeout_seconds=True)}},{'mcp_servers':{'a':dict(self.demo(),timeout_seconds=float('nan'))}},
                 {'mcp_servers':{'a':dict(self.demo(),env={'SECRET':'x'})}}]
        for kwargs in invalid:
            with self.assertRaises(ValueError):replace(self.config,**kwargs)

    async def test_real_demo_handshake_types_add_echo_and_allowlist(self):
        cfg=replace(self.config,mcp_enabled=True,mcp_servers={'demo':self.demo()})
        async with MCPClientManager(cfg,self.tools) as manager:
            self.assertEqual(manager.protocols['demo'],'2025-11-25')
            self.assertEqual(set(manager.clients),{'demo'})
            schema=self.tools.get_parameters('mcp__demo__add')
            self.assertEqual(schema['properties']['a']['type'],'number')
            self.assertEqual(set(schema['required']),{'a','b'})
            result=await self.tools.execute('mcp__demo__add',{'a':2.5,'b':4})
            self.assertTrue(result.success);self.assertIn('6.5',result.output)
            self.assertIn('hello',(await self.tools.execute('mcp__demo__echo',{'message':'hello'})).output)
            self.assertFalse((await self.tools.execute('mcp__demo__add',{'a':True,'b':2})).success)
            self.assertFalse((await self.tools.execute('mcp__demo__add',{'a':'bad','b':2})).success)
        self.assertFalse((await self.tools.execute('mcp__demo__add',{'a':1,'b':2})).success)
        filtered=build_default_tool_registry(self.workspace)
        async with MCPClientManager(replace(cfg,mcp_servers={'demo':self.demo(('add',))}),filtered) as manager:
            self.assertFalse(filtered.has_tool('mcp__demo__echo'))
            self.assertFalse((await manager.call('demo','echo',{'message':'not allowed'})).success)

    async def test_multiple_servers_names_no_native_override(self):
        cfg=replace(self.config,mcp_enabled=True,mcp_servers={'first':self.demo(('add',)),'second':self.demo(('add',))})
        async with MCPClientManager(cfg,self.tools):
            self.assertTrue(self.tools.has_tool('mcp__first__add'));self.assertTrue(self.tools.has_tool('mcp__second__add'))
            self.assertTrue((await self.tools.execute('write_file',{'path':'a','content':'local'})).success)
        cfg=self.fixture_config(['read_file'])
        async with MCPClientManager(cfg,self.tools):
            self.assertTrue(self.tools.has_tool('read_file'));self.assertTrue(self.tools.has_tool('mcp__test__read_file'))
            self.assertIn('local',(await self.tools.execute('read_file',{'path':'a'})).output)

    async def test_rich_schema_validation_and_result_types(self):
        async with MCPClientManager(self.fixture_config(['typed','many','structured','image','long','fail']),self.tools):
            args={'kind':'a','values':[1,2],'options':{'ok':True}}
            self.assertTrue((await self.tools.execute('mcp__test__typed',args)).success)
            for bad in ({'kind':'x'},{'values':[]},{'values':['x']},{'options':{'ok':'yes'}},{'extra':1}):
                self.assertFalse((await self.tools.execute('mcp__test__typed',args|bad)).success)
            self.assertEqual((await self.tools.execute('mcp__test__many',{})).output,'one\ntwo')
            self.assertEqual(json.loads((await self.tools.execute('mcp__test__structured',{})).output),{'ok':True,'values':[1,2]})
            self.assertFalse((await self.tools.execute('mcp__test__image',{})).success)
            result=await self.tools.execute('mcp__test__long',{})
            self.assertLessEqual(len(result.output),12000);self.assertIn('truncated',result.output)
            failed=await self.tools.execute('mcp__test__fail',{})
            self.assertFalse(failed.success);self.assertNotIn('PRIVATE_REMOTE_ERROR',failed.to_text())
        self.assertFalse(self.alive())

    async def test_startup_failure_schema_and_cleanup_atomic(self):
        cfg=self.fixture_config(['bad'],mode='bad-schema')
        with self.assertRaises(MCPStartupError):
            async with MCPClientManager(cfg,self.tools):pass
        self.assertFalse(self.alive());self.assertEqual(len(self.tools.get_definitions()),3)
        cfg=replace(self.config,mcp_enabled=True,mcp_servers={'demo':dict(self.demo(),command='/nonexistent-mybot-mcp-program')})
        with self.assertRaises(MCPStartupError):
            async with MCPClientManager(cfg,self.tools):pass
        self.assertTrue((await self.tools.execute('write_file',{'path':'after','content':'ok'})).success)

    async def test_tool_timeout_disconnect_release_process(self):
        for name in ('delay','crash'):
            tools=build_default_tool_registry(self.workspace)
            async with MCPClientManager(self.fixture_config([name],timeout=0.5),tools) as manager:
                result=await tools.execute('mcp__test__'+name,{})
                self.assertFalse(result.success);self.assertTrue(manager.closed)
                self.assertFalse(self.alive())
            self.assertFalse(self.alive())

    async def test_cancel_handshake_and_body_release_process(self):
        async def run(mode):
            async with MCPClientManager(self.fixture_config(['typed'],mode=mode,timeout=5),build_default_tool_registry(self.workspace)):
                await asyncio.sleep(30)
        for mode in ('normal','hang'):
            self.pid.unlink(missing_ok=True)
            task=asyncio.create_task(run(mode))
            for _ in range(100):
                if self.pid.exists():break
                await asyncio.sleep(.02)
            self.assertTrue(self.pid.exists())
            await asyncio.sleep(.1);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertFalse(self.alive())

    async def test_exception_and_registration_conflict_release(self):
        with self.assertRaisesRegex(RuntimeError,'test exit'):
            async with MCPClientManager(self.fixture_config(['typed']),self.tools):
                raise RuntimeError('test exit')
        self.assertFalse(self.alive())
        self.tools.register(N(name='mcp__test__typed'))
        with self.assertRaises(MCPStartupError):
            async with MCPClientManager(self.fixture_config(['typed']),self.tools):pass
        self.assertFalse(self.alive())

    async def test_handshake_timeout_and_missing_allowed_tool(self):
        with self.assertRaises(MCPStartupError):
            async with MCPClientManager(self.fixture_config(['typed'],mode='hang',timeout=.5),self.tools):pass
        self.assertFalse(self.alive())
        with self.assertRaises(MCPStartupError):
            async with MCPClientManager(self.fixture_config(['missing']),self.tools):pass
        self.assertFalse(self.alive());self.assertEqual(len(self.tools.get_definitions()),3)

    async def test_gateway_owns_connections_and_closes_llm(self):
        import mybot.app as app
        observed=[]
        class Probe(AgentLoop):
            async def run(agent):
                self.assertTrue(self.alive())
                observed.append((await agent._execute('mcp__test__typed','{"kind":"a","values":[1],"options":{"ok":true}}')).success)
        client=N(close=AsyncMock())
        with patch.object(app,'build_client',return_value=client),patch.object(app,'AgentLoop',Probe),contextlib.redirect_stdout(io.StringIO()):
            await app.run_gateway(self.fixture_config(['typed']))
        self.assertEqual(observed,[True]);self.assertFalse(self.alive());client.close.assert_awaited_once()
        class Broken(AgentLoop):
            async def run(agent):raise RuntimeError('gateway synthetic failure')
        with patch.object(app,'build_client',return_value=client),patch.object(app,'AgentLoop',Broken),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,'gateway synthetic failure'):
                await app.run_gateway(self.fixture_config(['typed']))
        self.assertFalse(self.alive())

    async def test_owner_task_and_detached_adapters_are_safe(self):
        async with MCPClientManager(self.fixture_config(['typed']),self.tools) as manager:
            args={'kind':'a','values':[1],'options':{'ok':True}}
            result=await asyncio.create_task(self.tools.execute('mcp__test__typed',args))
            self.assertFalse(result.success);self.assertIn('owning',result.error)
            self.assertTrue((await self.tools.execute('mcp__test__typed',args)).success)
        self.assertFalse(self.alive())

    async def test_adapter_rejects_unsupported_schema_and_names(self):
        for schema in ({'type':'object','$ref':'https://example.invalid/schema'},
                       {'type':'object','oneOf':[]},{'type':'object','properties':{'x':{'type':'string','pattern':'a'}}}):
            with self.assertRaises(Exception):check_schema(schema)
        for name in ('bad.name','x'*64):
            with self.assertRaises(ValueError):MCPToolAdapter(None,'test',types.Tool(name=name,inputSchema={'type':'object'}))
        self.assertFalse(MCPToolAdapter.result(types.CallToolResult(content=[],structuredContent={'bad':float('nan')})).success)

    async def test_agent_protocol_session_context_clear_and_debug_mask(self):
        effects=[response(calls=[call('m','mcp__demo__echo','{"message":"PRIVATE_ECHO_BODY"}')]),response('done'),response('fresh')]
        requests=[]
        async def create(**kwargs):requests.append(kwargs);return effects.pop(0)
        cfg=replace(self.config,mcp_enabled=True,mcp_servers={'demo':self.demo()},debug=True,context_enabled=True)
        async with MCPClientManager(cfg,self.tools):
            agent=AgentLoop(N(chat=N(completions=N(create=create))),cfg,self.tools,ContextBuilder(self.workspace))
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                await agent.handle_message('echo')
                assert_pairs(self,agent.session.history())
                self.assertIn('PRIVATE_ECHO_BODY',str(agent.session.history()))
                await agent.handle_message('/clear')
                self.assertEqual(agent.session.history(),[])
                await agent.handle_message('new')
            self.assertNotIn('PRIVATE_ECHO_BODY',output.getvalue());self.assertIn('<MCP arguments omitted>',output.getvalue())
            self.assertNotIn('PRIVATE_ECHO_BODY',str(requests[-1]['messages']))
            with_schema=ContextManager.count(requests[0]['messages'],requests[0]['tools'])
            self.assertGreater(with_schema,ContextManager.count(requests[0]['messages'],None))
            self.assertTrue((await self.tools.execute('mcp__demo__add',{'a':1,'b':2})).success)

    async def test_skills_and_long_mcp_results_request_copy(self):
        effects=[response(calls=[call('s','load_skill','{"name":"file-summary"}'),call('m','mcp__test__long','{}')]),response('done')]
        requests=[]
        async def create(**kwargs):requests.append(kwargs);return effects.pop(0)
        cfg=replace(self.fixture_config(['long']),skills_enabled=True,skills_path=PROJECT_DIR/'skills',
                    context_enabled=True,context_max_chars=40000,context_tool_result_max_chars=128)
        async with MCPClientManager(cfg,self.tools):
            agent=AgentLoop(N(chat=N(completions=N(create=create))),cfg,self.tools,ContextBuilder(self.workspace))
            await agent.handle_message('read skill and external long result')
            assert_pairs(self,agent.session.history())
            self.assertTrue(agent.context_clipped)
            canonical=next(m for m in agent.session.history() if m.get('tool_call_id')=='m')['content']
            request=next(m for m in requests[-1]['messages'] if m.get('tool_call_id')=='m')['content']
            self.assertGreater(len(canonical),10000);self.assertLess(len(request),200)
            self.assertIn('MCP result truncated',canonical)
            self.assertTrue(self.tools.has_tool('load_skill'));self.assertTrue(self.tools.has_tool('mcp__test__long'))

    async def test_config_template_uv_command_and_explicit_cwd(self):
        from mybot.mcp_client import transport as module
        template=json.loads((PROJECT_DIR/'config/config.example.json').read_text())
        cfg=replace(self.config,mcp_enabled=True,mcp_servers={n:s for n,s in template['mcp']['servers'].items() if s.get('transport','stdio')=='stdio'})
        original=module.stdio_client
        with patch.object(module,'stdio_client',wraps=original) as observed:
            async with MCPClientManager(cfg,self.tools):
                self.assertTrue((await self.tools.execute('mcp__demo__add',{'a':3,'b':4})).success)
        self.assertEqual(observed.call_args.args[0].cwd,PROJECT_DIR)

    async def test_planning_success_and_failure_evidence(self):
        async with MCPClientManager(self.fixture_config(['typed','fail']),self.tools):
            agent=AgentLoop(N(),self.config,self.tools,ContextBuilder(self.workspace))
            for tool in ('typed','fail'):
                agent.plan.reset('task')
                with contextlib.redirect_stdout(io.StringIO()):
                    await agent._execute('create_plan','{"steps":["one","two"]}')
                    await agent._execute('update_plan','{"step":1,"status":"in_progress"}')
                    args={'kind':'a','values':[1],'options':{'ok':True}} if tool=='typed' else {}
                    result=await agent._execute('mcp__test__'+tool,json.dumps(args))
                self.assertEqual(result.success,tool=='typed')
                self.assertEqual(agent.plan.steps[0].verified,tool=='typed')
                if tool=='fail':self.assertEqual(agent.plan.steps[0].status,'failed')


def check_mcp():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MCPChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_mcp()
