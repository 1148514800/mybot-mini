"""Real synthetic Git/journal/Undo safety tests. No live model or third-party MCP."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch, AsyncMock

from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.git_workflow import GitBaseline, GitWorkflowSettings
from mybot.agent.change_journal import ChangeJournal
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry, ToolResult
from mybot.tools.patch import ApplyPatchTool, sha
from mybot.tools.git_tools import GitStatusTool
from mybot.tools.undo import UndoService, UndoTransaction
from mybot.tools.undo_approval import undo_request, cli_undo_approval
from mybot.mcp_client.approval import ApprovalDecision
from mybot.evaluation.git_workflow import GitWorkflowClient, SpoofPatchTool, SpoofClient, evaluate
from mybot.evaluation.tool_agent import pair_messages
from scripts.coding_repo_demo import make_command_demo, fingerprint
from scripts.check_session import response
from scripts.check_autonomous_coding import call


async def approve(request): return ApprovalDecision.APPROVE


class GitWorkflowChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=make_command_demo(Path(self.tmp.name)/'repo')
        self.original=(self.root/'src/calculator.py').read_bytes()
        self.index=(self.root/'.git/index').read_bytes()
        self.before=fingerprint(self.root)

    async def asyncSetUp(self):
        self.baseline=await GitBaseline.capture(self.root)
        self.tool=ApplyPatchTool(self.root,patch_mode='write')
        self.bind()

    def bind(self, **limits):
        self.journal=ChangeJournal(self.baseline,self.tool,GitWorkflowSettings(enabled=True,undo_enabled=True,**limits))
        self.tool.observer=self.journal

    def git(self,*args,input=None):
        from mybot.tools.readonly_process import executable
        exe,_=executable('git',self.root)
        return subprocess.check_output([exe,'-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',*args],cwd=self.root,input=input,
            env={'PATH':'/usr/bin:/bin','HOME':'/var/empty','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'},stderr=subprocess.PIPE)

    def update(self,old='return left - right',new='return left + right',path='src/calculator.py'):
        return {'op':'update','path':path,'expected_sha256':sha((self.root/path).read_bytes()),'edits':[{'old_text':old,'new_text':new}]}

    async def apply(self,*changes,dry=False):
        return await self.tool.execute(dry_run=dry,changes=list(changes or [self.update()]))

    async def two_files(self):
        r=await self.apply(self.update(),{'op':'add','path':'tests/regression.py','content':'# New regression\n'})
        self.assertTrue(r.success,r.to_text())

    async def undo(self,provider=approve):return await UndoService(self.journal,provider).undo()

    def cfg(self, **kwargs):
        values=dict(context_token_budget={'input_limit':160000}, workspace=self.root,coding_enabled=True,coding_patch_mode='write',coding_command={'mode':'macos_readonly'},
            coding_autonomy={'enabled':True},coding_git_workflow={'enabled':True,'undo_enabled':True},
            skills_enabled=False,mcp_enabled=False,debug=False,max_react_steps=20)
        values.update(kwargs);return GatewayConfig(**values)

    async def agent(self,client=None,provider=approve, **kwargs):
        cfg=self.cfg(**kwargs)
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command=cfg.coding_command,command_approval_provider=approve)
        return AgentLoop(client or GitWorkflowClient(),cfg,tools,ContextBuilder(self.root),undo_approval_provider=provider)

    async def edited_agent(self, **kwargs):
        batches=iter([response(calls=[call('apply_patch',{'dry_run':False,'changes':[self.update()]})]),response('done'),response('done')])
        async def create(**kw):return next(batches)
        a=await self.agent(N(chat=N(completions=N(create=create))),**kwargs)
        with contextlib.redirect_stdout(io.StringIO()) as captured:await a.handle_message('Synthetic native edit')
        a._test_debug_log=captured.getvalue()
        return a

    async def test_split_index_refuses_undo_scope(self):
        self.git('update-index', '--split-index')
        baseline = await GitBaseline.capture(self.root)
        self.assertFalse(baseline.complete)
        self.assertIsNone(baseline.scope)
        self.assertTrue(baseline.files)

    async def test_v4_index_refuses_undo_scope(self):
        self.git('update-index', '--index-version', '4')
        baseline = await GitBaseline.capture(self.root)
        self.assertFalse(baseline.complete)
        self.assertIsNone(baseline.scope)

    def test_index_parser_rejects_corruption(self):
        from mybot.agent.git_workflow import validate_full_index
        import hashlib
        validate_full_index(self.index)
        for data in (b'', self.index[:-1], b'NOPE'+self.index[4:], self.index[:-20]+bytes(20)):
            with self.assertRaises(ValueError): validate_full_index(data)
        for body in (b'DIRC'+(9).to_bytes(4,'big')+bytes(4),
                     b'DIRC'+(2).to_bytes(4,'big')+(1).to_bytes(4,'big'),
                     b'DIRC'+(2).to_bytes(4,'big')+bytes(4)+b'link'+bytes(4)):
            with self.assertRaises(ValueError): validate_full_index(body+hashlib.sha1(body).digest())

    async def test_same_bytes_replacement_before_journal_commit_rejected(self):
        original = self.journal.after_success
        def replaced(items):
            path = self.root / items[0].path
            spare = path.with_name('external-replacement')
            spare.write_bytes(path.read_bytes())
            spare.chmod(stat.S_IMODE(path.stat().st_mode))
            os.replace(spare, path)
            return original(items)
        with patch.object(self.journal, 'after_success', replaced): result = await self.apply()
        self.assertFalse(result.success)
        self.assertEqual(result.metadata['status'], 'partial_failure_possible')
        self.assertFalse(self.journal.entries or self.journal.valid)

    async def test_cancel_releases_capsule(self):
        async def create(**kwargs): raise asyncio.CancelledError()
        agent = await self.agent(N(chat=N(completions=N(create=create))))
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(asyncio.CancelledError):
            await agent.handle_message('cancel fixture')
        self.assertIsNone(agent._git_capsule)
        self.assertIsNone(agent._active_journal)
        self.assertIsNone(agent.tools.get_tool('apply_patch').observer)

    async def test_exception_releases_capsule(self):
        async def create(**kwargs): raise RuntimeError('synthetic')
        agent = await self.agent(N(chat=N(completions=N(create=create))))
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            await agent.handle_message('exception fixture')
        self.assertIsNone(agent._git_capsule)
        self.assertIsNone(agent._active_journal)
        self.assertIsNone(agent.tools.get_tool('apply_patch').observer)

    def test_default_off(self):
        v=GatewayConfig().coding_git_workflow
        self.assertFalse(v['enabled'] or v['undo_enabled']);self.assertEqual(v['max_files'],24)

    def test_config_objects(self):
        for value in (None,False,[],{'extra':1}):
            with self.assertRaises(ValueError):self.cfg(coding_git_workflow=value)

    def test_config_types_and_bounds(self):
        for key in ('enabled','undo_enabled'):
            for val in (1,None,'yes'):
                with self.assertRaises(ValueError):self.cfg(coding_git_workflow={key:val})
        for key in ('max_files','max_journal_bytes','max_review_chars'):
            for val in (True,1.5,'2',None,0,-1,999999999):
                with self.subTest(key=key,val=val),self.assertRaises(ValueError):self.cfg(coding_git_workflow={key:val})

    def test_requires_coding(self):
        with self.assertRaises(ValueError):self.cfg(coding_enabled=False)

    def test_requires_write(self):
        with self.assertRaises(ValueError):self.cfg(coding_patch_mode='preview')

    def test_requires_autonomy(self):
        with self.assertRaises(ValueError):self.cfg(coding_autonomy={})

    def test_undo_explicit_enabled(self):
        with self.assertRaises(ValueError):self.cfg(coding_git_workflow={'undo_enabled':True})
        self.assertFalse(self.cfg(coding_git_workflow={'enabled':True}).coding_git_workflow['undo_enabled'])

    def test_undo_requires_readonly(self):
        with self.assertRaises(ValueError):self.cfg(coding_command={'mode':'host_confirm'})

    def test_undo_requires_mcp_disabled(self):
        with self.assertRaises(ValueError):self.cfg(mcp_enabled=True)

    def test_review_only_host_allowed(self):
        self.assertTrue(self.cfg(coding_command={'mode':'host_confirm'},coding_git_workflow={'enabled':True}).coding_git_workflow['enabled'])

    def test_config_loading_unknown(self):
        with self.assertRaises(ValueError):GatewayConfig(coding_git_workflow={'bad':1})

    async def test_no_schema_change(self):
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',command={'mode':'macos_readonly'})
        before=tools.get_definitions();a=await self.agent(coding_task_contract=False)
        after=[x for x in a.tools.get_definitions() if x['function']['name'] not in ('create_plan','update_plan')]
        self.assertEqual(before,after);self.assertFalse(a.tools.has_tool('undo_agent_changes'))
        self.assertFalse(a.tools.has_tool('write_file'))

    async def test_disabled_no_baseline_or_snapshots(self):
        async def create(**kw):return response('plain')
        a=await self.agent(N(chat=N(completions=N(create=create))),coding_git_workflow={})
        with patch.object(GitBaseline,'capture',side_effect=AssertionError('unexpected baseline')):
            reply=await a.handle_message('hello')
        self.assertIn('[CODING TASK HOST RESULT]',reply);self.assertNotIn('TASK CHANGE SUMMARY',reply)
        self.assertIsNone(a._git_capsule);self.assertIsNone(a.tools.get_tool('apply_patch').observer)

    async def test_baseline_dirty_states(self):
        b=self.baseline.summary();self.assertTrue(b['complete']);self.assertIn('README.md',b['staged'])
        self.assertIn('src/calculator.py',b['unstaged']);self.assertIn('notes.txt',b['untracked'])

    async def test_baseline_clean(self):
        self.git('add','.');self.git('-c','user.name=Synthetic','-c','user.email=test@example.invalid','commit','-qm','clean')
        b=await GitBaseline.capture(self.root);self.assertTrue(b.complete);self.assertEqual(b.files,[])

    async def test_head_correct(self):
        self.assertEqual(self.baseline.head,self.git('rev-parse','HEAD').decode().strip())

    async def test_index_bytes_preserved_baseline(self):
        await GitBaseline.capture(self.root);self.assertEqual(self.index,(self.root/'.git/index').read_bytes())
        self.assertTrue(self.baseline.unchanged())

    async def test_worktree_index_scope(self):
        dest=Path(self.tmp.name)/'linked'
        self.git('worktree','add','-b','codex/synthetic-linked',str(dest),'HEAD')
        b=await GitBaseline.capture(dest)
        self.assertTrue((dest/'.git').is_file());self.assertTrue(b.complete);self.assertTrue(b.unchanged())
        self.assertNotIn(str(b.scope.admin),json.dumps(b.summary()))
        self.assertNotEqual(b.scope.admin,dest/'.git')

    async def test_worktree_commondir_change_refuses_undo(self):
        dest = Path(self.tmp.name) / 'linked'
        self.git('worktree', 'add', '-b', 'codex/synthetic-links', str(dest), 'HEAD')
        baseline = await GitBaseline.capture(dest)
        self.assertTrue(baseline.unchanged())
        pointer = baseline.scope.admin / 'commondir'
        pointer.write_bytes(pointer.read_bytes() + b'\n')
        self.assertFalse(baseline.unchanged())

    async def test_non_git_workspace(self):
        outside=Path(self.tmp.name)/'plain';outside.mkdir()
        with self.assertRaises(ValueError):await GitBaseline.capture(outside)

    async def test_root_outside_workspace(self):
        with self.assertRaises(ValueError):await GitBaseline.capture(self.root/'src')

    async def test_status_truncated_incomplete(self):
        body={'clean':False,'files':[],'truncated':True}
        with patch.object(GitStatusTool,'execute',new=AsyncMock(return_value=ToolResult(True,json.dumps(body)))):
            b=await GitBaseline.capture(self.root)
        self.assertFalse(b.complete);self.assertTrue(b.truncated)

    async def test_real_status_over_limit(self):
        for i in range(205):(self.root/f'file-{i}.txt').write_text('x')
        b=await GitBaseline.capture(self.root);self.assertTrue(b.truncated);self.assertFalse(b.complete)

    async def test_unsafe_filter_incomplete(self):
        with (self.root/'.git/config').open('a') as f:f.write('\n[filter "bad=key"]\n clean = false\n')
        b=await GitBaseline.capture(self.root);self.assertFalse(b.complete)

    async def test_index_unavailable(self):
        (self.root/'.git/index').unlink()
        b=await GitBaseline.capture(self.root)
        self.assertFalse(b.complete);self.assertEqual(b.summary()['index_fingerprint'],'unavailable')
        self.assertTrue(b.files)

    async def test_index_symlink_refused(self):
        p=self.root/'.git/index';data=p.read_bytes();p.unlink();other=Path(self.tmp.name)/'private-index';other.write_bytes(data);p.symlink_to(other)
        b=await GitBaseline.capture(self.root);self.assertFalse(b.complete)

    async def test_incomplete_blocks_before_publish(self):
        self.baseline.complete=False
        before=fingerprint(self.root)
        r=await self.apply()
        self.assertEqual(r.error,'journal_baseline_incomplete_or_changed');self.assertEqual(before,fingerprint(self.root))

    async def test_rename_baseline(self):
        (self.root/'README.md').write_bytes(self.git('show','HEAD:README.md'))
        self.git('add','README.md')
        self.git('mv','README.md','RENAMED.md')
        b=await GitBaseline.capture(self.root)
        self.assertTrue(any(f.get('previous_path')=='README.md' for f in b.files))

    async def test_merge_conflict_baseline(self):
        blob=self.git('rev-parse','HEAD:src/calculator.py').decode().strip()
        payload=('0 '+'0'*40+'\tsrc/calculator.py\n'+''.join(f'100644 {blob} {i}\tsrc/calculator.py\n' for i in (1,2,3))).encode()
        self.git('update-index','--index-info',input=payload)
        b=await GitBaseline.capture(self.root);self.assertFalse(b.complete);self.assertIn('src/calculator.py',b.summary()['conflicts'])

    async def test_dry_run_no_journal(self):
        self.assertTrue((await self.apply(dry=True)).success);self.assertEqual(self.journal.entries,{})

    async def test_stale_no_journal(self):
        args=self.update();args['expected_sha256']='0'*64
        self.assertFalse((await self.apply(args)).success);self.assertEqual(self.journal.entries,{})

    async def test_success_exact_original_and_final(self):
        self.assertTrue((await self.apply()).success)
        e=self.journal.entries['src/calculator.py']
        self.assertEqual(e.original_bytes,self.original);self.assertIn(b'# Unstaged investigation note.',e.original_bytes)
        self.assertEqual(e.final_bytes,(self.root/e.relative_path).read_bytes());self.assertEqual(e.final_sha256,sha(e.final_bytes))

    async def test_multiple_patches_merge(self):
        await self.apply();await self.apply(self.update('return left + right','return (left + right)'))
        e=self.journal.entries['src/calculator.py'];self.assertEqual(e.original_bytes,self.original)
        self.assertEqual((e.first_patch_revision,e.last_patch_revision),(1,2));self.assertEqual(self.journal.revision,2)

    async def test_add_then_update_stays_added(self):
        await self.apply({'op':'add','path':'tests/new.py','content':'a = 1\n'})
        await self.apply(self.update('a = 1','a = 2',path='tests/new.py'))
        e=self.journal.entries['tests/new.py'];self.assertFalse(e.original_existed);self.assertEqual(e.original_bytes,b'')
        self.assertEqual((await self.undo())['undo_status'],'undo_completed');self.assertFalse((self.root/'tests/new.py').exists())

    async def test_multi_file_snapshots(self):
        await self.two_files();self.assertEqual(len(self.journal.entries),2);self.assertEqual(self.journal.revision,1)

    async def test_budget_bytes_before_write(self):
        self.bind(max_journal_bytes=1);before=fingerprint(self.root)
        r=await self.apply();self.assertEqual(r.error,'journal_budget_exceeded')
        self.assertEqual(before,fingerprint(self.root));self.assertEqual(self.journal.entries,{})

    async def test_budget_files_before_any_write(self):
        self.bind(max_files=1);before=fingerprint(self.root)
        r=await self.apply(self.update(),{'op':'add','path':'tests/new.py','content':'x\n'})
        self.assertEqual(r.error,'journal_budget_exceeded');self.assertEqual(before,fingerprint(self.root))

    async def test_budget_peak_reservation(self):
        n=len(self.original);self.bind(max_journal_bytes=3*n)
        self.assertTrue((await self.apply()).success)
        r=await self.apply(self.update('return left + right','return (left + right)'))
        self.assertEqual(r.error,'journal_budget_exceeded')
        self.assertEqual(self.journal.entries['src/calculator.py'].last_patch_revision,1)

    async def test_observer_final_failure_not_owned(self):
        with patch.object(self.tool,'_publish',side_effect=OSError('synthetic')):r=await self.apply()
        self.assertFalse(r.success);self.assertEqual(self.journal.entries,{})
        self.assertEqual((self.root/'src/calculator.py').read_bytes(),self.original)

    async def test_journal_commit_failure_uncertain(self):
        with patch.object(self.journal,'after_success',side_effect=RuntimeError('private data')):r=await self.apply()
        self.assertFalse(r.success);self.assertEqual(r.metadata['status'],'partial_failure_possible')
        self.assertFalse(self.journal.valid);self.assertEqual(self.journal.entries,{})
        self.assertNotIn('private data',r.to_text())

    async def test_cleanup_failure_not_committed(self):
        original=os.unlink
        def fail(name,*a,**kw):
            if str(name).startswith('.mybot-patch-'):raise OSError('cleanup')
            return original(name,*a,**kw)
        with patch('mybot.tools.patch.os.unlink',side_effect=fail):r=await self.apply()
        self.assertFalse(r.success);self.assertFalse(self.journal.valid);self.assertEqual(self.journal.entries,{})

    async def test_external_between_patches_rejected(self):
        await self.apply();p=self.root/'src/calculator.py';p.write_bytes(p.read_bytes()+b'\n# User new work\n')
        before=p.read_bytes();r=await self.apply(self.update('return left + right','return (left + right)'))
        self.assertEqual(r.error,'journal_external_conflict');self.assertEqual(before,p.read_bytes())

    async def test_no_snapshot_in_metadata(self):
        r=await self.apply();text=json.dumps(r.metadata)
        self.assertNotIn('original_bytes',text);self.assertNotIn('Unstaged investigation note',text)
        self.assertNotIn('return left - right',repr(self.journal))

    async def test_agent_diff_not_user_diff(self):
        await self.apply();review=self.journal.review()
        self.assertIn('-    return left - right',review);self.assertIn('+    return left + right',review)
        self.assertNotIn('+# Unstaged investigation note.',review)
        self.assertNotIn('+# Synthetic calculator',review)

    async def test_diff_cumulative_not_last_only(self):
        await self.apply();await self.apply(self.update('return left + right','return (left + right)'))
        text=self.journal.review();self.assertIn('-    return left - right',text);self.assertIn('+    return (left + right)',text)

    async def test_added_diff_dev_null(self):
        await self.two_files();self.assertIn('--- /dev/null',self.journal.review())

    async def test_review_truncation(self):
        self.bind(max_review_chars=256);await self.two_files();text=self.journal.review()
        self.assertLessEqual(len(text),256);self.assertIn('truncat',text)

    async def test_review_stale(self):
        await self.apply();p=self.root/'src/calculator.py';p.write_bytes(p.read_bytes()+b'# external\n')
        self.assertIn('stale_review',self.journal.review());self.assertFalse(self.journal.can_undo())

    async def test_summary_has_no_diff(self):
        await self.apply();self.assertNotIn('return left',self.journal.summary_text())

    async def test_no_capsule_undo(self):
        a=await self.agent();self.assertIn('undo_unavailable',await a.handle_message('/undo'))

    async def test_undo_disabled(self):
        self.journal.settings=GitWorkflowSettings(enabled=True)
        await self.apply();self.assertEqual((await self.undo())['undo_status'],'undo_unavailable')

    async def test_no_provider_denies(self):
        await self.apply();before=fingerprint(self.root)
        self.assertEqual((await self.undo(None))['undo_status'],'undo_denied');self.assertEqual(before,fingerprint(self.root))

    async def test_bool_approval_rejected(self):
        await self.apply()
        async def boolean(req):return True
        self.assertEqual((await self.undo(boolean))['undo_status'],'undo_denied')

    async def test_provider_exception_denies(self):
        await self.apply()
        async def fail(req):raise RuntimeError('private')
        r=await self.undo(fail);self.assertEqual(r['undo_status'],'undo_denied');self.assertNotIn('private',str(r))

    async def test_noninteractive_cli_denies(self):
        await self.apply();req=undo_request(self.journal.entries.values())
        with patch('sys.stdin.isatty',return_value=False):self.assertIs(await cli_undo_approval(req),ApprovalDecision.DENY)

    async def test_cli_exact_yes_and_full_scope(self):
        await self.two_files();req=undo_request(self.journal.entries.values())
        for answer,expected in [('yes',ApprovalDecision.APPROVE),('Yes',ApprovalDecision.DENY),('y',ApprovalDecision.DENY)]:
            with contextlib.redirect_stdout(io.StringIO()) as log,patch('sys.stdin.isatty',return_value=True),patch('sys.stdout.isatty',return_value=True),patch('builtins.input',return_value=answer):
                self.assertIs(await cli_undo_approval(req),expected)
            self.assertIn('src/calculator.py',log.getvalue());self.assertIn('tests/regression.py',log.getvalue())
            self.assertNotIn('return left',log.getvalue())

    async def test_frozen_approval_request(self):
        await self.apply();req=undo_request(self.journal.entries.values())
        from dataclasses import FrozenInstanceError
        with self.assertRaises(FrozenInstanceError):req.files=()

    async def test_approval_race_recheck(self):
        await self.two_files()
        async def race(req):
            p=self.root/'src/calculator.py';p.write_bytes(p.read_bytes()+b'# concurrent\n');return ApprovalDecision.APPROVE
        r=await self.undo(race);self.assertEqual(r['undo_status'],'undo_conflict')
        self.assertTrue((self.root/'tests/regression.py').exists())

    async def test_single_update_undo(self):
        await self.apply();r=await self.undo();self.assertEqual(r['undo_status'],'undo_completed')
        self.assertEqual((self.root/'src/calculator.py').read_bytes(),self.original)

    async def test_multiple_updates_undo_to_initial(self):
        await self.apply();await self.apply(self.update('return left + right','return (left + right)'))
        r=await self.undo();self.assertEqual(r['undo_status'],'undo_completed');self.assertEqual((self.root/'src/calculator.py').read_bytes(),self.original)

    async def test_multi_file_and_added_undo(self):
        await self.two_files();r=await self.undo();self.assertEqual(r['undo_status'],'undo_completed')
        self.assertFalse((self.root/'tests/regression.py').exists());self.assertEqual((self.root/'src/calculator.py').read_bytes(),self.original)

    async def test_dirty_comment_preserved(self):
        await self.two_files();await self.undo()
        self.assertIn(b'# Unstaged investigation note.',(self.root/'src/calculator.py').read_bytes())

    async def test_readme_and_notes_preserved(self):
        await self.two_files();await self.undo();after=fingerprint(self.root)
        self.assertEqual(after['README.md'],self.before['README.md']);self.assertEqual(after['notes.txt'],self.before['notes.txt'])

    async def test_index_byte_preserved_undo(self):
        await self.two_files();r=await self.undo();self.assertTrue(r['index_unchanged'])
        self.assertEqual(self.index,(self.root/'.git/index').read_bytes())

    async def test_external_edit_whole_batch_refused(self):
        await self.two_files();p=self.root/'src/calculator.py';p.write_bytes(p.read_bytes()+b'# user\n');before=fingerprint(self.root)
        r=await self.undo();self.assertEqual(r['undo_status'],'undo_conflict');self.assertEqual(before,fingerprint(self.root))

    async def test_same_bytes_replaced_inode_conflict(self):
        await self.two_files();p=self.root/'src/calculator.py';body=p.read_bytes();p.unlink();p.write_bytes(body)
        self.assertEqual((await self.undo())['undo_status'],'undo_conflict');self.assertTrue((self.root/'tests/regression.py').exists())

    async def test_added_file_external_edit_conflict(self):
        await self.two_files();(self.root/'tests/regression.py').write_text('# user took ownership\n')
        self.assertEqual((await self.undo())['undo_status'],'undo_conflict')

    async def test_added_file_staged_conflict(self):
        await self.two_files();self.git('add','tests/regression.py')
        self.assertEqual((await self.undo())['undo_status'],'undo_conflict');self.assertTrue((self.root/'tests/regression.py').exists())

    async def test_symlink_escape_conflict(self):
        await self.two_files();p=self.root/'src/calculator.py';outside=Path(self.tmp.name)/'outside';outside.write_bytes(p.read_bytes());p.unlink();p.symlink_to(outside)
        r=await self.undo();self.assertEqual(r['undo_status'],'undo_conflict');self.assertTrue((self.root/'tests/regression.py').exists())

    async def test_hardlink_conflict(self):
        await self.two_files();os.link(self.root/'src/calculator.py',Path(self.tmp.name)/'hardlink')
        self.assertEqual((await self.undo())['undo_status'],'undo_conflict')

    async def test_mode_change_conflict(self):
        await self.apply();(self.root/'src/calculator.py').chmod(0o700)
        self.assertEqual((await self.undo())['undo_status'],'undo_conflict')

    async def test_index_change_conflict(self):
        await self.two_files();self.git('add','src/calculator.py');index=(self.root/'.git/index').read_bytes()
        self.assertEqual((await self.undo())['undo_status'],'undo_conflict');self.assertEqual(index,(self.root/'.git/index').read_bytes())

    async def test_head_change_conflict(self):
        await self.two_files();self.git('-c','user.name=Synthetic','-c','user.email=test@example.invalid','commit','--allow-empty','-qm','external commit')
        self.assertEqual((await self.undo())['undo_status'],'undo_conflict')

    async def test_unrelated_change_allowed_and_preserved(self):
        await self.two_files();(self.root/'notes.txt').write_text('New user content\n')
        self.assertEqual((await self.undo())['undo_status'],'undo_completed');self.assertEqual((self.root/'notes.txt').read_text(),'New user content\n')

    async def test_publish_failure_rolls_back(self):
        await self.two_files();before=fingerprint(self.root);service=UndoService(self.journal,approve);original=service.transaction._publish
        def fail(item):
            if item.path=='tests/regression.py':raise OSError('publish failure')
            original(item)
        with patch.object(service.transaction,'_publish',side_effect=fail):r=await service.undo()
        self.assertEqual(r['undo_status'],'undo_rolled_back');self.assertEqual(before,fingerprint(self.root))

    async def test_remove_then_failure_restores_added_file(self):
        await self.two_files();before=fingerprint(self.root);service=UndoService(self.journal,approve);original=service.transaction._recheck
        failed=False
        def fail(item,*,published=False):
            nonlocal failed
            original(item,published=published)
            if item.op=='remove' and published and not failed:failed=True;raise OSError('after delete')
        with patch.object(service.transaction,'_recheck',side_effect=fail):r=await service.undo()
        self.assertEqual(r['undo_status'],'undo_rolled_back');self.assertEqual(before,fingerprint(self.root))

    async def test_concurrent_publish_never_overwrites_user(self):
        await self.two_files();service=UndoService(self.journal,approve);original=service.transaction._publish
        user=b'User concurrently replaced file\n'
        def race(item):
            original(item)
            if item.path=='src/calculator.py':(self.root/item.path).write_bytes(user)
        with patch.object(service.transaction,'_publish',side_effect=race):r=await service.undo()
        self.assertEqual(r['undo_status'],'undo_partial_failure_possible')
        self.assertEqual((self.root/'src/calculator.py').read_bytes(),user)
        self.assertTrue((self.root/'tests/regression.py').exists())

    async def test_consumed_cannot_repeat(self):
        await self.two_files();await self.undo();self.assertEqual(self.journal.entries,{})
        self.assertEqual((await self.undo())['undo_status'],'undo_unavailable')

    async def test_no_git_writes_in_undo(self):
        await self.two_files()
        with patch.object(self.baseline.tool,'git',side_effect=AssertionError('Git called during Undo')):
            self.assertEqual((await self.undo())['undo_status'],'undo_completed')

    async def test_changes_no_llm_and_no_writes(self):
        a=await self.edited_agent();before=fingerprint(self.root)
        with patch.object(a.client.chat.completions,'create',side_effect=AssertionError('LLM called')):
            text=await a.handle_message('/changes')
        self.assertIn('Agent-only Diff',text);self.assertEqual(before,fingerprint(self.root))

    async def test_undo_no_llm(self):
        a=await self.edited_agent()
        with patch.object(a.client.chat.completions,'create',side_effect=AssertionError('LLM called')):
            text=await a.handle_message('/undo')
        self.assertIn('undo_completed',text);self.assertTrue(pair_messages(a.session.history(),complete=True))

    async def test_clear_discards_private_images(self):
        a=await self.edited_agent();j=a._git_capsule;before=fingerprint(self.root)
        await a.handle_message('/clear');self.assertEqual(j.entries,{});self.assertIsNone(a._git_capsule)
        self.assertEqual(before,fingerprint(self.root));self.assertIn('undo_unavailable',await a.handle_message('/undo'))

    async def test_new_task_discards_old_capsule(self):
        a=await self.edited_agent();j=a._git_capsule
        async def create(**kw):return response('investigation only')
        a.client.chat.completions.create=create
        await a.handle_message('new task');self.assertFalse(j.active);self.assertEqual(j.entries,{})
        self.assertFalse(a._git_capsule.entries)

    async def test_restart_does_not_restore_capsule(self):
        a=await self.edited_agent();b=AgentLoop(a.client,a.config,a.tools,ContextBuilder(self.root),session=a.session)
        self.assertIsNone(b._git_capsule);self.assertIn('undo_unavailable',await b.handle_message('/undo'))

    async def test_snapshot_not_session_payload(self):
        a=await self.edited_agent();history=json.dumps(a.session.export_turns())
        self.assertNotIn('original_bytes',history);self.assertNotIn('final_bytes',history)
        # Existing Patch diff protocol can contain source excerpts; no full Journal serialization.
        self.assertNotIn('final_version',history)

    async def test_request_cannot_survive_clear(self):
        a=await self.edited_agent()
        async def clear(req):await a.handle_message('/clear');return ApprovalDecision.APPROVE
        a._undo_provider=clear;before=fingerprint(self.root);result=await a.handle_message('/undo')
        self.assertNotIn('"undo_status": "undo_completed"',result);self.assertEqual(before,fingerprint(self.root))

    async def test_unknown_registry_refused_in_strict_mode(self):
        a=await self.agent();a.tools.register(SpoofPatchTool())
        with patch.object(a.client.chat.completions,'create',side_effect=AssertionError('model must not run')):
            r=await a.handle_message('task')
        self.assertIn('blocked',r);self.assertIsNone(a._git_capsule)

    async def test_spoof_metadata_not_owned_review_only(self):
        a=await self.agent(SpoofClient(),coding_git_workflow={'enabled':True})
        a.tools.register(SpoofPatchTool(), capability='external_side_effect');await a.handle_message('task')
        self.assertEqual(a._git_capsule.entries,{});self.assertEqual(a.last_coding_report['state'],'completed_without_changes')

    async def test_host_review_only_marks_external(self):
        a=await self.edited_agent(coding_command={'mode':'host_confirm'},coding_git_workflow={'enabled':True})
        self.assertTrue(a._git_capsule.summary()['external_side_effects_possible']);self.assertFalse(a._git_capsule.can_undo())

    async def test_undo_invalidates_verified(self):
        a=await self.agent();await a.handle_message('repair calculator')
        self.assertEqual(a.last_coding_report['state'],'verified')
        await a.handle_message('/undo')
        self.assertEqual(a.last_coding_report['verification'],'invalid');self.assertEqual(a.last_coding_report['undo_status'],'undo_completed')
        self.assertIsNone(a.coding_controller)

    async def test_changes_external_edit_invalidates_report(self):
        a=await self.agent();await a.handle_message('repair calculator')
        p=self.root/'src/calculator.py';p.write_bytes(p.read_bytes()+b'# external\n')
        r=await a.handle_message('/changes');self.assertIn('stale_review',r)
        self.assertEqual(a.last_coding_report['verification'],'invalid')

    async def test_debug_does_not_print_snapshots(self):
        a=await self.edited_agent(debug=True)
        self.assertIn('[CALL]',a._test_debug_log);self.assertIn('[RESULT]',a._test_debug_log)
        self.assertNotIn('return left',a._test_debug_log);self.assertNotIn('Unstaged investigation note',a._test_debug_log)

    async def test_gateway_undo_provider(self):
        from mybot.app import run_gateway
        from mybot.tools.undo_approval import cli_undo_approval
        with patch('mybot.app.build_client',return_value=N(close=AsyncMock())),patch('mybot.app.AgentLoop',return_value=N(run=AsyncMock())) as loop,contextlib.redirect_stdout(io.StringIO()):
            await run_gateway(self.cfg())
        self.assertIs(loop.call_args.kwargs['undo_approval_provider'],cli_undo_approval)

    async def test_evaluation_detects_unexpected_extra_file(self):
        from mybot.evaluation.git_workflow import run_case, CASES
        spec = next(c for c in json.loads(CASES.read_text()) if c['id'] == 'dirty')
        original = UndoTransaction._publish
        def unexpected(transaction, item):
            original(transaction, item)
            (transaction.workspace / 'unexpected-extra.txt').write_text('Unexpected external write')
        with patch.object(UndoTransaction, '_publish', unexpected): result = await run_case(spec)
        self.assertEqual(result['unintended_file_changes_count'], 1)
        self.assertFalse(result['task_success'])

    async def test_complete_evaluation(self):
        report=await evaluate();bad=[(c['case'],c['undo_status']) for c in report['cases'] if not c['task_success']]
        self.assertEqual(bad,[]);self.assertEqual(report['false_owned_changes_count'],0)
        self.assertEqual(report['unintended_file_changes_count'],0);self.assertEqual(report['index_preserved_count'],report['total_cases'])
        self.assertTrue(all(c['cli_used_no_llm'] and c['tool_call_ids_paired'] for c in report['cases']))
        self.assertIsNone(report['actual_tokens']);self.assertIsNone(report['actual_cost'])


def check_git_workflow():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GitWorkflowChecks))
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_git_workflow()
