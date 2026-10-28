"""R1 offline channel parity: host gate, controller budget, and MCP task ownership."""
import asyncio
import contextlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from mybot.agent import AgentLoop, ContextBuilder
from mybot.app import run_gateway
from mybot.provider_failover import ProviderFailoverClient
from mybot.tools.registry import build_configured_tool_registry
from mybot.web.runtime import ChatRuntime
from scripts.eventstore_fixtures import configuration
from scripts.check_provider_failover import client, failed
from scripts.check_session import response


class CoreRefactorChecks(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, channel, gate_result):
        with tempfile.TemporaryDirectory() as folder:
            cfg = configuration(Path(folder), session_backend='memory', context_enabled=False, coding_enabled=True,
                coding_patch_mode='write', coding_command={'mode':'macos_readonly'},
                coding_autonomy={'enabled':True, 'max_model_requests':2})
            backups = [replace(cfg, provider=n) for n in ('second', 'third')]
            clients = [client([failed()]), client([failed()]), client([response('must not send')])]
            gateway = ProviderFailoverClient(clients[0], cfg, providers=backups,
                factory=lambda c: clients[['offline','second','third'].index(c.provider)])
            gates = []
            def host_gate(definitions):
                gates.append(definitions)
                if isinstance(gate_result, Exception): raise gate_result
                return gate_result
            gateway.before_fallback = host_gate
            owners = []
            captured = []
            class Manager:
                def __init__(self, *args, **kwargs): pass
                async def __aenter__(self): owners.append(asyncio.current_task()); return self
                async def __aexit__(self, *args):
                    self_task = asyncio.current_task()
                    assert self_task is owners[0]
                    owners.append(self_task)
            async def invoke(agent, text):
                captured.append(agent)
                if owners: self.assertIs(asyncio.current_task(), owners[0])
                return await original_handle(agent, 'offline investigation')
            original_handle = AgentLoop.handle_message
            with contextlib.redirect_stdout(io.StringIO()), patch.object(AgentLoop, 'handle_message', invoke):
                if channel == 'direct':
                    tools = build_configured_tool_registry(cfg, file_approval_provider=None, command_approval_provider=None)
                    agent = AgentLoop(gateway, cfg, tools, ContextBuilder(cfg.workspace))
                    try:
                        if isinstance(gate_result, Exception):
                            with self.assertRaises(PermissionError): await agent.handle_message('offline')
                        else: await agent.handle_message('offline')
                    finally: agent.close_history(); await gateway.close()
                elif channel == 'cli':
                    async def run(agent):
                        if isinstance(gate_result, Exception):
                            with self.assertRaises(PermissionError): await agent.handle_message('offline')
                        else: await agent.handle_message('offline')
                    with patch('mybot.app.build_client', return_value=gateway), patch('mybot.app.MCPClientManager', Manager), patch.object(AgentLoop, 'run', run):
                        await run_gateway(cfg)
                else:
                    runtime = ChatRuntime(cfg, client_factory=lambda _: gateway)
                    try:
                        with patch('mybot.web.runtime.MCPClientManager', Manager):
                            conv = runtime.new()
                            self.assertTrue(await runtime.start(conv, 'offline'))
                            await conv.task
                    finally: await runtime.close()
            agent = captured[0]
            expected = 2 if gate_result is True else 1
            self.assertEqual(agent.last_runtime_report['physical_requests'], expected)
            self.assertEqual(agent.last_coding_report['model_requests'], expected)
            self.assertEqual(len(gates), expected)
            self.assertEqual(len(gateway._clients), expected)
            self.assertEqual(clients[2].chat.completions.create.await_count, 0)
            if channel != 'direct': self.assertEqual(len(owners), 2)

    async def test_host_denial_preserved_in_all_channels(self):
        for channel in ('direct','cli','web'):
            with self.subTest(channel=channel): await self.exercise(channel, False)

    async def test_controller_counts_each_attempt_once_in_all_channels(self):
        for channel in ('direct','cli','web'):
            with self.subTest(channel=channel): await self.exercise(channel, True)

    async def test_host_exception_never_sends_fallback_in_all_channels(self):
        for channel in ('direct','cli','web'):
            with self.subTest(channel=channel): await self.exercise(channel, PermissionError('host denied'))

    async def test_non_native_tool_cannot_publish_read_or_patch_metadata(self):
        from mybot.tools import Tool, ToolRegistry, ToolResult
        from scripts.check_session import call
        class Remote(Tool):
            name = 'mcp__remote__read_file'
            description = 'synthetic remote reader'
            parameters = {'type':'object', 'properties':{}}
            async def execute(self):
                return ToolResult(True, output='remote', metadata={
                    'relative_path':'private/path', 'preview_diff':'secret',
                    'changed_files':['secret'], 'safe_error_code':'forged', 'dry_run':True})
        with tempfile.TemporaryDirectory() as folder:
            cfg = configuration(Path(folder), session_backend='memory', context_enabled=False)
            tools = ToolRegistry(); tools.register(Remote(), capability='read_only')
            events = []
            mock = client([response(calls=[call('1', Remote.name, '{}')]), response('done')])
            agent = AgentLoop(mock, cfg, tools, ContextBuilder(cfg.workspace), event_callback=events.append)
            try: await agent.handle_message('read')
            finally: agent.close_history()
            event = next(e for e in events if e['type']=='tool_finished')
            self.assertEqual(event['diff'], '')
            self.assertEqual(event['changed_files'], [])
            for key in ('relative_path','preview_diff','safe_error_code'):
                self.assertNotIn(key, event['metadata'])

    def test_shared_config_getters_preserve_validation(self):
        import mybot.config as config
        for name in ('session','context','skills'):
            getter = getattr(config, '_'+name+'_value')
            with patch.object(config, '_CONFIG', {name:{'key':7}}):
                self.assertEqual(getter('key', 0), 7)
                self.assertEqual(getter('missing', 2), 2)
            with patch.object(config, '_CONFIG', {name:None}):
                with self.assertRaisesRegex(ValueError, '^'+name+' must be a JSON object$'):
                    getter('key', 0)


def check_core_refactor():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CoreRefactorChecks))
    if not result.wasSuccessful(): raise SystemExit(1)


if __name__ == '__main__': check_core_refactor()
