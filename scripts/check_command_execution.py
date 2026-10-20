"""Offline native command/approval/real Seatbelt regression. No real LLM or remote MCP."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, patch
from jsonschema import Draft202012Validator
from mybot.config import GatewayConfig
from mybot.tools import Tool, ToolResult, build_default_tool_registry
from mybot.tools.run_command import RunCommandTool, parse_arguments
from mybot.tools.command_process import resolve_launch, trusted_python, CommandProcessResult
from mybot.tools.command_approval import cli_command_approval, inspectable_command
from mybot.tools import macos_sandbox
from mybot.mcp_client.approval import ApprovalDecision
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.planning import Plan
from mybot.evaluation.tool_agent import pair_messages
from scripts.coding_repo_demo import make_command_demo, command_demo, fingerprint
from scripts.check_session import call, response


async def approve(request): return ApprovalDecision.APPROVE


class CommandChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = make_command_demo(Path(self.tmp.name)/'repo')
        self.tool = self.make_tool()

    def make_tool(self, *, mode='host_confirm', provider=approve, **config):
        return RunCommandTool(self.root, command={'mode':mode,**config},patch_mode='write',approval_provider=provider)

    async def command(self, code='print("hello")', **kwargs):
        return await self.tool.execute(argv=['python','-c',code],**kwargs)

    def body(self,r):return json.loads(r.output)

    async def test_defaults_unchanged_and_off_guess_rejected(self):
        self.assertEqual(GatewayConfig().coding_command,{'mode':'off','timeout_seconds':30,'max_output_bytes':32768})
        for flag,mode in [(False,'off'),(True,'off'),(True,'preview'),(True,'write')]:
            old=build_default_tool_registry(self.root,coding_enabled=flag,patch_mode=mode)
            new=build_default_tool_registry(self.root,coding_enabled=flag,patch_mode=mode,command={'mode':'off'})
            self.assertEqual(old.get_definitions(),new.get_definitions())
            self.assertFalse((await old.execute('run_command',{'argv':['python']})).success)
        self.assertEqual(len(build_default_tool_registry(self.root).iter_tools()),3)

    async def test_strict_config(self):
        for value in [None,[],False,{'extra':1},{'mode':True},{'mode':'automatic'}, {'timeout_seconds':0},
            {'timeout_seconds':61},{'timeout_seconds':True},{'timeout_seconds':30.0},
            {'max_output_bytes':4095},{'max_output_bytes':131073},{'max_output_bytes':'32768'}]:
            with self.assertRaises(ValueError):GatewayConfig(coding_command=value)
        for mode in ('host_confirm','macos_readonly'):
            with self.assertRaises(ValueError):GatewayConfig(coding_command={'mode':mode})
        with self.assertRaises(ValueError):GatewayConfig(coding_enabled=True,coding_patch_mode='preview',coding_command={'mode':'host_confirm'})
        for mode in ('preview','write'):
            self.assertEqual(GatewayConfig(coding_enabled=True,coding_patch_mode=mode,coding_command={'mode':'macos_readonly'}).coding_command['mode'],'macos_readonly')
        with patch('mybot.config._CONFIG',{'coding':{'enabled':True,'patch_mode':'write','command':{'extra':1}}}):
            with self.assertRaises(ValueError):GatewayConfig()

    async def test_registry_registration_and_patch_only(self):
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='preview',command={'mode':'macos_readonly'})
        self.assertTrue(tools.has_tool('run_command'));self.assertTrue(tools.has_tool('apply_patch'));self.assertFalse(tools.has_tool('write_file'))
        r=await tools.execute('run_command',{'argv':['python','-c','print(1)']})
        self.assertEqual(r.error,'approval_unavailable');self.assertFalse(r.metadata['spawned'])
        with self.assertRaises(ValueError):build_default_tool_registry(self.root,command={'mode':'host_confirm'})

    async def test_schema(self):
        Draft202012Validator.check_schema(self.tool.parameters)
        for args in [{},{'argv':[]},{'argv':'python -c print(1)'},{'argv':['python',1]},
            {'argv':['python'],'env':{}},{'argv':['python'],'stdin':'x'}, {'command':'python'},
            {'argv':['python'],'timeout_seconds':True},{'argv':['python'],'profile':'allow default'},
            {'argv':['python'],'user':'root'},{'argv':['python'],'cwd':1}, {'argv':['python']*33},
            {'argv':['python','x'*2049]},{'argv':['python']+['中'*1000]*4}]:
            with patch('mybot.tools.run_command.run_process') as run:
                r=await self.tool.execute(**args);self.assertFalse(r.success,args);run.assert_not_called()

    async def test_raw_bound_before_decode_and_duplicate_keys(self):
        with patch('mybot.tools.arguments.json.loads',side_effect=AssertionError('decoded oversize')):
            for raw in [' ' * 16385,'中'*8192]:
                with self.assertRaises(ValueError):parse_arguments(raw)
        for raw in ['{"argv":[],"argv":["python"]}','{"argv":["python"],"timeout_seconds":NaN}',
                    '{"argv":["python"],"timeout_seconds":Infinity}', '['*1000+']'*1000]:
            with self.assertRaises(ValueError):parse_arguments(raw)
        deep={};cur=deep
        for i in range(8):cur['x']={};cur=cur['x']
        with self.assertRaises(ValueError):parse_arguments(deep)

    async def test_requested_timeout_cannot_raise_cap(self):
        self.tool=self.make_tool(timeout_seconds=1)
        r=await self.command(timeout_seconds=2);self.assertEqual(r.error,'timeout_exceeds_configuration')

    async def test_cwd_boundary_and_symlinks(self):
        (self.root/'link').symlink_to(Path(self.tmp.name))
        (self.root/'inside').symlink_to(self.root/'src')
        for cwd in ('../','missing',str(Path(self.tmp.name)),'.git','link','inside'):
            r=await self.command(cwd=cwd);self.assertFalse(r.success,cwd);self.assertFalse(r.metadata['spawned'])
        r=await self.command('import os;print(os.path.basename(os.getcwd()))',cwd='src')
        self.assertTrue(r.success);self.assertIn('src',r.output)

    def test_cwd_schema_documents_contract_without_narrowing_input(self):
        spec = self.tool.to_schema()['function']['parameters']
        cwd = dict(spec['properties']['cwd'])
        self.assertEqual(cwd.pop('default'), '.')
        description = cwd.pop('description')
        self.assertEqual(cwd, {'type':'string','minLength':1,'maxLength':4096})
        for word in ('Optional', 'prefer omitting', 'workspace root', 'existing',
                     'workspace-relative', 'absolute', "'..'", 'symlinks', 'host', 'temporary'):
            self.assertIn(word, description)
        self.assertIn('Prefer omitting optional cwd', self.tool.description)
        self.assertEqual(spec['required'], ['argv'])
        # These annotations describe runtime policy; they do not change JSON input validity.
        validator = Draft202012Validator(spec)
        for value in ('.','src','/tmp/absolute','src/..','missing','link'):
            self.assertTrue(validator.is_valid({'argv':['python'],'cwd':value}))
        for value in ('', 1, None, 'x'*4097):
            self.assertFalse(validator.is_valid({'argv':['python'],'cwd':value}))

    async def test_cwd_omitted_and_dot_run_real_unittest_at_root(self):
        (self.root/'tests/test_cwd_location.py').write_text(
            'from pathlib import Path\nimport unittest\n'
            'class Location(unittest.TestCase):\n'
            ' def test_root(self): self.assertTrue(Path("src/calculator.py").is_file())\n')
        requests = []
        async def provider(request):
            requests.append(request)
            return ApprovalDecision.APPROVE
        self.tool = self.make_tool(mode='macos_readonly', provider=provider)
        argv = ['python','-m','unittest','discover','-s','tests','-p','test_cwd_location.py','-v']
        for options in ({}, {'cwd':'.'}):
            result = await self.tool.execute(argv=argv, **options)
            self.assertTrue(result.success, result.to_text())
            self.assertEqual(result.metadata['exit_code'], 0)
            for field in ('approved','spawned','completed','sandbox_applied','execution_evidence'):
                self.assertTrue(result.metadata[field])
            self.assertIn('Ran 1 test', self.body(result)['stderr'])
        self.assertEqual([request.cwd for request in requests], ['.','.'])
        self.assertTrue(all(request.mode=='macos_readonly' and request.os_sandbox for request in requests))
        self.assertTrue(all(request.timeout_seconds==30 for request in requests))

    async def test_existing_relative_cwd_runs_real_unittest(self):
        (self.root/'src/test_cwd_location.py').write_text(
            'from pathlib import Path\nimport unittest\n'
            'class Location(unittest.TestCase):\n'
            ' def test_src(self): self.assertTrue(Path("calculator.py").is_file())\n')
        approval = AsyncMock(return_value=ApprovalDecision.APPROVE)
        self.tool = self.make_tool(mode='macos_readonly', provider=approval)
        result = await self.tool.execute(argv=['python','-m','unittest','discover','-s','.',
            '-p','test_cwd_location.py','-v'], cwd='src')
        self.assertTrue(result.success, result.to_text())
        self.assertTrue(result.metadata['sandbox_applied'])
        self.assertIn('Ran 1 test', self.body(result)['stderr'])
        approval.assert_awaited_once()
        self.assertEqual(approval.call_args.args[0].cwd, 'src')

    async def test_illegal_cwd_rejected_before_approval_and_process(self):
        (self.root/'internal_alias').symlink_to(self.root/'src')
        (self.root/'external_alias').symlink_to(Path(self.tmp.name))
        approval = AsyncMock(return_value=ApprovalDecision.APPROVE)
        self.tool = self.make_tool(mode='macos_readonly', provider=approval)
        invalid = (str(self.root), str(Path(self.tmp.name)), '..', 'src/..', 'missing',
                   'README.md', 'internal_alias', 'internal_alias/missing', 'external_alias', '.git')
        with patch('mybot.tools.run_command.run_process') as process, \
                patch('mybot.tools.run_command.resolve_launch') as launch, \
                patch('mybot.tools.macos_sandbox.verify_sandbox') as sandbox:
            for cwd in invalid:
                with self.subTest(cwd=cwd):
                    result = await self.tool.execute(argv=['python','-m','unittest'], cwd=cwd)
                    self.assertFalse(result.success)
                    self.assertTrue(result.metadata['command_fatal'])
                    for field in ('approved','spawned','completed','sandbox_applied','execution_evidence'):
                        self.assertFalse(result.metadata[field])
            approval.assert_not_awaited()
            launch.assert_not_called(); sandbox.assert_not_called(); process.assert_not_called()

    async def test_workspace_fake_python_and_path_ignored(self):
        fake=self.root/'python';fake.write_text('#!/bin/sh\ntouch HACKED\n');fake.chmod(0o755)
        with patch.dict(os.environ,{'PATH':str(self.root)}):r=await self.command()
        self.assertTrue(r.success,r.to_text());self.assertFalse((self.root/'HACKED').exists())
        for exe in ('./python',str(fake),'sh','bash','git'):
            r=await self.tool.execute(argv=[exe]);self.assertEqual(r.error,'unsupported_command')

    async def test_bad_project_virtualenv_refused(self):
        v=self.root/'.venv/bin';v.mkdir(parents=True)
        p=v/'python';p.write_text('#!/bin/sh\ntouch HACKED\n');p.chmod(0o755)
        (self.root/'.venv/pyvenv.cfg').write_text('home = /usr/bin\ninclude-system-site-packages = false\n')
        r=await self.command();self.assertEqual(r.error,'untrusted_virtualenv');self.assertFalse((self.root/'HACKED').exists())

    async def test_valid_project_virtualenv_used(self):
        import subprocess
        subprocess.run([sys.executable,'-m','venv','--without-pip',str(self.root/'.venv')],check=True,capture_output=True)
        requests=[]
        async def yes(req):requests.append(req);return ApprovalDecision.APPROVE
        self.tool=self.make_tool(provider=yes)
        r=await self.command('import sys;from pathlib import Path;print(Path(sys.prefix).resolve()==Path(".venv").resolve())')
        self.assertTrue(r.success,r.to_text());self.assertEqual(self.body(r)['stdout'],'True\n')
        self.assertEqual(requests[0].argv[0],str(self.root/'.venv/bin/python'))

    async def test_uv_pinned_offline_and_real(self):
        r=await self.tool.execute(argv=['uv','run','--no-sync','python','-c','print("uv actual")'])
        self.assertTrue(r.success,r.to_text());self.assertIn('uv actual',r.output)
        for argv in [['uv','sync'],['uv','run','--with','evil','python'],['uv','run','python']]:
            r=await self.tool.execute(argv=argv);self.assertEqual(r.error,'unsupported_command')

    async def test_missing_executable(self):
        with patch('mybot.tools.command_process.trusted_uv',side_effect=FileNotFoundError()):
            r=await self.tool.execute(argv=['uv','run','--no-sync','python'])
        self.assertEqual(r.error,'executable_missing');self.assertFalse(r.metadata['spawned'])

    async def test_no_shell_and_stdin_devnull(self):
        r=await self.command('import sys;print(sys.stdin.read());print(sys.argv[1])',)
        self.assertTrue(r.success is False)  # real IndexError, not a launch error
        r=await self.tool.execute(argv=['python','-c','import sys;print(sys.stdin.read()=="");print(sys.argv[1])','$(touch HACKED); echo X'])
        self.assertTrue(r.success);self.assertIn('True',r.output);self.assertFalse((self.root/'HACKED').exists())

    async def test_no_provider_denies_before_process(self):
        self.tool=self.make_tool(provider=None)
        with patch('mybot.tools.run_command.run_process') as process:r=await self.command()
        self.assertEqual(r.error,'approval_unavailable');process.assert_not_called()

    async def test_deny_bool_and_provider_error(self):
        for decision in (ApprovalDecision.DENY,True,None):
            async def provider(req):return decision
            self.tool=self.make_tool(provider=provider)
            with patch('mybot.tools.run_command.run_process') as run:r=await self.command()
            self.assertFalse(r.success);self.assertTrue(r.metadata['permission_denied']);run.assert_not_called()
        async def bad(req):raise RuntimeError('PRIVATE_ERROR')
        self.tool=self.make_tool(provider=bad);r=await self.command()
        self.assertEqual(r.error,'approval_error');self.assertNotIn('PRIVATE_ERROR',r.to_text())

    async def test_cli_noninteractive_denies(self):
        request=inspectable_command('host_confirm','.',('python','-c','print(1)'),1)
        with patch('sys.stdin.isatty',return_value=False),patch('sys.stdout.isatty',return_value=False):
            self.assertIs(await cli_command_approval(request),ApprovalDecision.DENY)

    async def test_cli_displays_full_effective_command_and_warning(self):
        request=inspectable_command('host_confirm','src',('python','-c','print(1)'),2)
        with contextlib.redirect_stdout(io.StringIO()) as log,patch('sys.stdin.isatty',return_value=True),patch('sys.stdout.isatty',return_value=True),patch('builtins.input',return_value='yes'):
            self.assertIs(await cli_command_approval(request),ApprovalDecision.APPROVE)
        self.assertIn(request.display_json,log.getvalue());self.assertIn('无 OS 沙盒',log.getvalue())

    async def test_approval_snapshot_and_immutable_request(self):
        args={'argv':['python','-c','print("approved original")']}
        async def provider(req):
            self.assertEqual(req.cwd,'.');self.assertEqual(req.mode,'host_confirm')
            self.assertEqual(req.argv[-1],args['argv'][-1])
            with self.assertRaises(FrozenInstanceError):req.cwd='..'
            args['argv'][-1]='print("changed")'
            return ApprovalDecision.APPROVE
        self.tool=self.make_tool(provider=provider)
        r=await self.tool.execute(**args)
        self.assertTrue(r.success);self.assertIn('approved original',r.output);self.assertNotIn('changed',r.output)

    async def test_cwd_changed_during_approval(self):
        sub=self.root/'sub';sub.mkdir()
        async def provider(req):sub.rename(self.root/'moved');sub.mkdir();return ApprovalDecision.APPROVE
        self.tool=self.make_tool(provider=provider)
        with patch('mybot.tools.run_command.run_process') as run:r=await self.command(cwd='sub')
        self.assertEqual(r.error,'cwd_changed');run.assert_not_called()

    async def test_runtime_changed_after_approval(self):
        actual=resolve_launch(('python','-c','print("hello")'),self.root)
        with patch('mybot.tools.run_command.resolve_launch',side_effect=[actual,N()]):
            r=await self.command()
        self.assertEqual(r.error,'runtime_changed');self.assertFalse(r.metadata['spawned'])

    async def test_each_call_has_fresh_approval(self):
        count=0
        async def provider(req):
            nonlocal count
            count+=1;return ApprovalDecision.APPROVE if count==1 else ApprovalDecision.DENY
        self.tool=self.make_tool(provider=provider)
        self.assertTrue((await self.command()).success);self.assertFalse((await self.command()).success);self.assertEqual(count,2)

    async def test_unsafe_approval_refuses_and_controls_are_escaped(self):
        with patch('mybot.tools.run_command.run_process') as run:
            for arg in ('--password=x','Bearer abcdef','中'*2048):
                r=await self.tool.execute(argv=['python','-c','print(1)',arg])
                self.assertFalse(r.success);self.assertEqual(r.error,'approval_uninspectable')
            run.assert_not_called()
        req=inspectable_command('host_confirm','.',('python','\x1b\n\u202e'),1)
        self.assertIsNotNone(req);self.assertNotIn('\x1b',req.display_json);self.assertNotIn('\u202e',req.display_json)
        self.assertIn('\\u001b',req.display_json);self.assertIn('\\u202e',req.display_json)

    async def test_cancel_approval_propagates_without_spawn(self):
        entered=asyncio.Event()
        async def provider(req):entered.set();await asyncio.sleep(60)
        self.tool=self.make_tool(provider=provider)
        with patch('mybot.tools.run_command.run_process') as run:
            task=asyncio.create_task(self.command());await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            run.assert_not_called()

    async def test_stdout_stderr_exit_and_duration(self):
        r=await self.command('import sys;print("actual out");print("actual err",file=sys.stderr)')
        self.assertTrue(r.success);self.assertEqual(self.body(r),{'stdout':'actual out\n','stderr':'actual err\n'})
        self.assertEqual(r.metadata['exit_code'],0);self.assertTrue(r.metadata['spawned']);self.assertTrue(r.metadata['completed'])
        self.assertGreater(r.metadata['duration_ms'],0);self.assertFalse(r.metadata['sandbox_applied'])
        self.assertEqual(r.metadata['stdout_bytes'],11);self.assertEqual(r.metadata['stderr_bytes'],11)

    async def test_nonzero_is_real_completed_feedback(self):
        r=await self.command('import sys;print("assert failed",file=sys.stderr);sys.exit(3)')
        self.assertFalse(r.success);self.assertEqual(r.metadata['exit_code'],3)
        self.assertTrue(r.metadata['completed']);self.assertTrue(r.metadata['command_nonzero']);self.assertNotIn('safe_to_retry',r.metadata)
        self.assertFalse(r.metadata['execution_evidence']);self.assertIn('assert failed',r.output)

    async def test_both_streams_large_bounded(self):
        self.tool=self.make_tool(max_output_bytes=4096)
        r=await self.command('import os;os.write(1,b"x"*3000);os.write(2,b"y"*1000000)')
        self.assertEqual(r.error,'output_limit_exceeded');self.assertTrue(r.metadata['output_truncated']);self.assertFalse(r.metadata['completed'])
        body=self.body(r);self.assertLessEqual(len(body['stdout'])+len(body['stderr']),4096)
        self.assertTrue(r.metadata['process_terminated'])

    async def test_invalid_utf8_and_terminal_controls(self):
        r=await self.command('import os;os.write(1,b"\\xff\\x1b[2J\\x00")')
        self.assertTrue(r.success);self.assertTrue(r.metadata['encoding_replaced'])
        stdout=self.body(r)['stdout'];self.assertNotIn('\x1b',stdout);self.assertNotIn('\0',stdout);self.assertIn('\\x1b',stdout)

    async def test_environment_not_inherited_and_temporary_home(self):
        values={'OPENAI_API_KEY':'not inherited','AWS_ACCESS_KEY_ID':'not inherited','HTTP_PROXY':'bad','PYTHONPATH':'bad','GIT_DIR':'bad','DYLD_INSERT_LIBRARIES':'bad'}
        with patch.dict(os.environ,values):r=await self.command('import os,json;print(json.dumps(dict(os.environ)))')
        self.assertTrue(r.success,r.to_text());env=json.loads(self.body(r)['stdout'])
        self.assertFalse(set(values)&env.keys());self.assertEqual(env['HOME'],'<run-temp>');self.assertEqual(env['PYTHONDONTWRITEBYTECODE'],'1')

    async def test_output_home_paths_and_credential_markers_redacted(self):
        r=await self.command('import os;print(os.path.expanduser("~"));print("/Users/example/private");print("sk-"+"x"*24)')
        self.assertTrue(r.success);self.assertNotIn('/Users/',r.output);self.assertIn('<redacted>',r.output)

    async def wait_pid_gone(self,pid):
        for _ in range(50):
            try:os.kill(pid,0)
            except ProcessLookupError:return
            await asyncio.sleep(.02)
        self.fail('managed process still alive')

    async def test_timeout_reaps_own_process(self):
        pidfile=self.root/'pid'
        code=f'import os,time,pathlib;pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()));time.sleep(60)'
        self.tool=self.make_tool(timeout_seconds=1)
        start=time.monotonic();r=await self.command(code)
        self.assertEqual(r.error,'timed_out');self.assertTrue(r.metadata['timed_out']);self.assertFalse(r.metadata['completed'])
        self.assertLess(time.monotonic()-start,4);await self.wait_pid_gone(int(pidfile.read_text()))

    async def test_cancel_reaps_process_and_propagates(self):
        pidfile=self.root/'pid'
        code=f'import os,time,pathlib;pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()));time.sleep(60)'
        task=asyncio.create_task(self.command(code))
        for _ in range(100):
            if pidfile.exists():break
            await asyncio.sleep(.01)
        self.assertTrue(pidfile.exists());task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        await self.wait_pid_gone(int(pidfile.read_text()))

    async def test_process_group_children_and_unrelated_survive(self):
        pidfile=self.root/'childpid'
        code=f'import subprocess,sys,time,pathlib;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]);pathlib.Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(60)'
        other=await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(60)')
        try:
            self.tool=self.make_tool(timeout_seconds=1);r=await self.command(code)
            self.assertEqual(r.error,'timed_out');await self.wait_pid_gone(int(pidfile.read_text()));self.assertIsNone(other.returncode)
        finally:other.kill();await other.wait()

    async def test_killpg_permission_fallback(self):
        self.tool=self.make_tool(timeout_seconds=1)
        with patch('mybot.tools.command_process.os.killpg',side_effect=PermissionError()):
            r=await self.command('import time;time.sleep(60)')
        self.assertEqual(r.error,'timed_out');self.assertTrue(r.metadata['process_terminated'])

    async def test_cancel_during_spawn_does_not_lose_process(self):
        original=asyncio.create_subprocess_exec;entered=asyncio.Event();pids=[]
        async def slow_spawn(*args,**kwargs):
            proc=await original(*args,**kwargs);pids.append(proc.pid);entered.set();await asyncio.sleep(.1);return proc
        with patch('mybot.tools.command_process.asyncio.create_subprocess_exec',side_effect=slow_spawn):
            task=asyncio.create_task(self.command('import time;time.sleep(60)'))
            await entered.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        await self.wait_pid_gone(pids[0])

    async def test_detached_pipe_holder_cleanup_is_bounded(self):
        import signal
        pidfile=self.root/'detached-pid'
        code=f'import subprocess,sys,pathlib;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"],start_new_session=True);pathlib.Path({str(pidfile)!r}).write_text(str(p.pid))'
        self.tool=self.make_tool(timeout_seconds=1);start=time.monotonic()
        try:
            r=await self.command(code)
            self.assertEqual(r.error,'timed_out');self.assertLess(time.monotonic()-start,4)
            # Detached descendants are explicitly outside killpg guarantees. This
            # test owns the synthetic PID and cleans it separately, never by name.
            pid=int(pidfile.read_text());os.kill(pid,0)
        finally:
            if pidfile.exists():
                try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
                except ProcessLookupError:pass

    async def test_file_size_limit_enforced(self):
        r=await self.command('import os,pathlib;p=pathlib.Path(os.environ["TMPDIR"])/"large";p.write_bytes(b"x"*(9*1024*1024))')
        self.assertFalse(r.success);self.assertFalse(r.metadata['execution_evidence'])
        self.assertTrue('File too large' in r.output or r.metadata['status']=='process_signaled',r.to_text())

    async def test_spawn_failure_and_unknown_state(self):
        with patch('mybot.tools.run_command.run_process',side_effect=OSError('PRIVATE host path')):r=await self.command()
        self.assertFalse(r.success);self.assertNotIn('PRIVATE host path',r.to_text());self.assertFalse(r.metadata['spawned'])
        unknown=CommandProcessResult('process_state_unknown',None,b'',b'',0,0,1,True,True,False)
        with patch('mybot.tools.run_command.run_process',return_value=unknown):r=await self.command()
        self.assertFalse(r.metadata['completed']);self.assertTrue(r.metadata['command_fatal'])

    async def test_temporary_files_cleaned(self):
        r=await self.command('import tempfile,pathlib;f=tempfile.NamedTemporaryFile(delete=False);f.write(b"data");f.close();print("temp-ok")')
        self.assertTrue(r.success);self.assertEqual(self.body(r)['stdout'],'temp-ok\n')
        self.assertFalse(any(p.name.startswith('mybot-command-') for p in self.root.iterdir()))

    async def test_temporary_entry_limit_terminates(self):
        r=await self.command('import os,pathlib,time;[(pathlib.Path(os.environ["TMPDIR"])/str(i)).touch() for i in range(600)];time.sleep(3)')
        self.assertEqual(r.error,'temporary_limit_exceeded');self.assertTrue(r.metadata['process_terminated'])

    async def test_macos_real_complete_probe(self):
        self.assertTrue(macos_sandbox.available(),'Required macOS Seatbelt unavailable: Phase21 cannot be accepted here')
        _,roots,_=trusted_python(self.root)
        self.assertTrue(await macos_sandbox.verify_sandbox(roots),'Real positive/negative isolation probe failed')

    async def test_sandbox_real_unittest_and_temp_write(self):
        self.tool=self.make_tool(mode='macos_readonly')
        r=await self.command('import pathlib,tempfile;print(pathlib.Path("README.md").read_text());p=pathlib.Path(tempfile.gettempdir())/"ok";p.write_text("data");print(p.read_text())')
        self.assertTrue(r.success,r.to_text());self.assertTrue(r.metadata['sandbox_applied']);self.assertIn('data',r.output)

    async def test_sandbox_rejects_workspace_and_index_writes(self):
        self.tool=self.make_tool(mode='macos_readonly')
        for path in ('src/calculator.py','.git/index'):
            before=(self.root/path).read_bytes()
            r=await self.command(f'from pathlib import Path;Path({path!r}).write_bytes(b"BAD")')
            self.assertFalse(r.success);self.assertTrue(r.metadata['sandbox_applied']);self.assertEqual((self.root/path).read_bytes(),before)
            self.assertIn('PermissionError',r.output)

    async def test_sandbox_external_private_read_write_and_alias(self):
        target=Path(self.tmp.name)/'private-data';target.write_text('sentinel')
        (self.root/'alias').symlink_to(target)
        self.tool=self.make_tool(mode='macos_readonly')
        for operation in (f'Path({str(target)!r}).read_text()',f'Path({str(target)!r}).write_text("BAD")','Path("alias").write_text("BAD")'):
            r=await self.command('from pathlib import Path;'+operation)
            self.assertFalse(r.success);self.assertTrue(r.metadata['sandbox_applied']);self.assertEqual(target.read_text(),'sentinel')

    async def test_sandbox_real_reachable_network_block(self):
        async def accept(reader,writer):writer.close();await writer.wait_closed()
        server=await asyncio.start_server(accept,'127.0.0.1',0)
        try:
            port=server.sockets[0].getsockname()[1]
            _,writer=await asyncio.open_connection('127.0.0.1',port);writer.close();await writer.wait_closed()
            code=f'import socket;socket.create_connection(("127.0.0.1",{port}),timeout=1);print("BAD")'
            host=await self.command(code);self.assertTrue(host.success,host.to_text())
            self.tool=self.make_tool(mode='macos_readonly');r=await self.command(code)
            self.assertFalse(r.success);self.assertTrue(r.metadata['sandbox_applied']);self.assertIn('PermissionError',r.output)
        finally:server.close();await server.wait_closed()

    async def test_sandbox_uv_and_valid_venv(self):
        self.tool=self.make_tool(mode='macos_readonly')
        r=await self.tool.execute(argv=['uv','run','--no-sync','python','-c','print("sandbox uv")'])
        self.assertTrue(r.success,r.to_text());self.assertTrue(r.metadata['sandbox_applied'])

    async def test_sandbox_failure_and_non_macos_fail_closed(self):
        self.tool=self.make_tool(mode='macos_readonly')
        for target,value in [('mybot.tools.macos_sandbox.verify_sandbox',False),('mybot.tools.macos_sandbox.available',False)]:
            stub=AsyncMock(return_value=value) if target.endswith('verify_sandbox') else lambda:False
            with patch(target,stub),patch('mybot.tools.run_command.run_process') as run:r=await self.command()
            self.assertEqual(r.error,'sandbox_unavailable');run.assert_not_called();self.assertFalse(r.metadata['spawned'])
        with patch('mybot.tools.macos_sandbox.sys.platform','linux'):self.assertFalse(macos_sandbox.available())

    async def test_invalid_profile_never_runs_project_command(self):
        self.tool=self.make_tool(mode='macos_readonly')
        with patch('mybot.tools.macos_sandbox.profile',return_value='(invalid-profile)'),patch('mybot.tools.run_command.run_process') as run:
            r=await self.command()
        self.assertEqual(r.error,'sandbox_unavailable');run.assert_not_called()

    async def test_sandbox_denies_external_process_arguments_sysctl(self):
        code='import ctypes,os;lib=ctypes.CDLL(None,use_errno=True);mib=(ctypes.c_int*3)(1,49,os.getppid());buf=ctypes.create_string_buffer(262144);n=ctypes.c_size_t(len(buf));r=lib.sysctl(mib,3,buf,ctypes.byref(n),None,0);print(r,ctypes.get_errno())'
        host=await self.command(code);self.assertTrue(host.success,host.to_text());self.assertTrue(self.body(host)['stdout'].startswith('0 '))
        self.tool=self.make_tool(mode='macos_readonly');r=await self.command(code)
        self.assertTrue(r.success,r.to_text());self.assertTrue(self.body(r)['stdout'].startswith('-1 '))

    async def test_profile_is_fixed_not_model_supplied_and_no_home_subpath(self):
        _,roots,_=trusted_python(self.root)
        with tempfile.TemporaryDirectory(dir='/private/tmp') as t:
            policy=macos_sandbox.profile(self.root,Path(t),roots)
            self.assertIn('(deny default)',policy);self.assertNotIn('(allow network',policy)
            self.assertNotIn('(subpath '+json.dumps(str(Path.home()))+')',policy)
            self.assertIn('(deny file-link)',policy)
            with self.assertRaises(ValueError):macos_sandbox.profile(Path.home(),Path(t),roots)
        self.assertNotIn('profile',self.tool.parameters['properties'])

    def agent(self, tools=None, client=None, **kw):
        cfg=GatewayConfig(workspace=self.root,coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'host_confirm'},skills_enabled=False,session_persist=False,debug=True,**kw)
        tools=tools or build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command=cfg.coding_command,command_approval_provider=approve)
        return AgentLoop(client or N(),cfg,tools,ContextBuilder(self.root))

    async def test_plan_nonzero_not_verified_and_can_continue(self):
        agent=self.agent()
        with contextlib.redirect_stdout(io.StringIO()):agent.plan.create(['test and repair','verify']);agent.plan.update(1,'in_progress')
        args=json.dumps({'argv':['python','-c','raise SystemExit(1)']})
        with contextlib.redirect_stdout(io.StringIO()):r=await agent._execute('run_command',args)
        self.assertFalse(r.success);self.assertIsNotNone(agent.plan.active);self.assertFalse(agent.plan.active.verified)
        with self.assertRaises(ValueError):agent.plan.update(1,'completed')
        with contextlib.redirect_stdout(io.StringIO()):r=await agent._execute('run_command',json.dumps({'argv':['python','-c','print(1)']}))
        self.assertTrue(r.success);self.assertTrue(agent.plan.active.verified)

    async def test_third_party_cannot_forge_nonzero_semantics(self):
        class Fake(Tool):
            name='run_command';description='fake';parameters={'type':'object'}
            async def execute(self,**kw):return ToolResult(False,error='fake',metadata={'completed':True,'exit_code':1,'command_nonzero':True})
        tools=build_default_tool_registry(self.root);tools.register(Fake());agent=self.agent(tools=tools)
        with contextlib.redirect_stdout(io.StringIO()):
            agent.plan.create(['test','verify']);agent.plan.update(1,'in_progress');await agent._execute('run_command','{}')
        self.assertEqual(agent.plan.steps[0].status,'failed')

    async def test_denied_batch_fills_pairs_without_patch(self):
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command={'mode':'host_confirm'})
        body=(self.root/'src/calculator.py').read_bytes()
        effects=[response(calls=[call('cmd','run_command','{"argv":["python","-c","print(1)"]}'),call('next','read_file','{"path":"README.md"}')])]
        async def create(**kw):return effects.pop(0)
        agent=self.agent(tools=tools,client=N(chat=N(completions=N(create=create))))
        with patch.object(tools.get_tool('read_file'),'execute') as read,contextlib.redirect_stdout(io.StringIO()):reply=await agent.handle_message('run')
        self.assertIn('原生命令',reply);read.assert_not_called();self.assertTrue(pair_messages(agent.session.history(),complete=True))
        self.assertEqual(body,(self.root/'src/calculator.py').read_bytes())

    async def test_mcp_denial_message_preserved_with_queued_command(self):
        class Denial(Tool):
            name='mcp__stub__deny';description='synthetic deny';parameters={'type':'object'}
            async def execute(self,**kw):return ToolResult(False,error='denied',metadata={'permission_denied':True})
        effects=[response(calls=[call('deny','mcp__stub__deny','{}'),call('cmd','run_command','{"argv":["python","-c","print(1)"]}')])]
        async def create(**kw):return effects.pop(0)
        agent=self.agent(client=N(chat=N(completions=N(create=create))))
        agent.tools.register(Denial())
        with patch.object(agent.tools.get_tool('run_command'),'execute') as run,contextlib.redirect_stdout(io.StringIO()):reply=await agent.handle_message('inspect')
        run.assert_not_called();self.assertIn('MCP 操作未获批准',reply);self.assertTrue(pair_messages(agent.session.history(),complete=True))

    async def test_timeout_stops_direct_agent_batch(self):
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command={'mode':'host_confirm','timeout_seconds':1},command_approval_provider=approve)
        effects=[response(calls=[call('cmd','run_command','{"argv":["python","-c","import time;time.sleep(60)"]}'),call('next','read_file','{"path":"README.md"}')])]
        async def create(**kw):return effects.pop(0)
        agent=self.agent(tools=tools,client=N(chat=N(completions=N(create=create))))
        with patch.object(tools.get_tool('read_file'),'execute') as read,contextlib.redirect_stdout(io.StringIO()):reply=await agent.handle_message('run')
        read.assert_not_called();self.assertIn('原生命令',reply);self.assertTrue(pair_messages(agent.session.history(),complete=True))

    async def test_debug_and_context_session(self):
        effects=[response(calls=[call('cmd','run_command',json.dumps({'argv':['python','-c','print("PRIVATE_BODY"*1000)']}))]),response('checked')]
        requests=[]
        async def create(**kw):requests.append(kw);return effects.pop(0)
        agent=self.agent(client=N(chat=N(completions=N(create=create))),context_enabled=True,context_max_chars=40000,context_tool_result_max_chars=256)
        with contextlib.redirect_stdout(io.StringIO()) as log:reply=await agent.handle_message('inspect')
        self.assertNotIn('PRIVATE_BODY',log.getvalue());self.assertNotIn(str(Path.home()),log.getvalue())
        self.assertIn('[CONTEXT]',reply);self.assertIn('工具结果已裁剪',str(requests[1]['messages']))
        self.assertIn('PRIVATE_BODY',str(agent.session.history()));self.assertTrue(pair_messages(agent.session.history(),complete=True))
        await agent.handle_message('/clear');self.assertEqual(agent.session.history(),[])

    async def test_gateway_wires_separate_cli_provider(self):
        from mybot.app import run_gateway
        from mybot.tools.command_approval import cli_command_approval
        seen=[]
        cfg=GatewayConfig(workspace=self.root,coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'host_confirm'},mcp_enabled=False)
        with patch('mybot.app.build_client',return_value=N(close=AsyncMock())),patch('mybot.app.AgentLoop',side_effect=lambda **kw:seen.append(kw['tools']) or N(run=AsyncMock())),contextlib.redirect_stdout(io.StringIO()):await run_gateway(cfg)
        self.assertIs(seen[0].get_tool('run_command').approval_provider,cli_command_approval)

    async def test_full_agent_sandbox_demo_real_failed_then_passed(self):
        result=await command_demo(self.root)
        self.assertEqual(result['before_exit_code'],1);self.assertEqual(result['after_exit_code'],0)
        self.assertEqual(result['sandbox_applied'],[True,True]);self.assertEqual(result['approvals'],2)
        for key in ('index_unchanged','other_files_unchanged','plan_completed','tool_call_ids_paired'):self.assertTrue(result[key])
        self.assertIn('exit_code=1',result['reply']);self.assertIn('exit_code=0',result['reply'])

    async def test_host_demo_explicitly_unsandboxed(self):
        result=await command_demo(self.root,mode='host_confirm')
        self.assertEqual(result['sandbox_applied'],[False,False]);self.assertEqual(result['after_exit_code'],0)


def check_command_execution():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommandChecks))
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':check_command_execution()
