"""Real local git/rg plus original AgentLoop. All writable operations are fixture preparation."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from types import SimpleNamespace as N
from unittest.mock import AsyncMock,patch
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from mybot.tools.repository import MAX_FILE_BYTES
from mybot.tools.readonly_process import run_readonly,ProcessResult,executable
from mybot.tools.git_tools import GitStatusTool
from mybot.agent import AgentLoop,ContextBuilder
from mybot.agent.context_manager import ContextBudgetError
from scripts.coding_repo_demo import make_demo,investigate,fingerprint
from scripts.check_session import call,response,assert_pairs


class RepositoryChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=make_demo(self.root/'repo')
        self.tools=build_default_tool_registry(self.repo,coding_enabled=True)
        self.git_exe,_=executable('git',self.repo)

    def git(self,*args):
        return subprocess.check_output([self.git_exe,'-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',*args],cwd=self.repo,
            env={'PATH':'/usr/bin:/bin','HOME':'/var/empty','GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1'},stderr=subprocess.PIPE)

    async def run_tool(self,name,**args):return await self.tools.execute(name,args)
    async def search(self,query,**args):return await self.run_tool('search_code',query=query,**args)
    def write(self,name,body):
        p=self.repo/name;p.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(body,bytes):p.write_bytes(body)
        else:p.write_text(body)
        return p

    async def test_default_registry_and_config(self):
        self.assertEqual([t.name for t in build_default_tool_registry(self.repo).iter_tools()],['read_file','list_files'])
        self.assertEqual(len(self.tools.iter_tools()),7)
        self.assertTrue(self.tools.permitted('repo_map'))
        self.assertFalse(GatewayConfig().coding_enabled)
        for bad in (1,0,None,[],{},'true'):
            with self.assertRaises(ValueError):GatewayConfig(coding_enabled=bad)
            with self.assertRaises(ValueError):build_default_tool_registry(self.repo,coding_enabled=bad)
        for value in ([],None,{'extra':True}):
            from scripts.check_lean_core_v2 import document
            from mybot.config import config_from_document
            doc = document(); doc['coding'] = value
            with self.assertRaises(ValueError): config_from_document(doc)
        for value in ({},{'enabled':False},{'enabled':True}):
            doc = document(); doc['coding'] = value
            self.assertEqual(config_from_document(doc).coding_enabled, value.get('enabled', False))

    async def test_strict_schemas(self):
        for name,args in [('search_code',{'query':'x','max_results':True}),('search_code',{'query':'x','case_sensitive':1}),
            ('search_code',{'query':'x','mode':'pcre2'}),('read_file_range',{'path':'README.md','start_line':True,'end_line':2}),
            ('git_status',{'repo_path':1}),('git_diff',{'scope':'HEAD'}),('git_diff',{'options':'--cached'})]:
            self.assertFalse((await self.run_tool(name,**args)).success,(name,args))
        for name in ('search_code','read_file_range','git_status','git_diff'):
            self.assertFalse((await self.run_tool(name,unknown=True)).success)
            self.assertFalse(self.tools.get_parameters(name)['additionalProperties'])
        for query in ('',' ','x'*257):self.assertFalse((await self.search(query)).success)

    async def test_literal_regex_case_glob_lines_columns(self):
        r=await self.search('def add',file_glob='*.py');self.assertTrue(r.success)
        hit=json.loads(r.output)['matches'][0]
        self.assertEqual((hit['path'],hit['line'],hit['column']),('src/calculator.py',1,1))
        self.assertFalse(json.loads((await self.search('DEF ADD')).output)['matches'])
        self.assertTrue(json.loads((await self.search('DEF ADD',case_sensitive=False)).output)['matches'])
        self.assertTrue(json.loads((await self.search(r'^def (add|total)\(',mode='regex')).output)['matches'])
        self.assertFalse(json.loads((await self.search('def add',file_glob='*.md')).output)['matches'])
        self.assertFalse((await self.search('(?=x)',mode='regex')).success)

    async def test_unicode_and_deterministic_order(self):
        self.write('空 格/中文.py','变量 = 1\nneedle\n');self.write('a.py','needle\n')
        a=await self.search('needle');b=await self.search('needle')
        self.assertEqual(a.output,b.output)
        self.assertEqual([m['line'] for m in json.loads(a.output)['matches']],[1,2])
        self.assertIn('空 格/中文.py',a.output)

    async def test_ignore_private_binary_dependencies(self):
        for name in ('ignored.py','.hidden.py','.env','node_modules/dep.py','.venv/dep.py',
                     'config/config.json','credentials.json','cache/data.py','weights.pt'):
            self.write(name,'needle')
        self.write('binary.py',b'needle\0PRIVATE');self.write('bad.py',b'needle\xff')
        self.write('good.py','needle')
        r=await self.search('needle',file_glob='*')
        self.assertEqual([m['path'] for m in json.loads(r.output)['matches']],['good.py'])
        for name in ('.env','config/config.json','node_modules/dep.py','credentials.json'):
            self.assertFalse((await self.search('needle',path=name)).success)
            self.assertFalse((await self.run_tool('read_file_range',path=name,start_line=1,end_line=2)).success)

    async def test_search_no_match_and_bounds(self):
        self.assertEqual(json.loads((await self.search('notfound')).output)['matches'],[])
        self.write('many.py','needle\n'*10000)
        r=await self.search('needle',max_results=5)
        self.assertTrue(r.success);self.assertTrue(r.metadata['truncated']);self.assertLessEqual(r.metadata['shown'],5)
        self.assertLessEqual(len(r.to_text()),16000)
        self.write('huge_line.py','needle'+'x'*50000)
        r=await self.search('needle',path='huge_line.py');self.assertTrue(r.metadata['truncated'])
        self.assertLessEqual(len(r.to_text()),16000)

    async def test_injection_and_missing_dependency(self):
        self.write('literal.py','$(touch HACKED)\n--no-ignore\n')
        self.assertTrue((await self.search('$(touch HACKED)')).success);self.assertFalse((self.repo/'HACKED').exists())
        self.assertTrue(json.loads((await self.search('--no-ignore')).output)['matches'])
        with patch('mybot.tools.readonly_process.executable',side_effect=FileNotFoundError('dependency_missing: rg')):
            r=await self.search('x');self.assertEqual(r.error,'dependency_missing')

    async def test_rg_config_and_fake_path_not_used(self):
        marker=self.repo/'RAN';fake=self.write('rg','#!/bin/sh\ntouch '+str(marker));fake.chmod(0o755)
        cfg=self.write('rg-config','--hidden\n--no-ignore\n')
        with patch.dict(os.environ,{'PATH':str(self.repo)+os.pathsep+os.environ['PATH'],'RIPGREP_CONFIG_PATH':str(cfg)}):
            self.write('.hidden.py','needle');r=await self.search('needle')
        self.assertFalse(marker.exists());self.assertFalse(json.loads(r.output)['matches'])
        self.assertNotEqual(executable('rg',self.repo)[0],str(fake))

    async def test_workspace_paths_and_symlinks(self):
        outside=self.root/'outside.py';outside.write_text('needle')
        (self.repo/'escape.py').symlink_to(outside)
        (self.repo/'internal.py').symlink_to(self.repo/'src/calculator.py')
        for path in ('../outside.py',str(outside),'escape.py'):
            self.assertFalse((await self.search('needle',path=path)).success)
            self.assertFalse((await self.run_tool('read_file_range',path=path,start_line=1,end_line=2)).success)
        self.assertTrue((await self.run_tool('read_file_range',path='internal.py',start_line=1,end_line=1)).success)
        self.assertTrue((await self.search('def add',path=str(self.repo/'src/calculator.py'))).success)
        self.assertFalse(json.loads((await self.search('needle')).output)['matches'])
        self.assertFalse((await self.search('x',path='absent')).success)

    async def test_range_inclusive_empty_and_outside(self):
        self.write('range.py','one\ntwo\nthree\n')
        r=await self.run_tool('read_file_range',path='range.py',start_line=2,end_line=3)
        self.assertEqual(r.output,'2 | two\n3 | three\n');self.assertIsNone(r.metadata['next_start_line'])
        r=await self.run_tool('read_file_range',path='range.py',start_line=1,end_line=1)
        self.assertEqual(r.output,'1 | one\n');self.assertEqual(r.metadata['next_start_line'],2)
        self.write('empty.py','');r=await self.run_tool('read_file_range',path='empty.py',start_line=1,end_line=1)
        self.assertTrue(r.success);self.assertEqual(r.metadata['total_lines'],0)
        for start,end in ((0,1),(2,1),(1,201),(100,110)):
            self.assertFalse((await self.run_tool('read_file_range',path='range.py',start_line=start,end_line=end)).success)

    async def test_range_encoding_types_and_resources(self):
        for name,body,error in [('bad.py',b'\xff','invalid_utf8'),('binary.py',b'a\0b','binary_file'),('large.py',b'x'*(MAX_FILE_BYTES+1),'file_too_large')]:
            self.write(name,body);r=await self.run_tool('read_file_range',path=name,start_line=1,end_line=1)
            self.assertEqual(r.error,error)
        self.assertFalse((await self.run_tool('read_file_range',path='src',start_line=1,end_line=1)).success)
        self.write('crlf.py',b'one\r\ntwo\r\n')
        r=await self.run_tool('read_file_range',path='crlf.py',start_line=1,end_line=2)
        self.assertEqual(r.output,'1 | one\r\n2 | two\r\n')
        self.write('long.py','x'*30000+'\nnext\n')
        r=await self.run_tool('read_file_range',path='long.py',start_line=1,end_line=2)
        self.assertTrue(r.metadata['truncated']);self.assertEqual(r.metadata['partial_line'],1)
        self.assertEqual(r.metadata['next_start_line'],1);self.assertLessEqual(len(r.to_text()),16000)

    async def test_range_many_lines_continuation(self):
        self.write('many.py','x'*200+'\n'+('y'*200+'\n')*199)
        r=await self.run_tool('read_file_range',path='many.py',start_line=1,end_line=200)
        self.assertTrue(r.metadata['truncated'])
        nxt=r.metadata['next_start_line'];self.assertGreater(nxt,1)
        r2=await self.run_tool('read_file_range',path='many.py',start_line=nxt,end_line=nxt)
        self.assertTrue(r2.output.startswith(str(nxt)+' | '))

    async def test_status_staged_unstaged_untracked_and_clean(self):
        r=await self.run_tool('git_status');d=json.loads(r.output);self.assertFalse(d['clean'])
        rows={m['path']:m for m in d['files']}
        self.assertTrue(rows['README.md']['staged']);self.assertTrue(rows['src/calculator.py']['unstaged'])
        self.assertTrue(rows['notes.txt']['untracked'])
        self.git('add','.');self.git('-c','user.name=Demo','-c','user.email=demo@example.invalid','commit','-qm','clean fixture')
        self.assertTrue(json.loads((await self.run_tool('git_status')).output)['clean'])

    async def test_status_delete_rename_unicode_and_newline(self):
        self.git('add','.');self.git('-c','user.name=Demo','-c','user.email=demo@example.invalid','commit','-qm','before rename');self.git('mv','README.md','重命 名\nnew.md');(self.repo/'tests/test_calculator.py').unlink()
        self.write('untracked\n"中文.txt','x')
        rows=json.loads((await self.run_tool('git_status')).output)['files']
        rename=next(r for r in rows if r.get('previous_path')=='README.md')
        self.assertEqual(rename['path'],'重命 名\nnew.md');self.assertEqual(rename['status'],'renamed')
        self.assertTrue(any(r['status']=='deleted' for r in rows))
        self.assertTrue(any(r['path']=='untracked\n"中文.txt' and r['untracked'] for r in rows))

    async def test_status_many_bounded_and_no_false_clean(self):
        for i in range(230):self.write(f'f{i:03}.txt','x')
        r=await self.run_tool('git_status');d=json.loads(r.output)
        self.assertTrue(d['truncated']);self.assertFalse(d['clean']);self.assertLessEqual(len(d['files']),200)
        with patch.object(GitStatusTool,'git_root',AsyncMock(return_value=self.repo)),patch.object(GitStatusTool,'git',AsyncMock(return_value=ProcessResult(-9,b'',True,False))):
            r=await self.run_tool('git_status');self.assertFalse(json.loads(r.output)['clean'])

    async def test_git_boundaries_nested_and_worktree(self):
        other=self.repo/'plain';other.mkdir()
        standalone=self.root/'plain';standalone.mkdir()
        tool=GitStatusTool(standalone);self.assertEqual((await tool.execute()).error,'not_git_repository')
        tool=GitStatusTool(self.repo/'src');self.assertEqual((await tool.execute()).error,'not_git_repository')
        self.assertFalse((await self.run_tool('git_status',repo_path='../plain')).success)
        # Legitimate linked worktree metadata is outside its own workspace, but its toplevel is inside.
        linked=self.root/'linked';self.git('worktree','add','--detach',str(linked),'HEAD')
        self.assertTrue((await GitStatusTool(linked).execute()).success)
        self.git('worktree','remove',str(linked))
        (self.repo/'nested').mkdir();self.git('-C','nested','init','-q')
        self.assertTrue((await self.run_tool('git_status',repo_path='nested')).success)

    async def test_git_diff_scopes_path_and_untracked(self):
        a=await self.run_tool('git_diff',scope='unstaged');b=await self.run_tool('git_diff',scope='staged')
        self.assertIn('+\n+# Unstaged investigation note.',a.output);self.assertNotIn('Staged teaching note.',a.output)
        self.assertIn('Staged teaching note.',b.output);self.assertNotIn('Unstaged investigation',b.output)
        self.assertEqual((await self.run_tool('git_diff',file_path='notes.txt')).output,'(no tracked diff)')
        self.assertEqual((await self.run_tool('git_diff',file_path='tests/test_calculator.py')).output,'(no tracked diff)')
        self.assertFalse((await self.run_tool('git_diff',file_path='../outside')).success)
        self.assertFalse((await self.run_tool('git_diff',file_path='.git/config')).success)

    async def test_literal_pathspec_unicode_and_sensitive_exclusion(self):
        self.write(':(glob)**','base\n');self.write('空 格.py','base\n');self.write('config/config.json','PRIVATE_BASE')
        self.git('add','.');self.git('-c','user.name=Demo','-c','user.email=demo@example.invalid','commit','-qm','fixture paths')
        self.write(':(glob)**','changed\n');self.write('空 格.py','changed\n');self.write('config/config.json','PRIVATE_NEW')
        r=await self.run_tool('git_diff',file_path=':(glob)**');self.assertIn(':(glob)**',r.output);self.assertNotIn('空 格.py',r.output)
        r=await self.run_tool('git_diff',file_path='空 格.py');self.assertIn('空 格.py',r.output)
        r=await self.run_tool('git_diff');self.assertNotIn('PRIVATE_',r.output);self.assertGreater(r.metadata['excluded_private_or_large_files'],0)
        self.assertFalse((await self.run_tool('git_diff',file_path='config/config.json')).success)

    async def test_diff_size_limit(self):
        with (self.repo/'src/calculator.py').open('a') as f:f.write('long line text '*10000+'\n'+'line\n'*500)
        r=await self.run_tool('git_diff');self.assertTrue(r.success);self.assertTrue(r.metadata['truncated'])
        self.assertLessEqual(len(r.to_text()),24000);self.assertLessEqual(r.metadata['shown_lines'],300)

    async def test_git_extensions_and_environment_never_execute(self):
        marker=self.repo/'EXECUTED';script=self.write('.hook.py',f'from pathlib import Path\nPath({str(marker)!r}).write_text("BAD")\n')
        command=f'{sys.executable} {script}'
        for key in ('core.fsmonitor','core.pager','diff.external','diff.evil.command','diff.evil.textconv',
                    'filter.evil.clean','filter.evil.smudge','filter.evil.process'):
            self.git('config',key,command)
        self.git('config','filter.evil.required','true')
        self.write('.gitattributes','*.py diff=evil filter=evil\n')
        before=(self.repo/'.git/index').read_bytes()
        with patch.dict(os.environ,{'GIT_DIR':str(self.root/'bad'),'GIT_WORK_TREE':str(self.root),'GIT_INDEX_FILE':str(self.root/'badindex'),
                                    'GIT_EXTERNAL_DIFF':command,'GIT_PAGER':command,'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'core.fsmonitor','GIT_CONFIG_VALUE_0':command}):
            a=await self.run_tool('git_status');b=await self.run_tool('git_diff')
        self.assertTrue(a.success);self.assertTrue(b.success)
        self.assertFalse(marker.exists());self.assertEqual((self.repo/'.git/index').read_bytes(),before)

    async def test_no_mutations_all_tools(self):
        before=fingerprint(self.repo);index=(self.repo/'.git/index').read_bytes()
        for name,args in [('search_code',{'query':'add'}),('read_file_range',{'path':'src/calculator.py','start_line':1,'end_line':8}),('git_status',{}),('git_diff',{}),('git_diff',{'scope':'staged'})]:
            self.assertTrue((await self.run_tool(name,**args)).success)
        self.assertEqual(before,fingerprint(self.repo));self.assertEqual(index,(self.repo/'.git/index').read_bytes())

    async def test_process_timeout_cancel_and_output_cap(self):
        pidfile=self.root/'pid'
        script=f'import os,time;open({str(pidfile)!r},"w").write(str(os.getpid()));time.sleep(60)'
        with patch('mybot.tools.readonly_process.executable',return_value=(sys.executable,'/usr/bin:/bin')):
            r=await run_readonly('rg',['-c',script],cwd=self.repo,workspace=self.repo,timeout=.2)
            self.assertTrue(r.timed_out)
            pid=int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            task=asyncio.create_task(run_readonly('rg',['-c',script],cwd=self.repo,workspace=self.repo))
            await asyncio.sleep(.1);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            pid=int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            r=await run_readonly('rg',['-c','import sys;sys.stdout.write("x"*1000000)'],cwd=self.repo,workspace=self.repo,stdout_limit=1000)
            self.assertTrue(r.truncated);self.assertLessEqual(len(r.stdout),1000)
            r=await run_readonly('git',['-c','import sys;sys.stderr.write("x"*1000000)'],cwd=self.repo,workspace=self.repo)
            self.assertTrue(r.truncated)

    async def test_agent_demo_real_files_and_tools(self):
        r=await investigate(self.repo)
        self.assertEqual(r['llm_requests'],5);self.assertIn('src/calculator.py:1 add',r['reply'])
        self.assertTrue(r['files_unchanged']);self.assertTrue(r['index_unchanged']);self.assertTrue(r['tool_call_ids_paired'])

    async def test_gateway_explicit_coding_flag(self):
        from mybot.app import run_gateway
        cfg=GatewayConfig(workspace=self.repo,coding_enabled=True,mcp_enabled=False,skills_enabled=False)
        seen=[]
        def agent_factory(**kw):seen.append(kw['tools']);return N(run=AsyncMock())
        with patch('mybot.app.init_workspace'),patch('mybot.app.build_client',return_value=N(close=AsyncMock())),patch('mybot.app.AgentLoop',side_effect=agent_factory):
            with contextlib.redirect_stdout(io.StringIO()):await run_gateway(cfg)
        self.assertTrue(seen[0].has_tool('search_code'))

    async def test_context_session_schema_and_debug_privacy(self):
        self.write('large.py','PRIVATE_BODY '*2000)
        requests=[]
        effects=[response(calls=[call('r','read_file_range','{"path":"large.py","start_line":1,"end_line":1}')]),response('investigated')]
        async def create(**kwargs):requests.append(kwargs);return effects.pop(0)
        cfg=GatewayConfig(workspace=self.repo,coding_enabled=True,skills_enabled=False,
                          context_enabled=True,context_tool_result_max_chars=256,context_max_chars=40000,debug=True)
        agent=AgentLoop(N(chat=N(completions=N(create=create))),cfg,self.tools,ContextBuilder(self.repo))
        with contextlib.redirect_stdout(io.StringIO()) as out:reply=await agent.handle_message('inspect')
        self.assertIn('[CONTEXT]',reply);self.assertIn('工具结果已裁剪',str(requests[1]['messages']))
        self.assertNotIn('PRIVATE_BODY',out.getvalue());self.assertNotIn('large.py',out.getvalue())
        original=next(m['content'] for m in agent.session.history() if m['role']=='tool')
        self.assertGreater(len(original),256);assert_pairs(self,agent.session.history())
        self.assertEqual(self.tools.get_parameters('read_file_range')['required'],['path','start_line','end_line'])
        await agent.handle_message('/clear');self.assertEqual(agent.session.history(),[])
        agent.config.context_token_budget['input_limit']=256
        with self.assertRaises(ContextBudgetError):await agent.handle_message('x')

    async def test_planning_and_mcp_discovery_native_visibility(self):
        effects=[response(calls=[call('p','create_plan','{"steps":["inspect status","read diff"]}')]),
                 response(calls=[call('s','update_plan','{"step":1,"status":"in_progress"}'),call('g','git_status','{}'),call('c','update_plan','{"step":1,"status":"completed"}')]),
                 response(calls=[call('s2','update_plan','{"step":2,"status":"in_progress"}'),call('d','git_diff','{}'),call('c2','update_plan','{"step":2,"status":"completed"}')]),response('investigated; not repaired')]
        requests=[]
        async def create(**kwargs):requests.append(kwargs);return effects.pop(0)
        cfg=GatewayConfig(workspace=self.repo,coding_enabled=True,skills_enabled=True,
                          mcp_discovery={'enabled':True,'routing_mode':'adaptive','selection_policy':'selective'})
        agent=AgentLoop(N(chat=N(completions=N(create=create))),cfg,self.tools,ContextBuilder(self.repo))
        with contextlib.redirect_stdout(io.StringIO()):await agent.handle_message('investigate repository')
        names={s['function']['name'] for s in requests[0]['tools']}
        self.assertTrue({'search_code','read_file_range','git_status','git_diff','search_mcp_tools','activate_mcp_tools','load_skill'}<=names)
        self.assertEqual(agent.routing_diagnostics['routing_strategy'],'no_mcp_tools')
        self.assertTrue(all(s.verified for s in agent.plan.steps));assert_pairs(self,agent.session.history())

    async def test_overall_timeout_and_search_exit_error(self):
        async def slow(*args,**kwargs):await asyncio.sleep(1)
        with patch('mybot.tools.repository.TIMEOUT_SECONDS',.02),patch('mybot.tools.search_code.SearchCodeTool._execute',slow):
            r=await self.search('x');self.assertFalse(r.success);self.assertTrue(r.metadata['timed_out'])
        outcomes=[ProcessResult(0,b'./src/calculator.py\0',False,False),ProcessResult(2,b'',False,False)]
        with patch('mybot.tools.search_code.run_readonly',AsyncMock(side_effect=outcomes)):
            self.assertEqual((await self.search('x')).error,'search_failed')

    async def test_git_both_columns_and_deleted_diff(self):
        self.write('README.md','staged then unstaged change\n')
        rows=json.loads((await self.run_tool('git_status')).output)['files']
        row=next(r for r in rows if r['path']=='README.md')
        self.assertTrue(row['staged']);self.assertTrue(row['unstaged'])
        (self.repo/'src/calculator.py').unlink()
        r=await self.run_tool('git_diff',file_path='src/calculator.py')
        self.assertTrue(r.success);self.assertIn('deleted file mode',r.output)

    async def test_git_declared_toplevel_outside_and_missing_git(self):
        outside=self.root/'outside';outside.mkdir()
        self.git('config','core.worktree',str(outside))
        r=await self.run_tool('git_status');self.assertEqual(r.error,'repository_outside_workspace')
        with patch('mybot.tools.readonly_process.executable',side_effect=FileNotFoundError('dependency_missing: git')):
            self.assertEqual((await self.run_tool('git_status')).error,'dependency_missing')

    async def test_ignored_explicit_file_still_not_searched(self):
        self.write('ignored.py','needle')
        r=await self.search('needle',path='ignored.py',file_glob='*.py')
        self.assertEqual(json.loads(r.output)['matches'],[])

    async def test_process_group_failure_falls_back_and_does_not_kill_other_process(self):
        other=await asyncio.create_subprocess_exec(sys.executable,'-c','import time;time.sleep(60)')
        try:
            with patch('mybot.tools.readonly_process.executable',return_value=(sys.executable,'/usr/bin:/bin')),patch('mybot.tools.readonly_process.os.killpg',side_effect=PermissionError()):
                r=await run_readonly('rg',['-c','import time;time.sleep(60)'],cwd=self.repo,workspace=self.repo,timeout=.05)
                self.assertTrue(r.timed_out)
            self.assertIsNone(other.returncode)
        finally:
            other.kill();await other.wait()

    async def test_gateway_coding_never_bootstraps_or_creates_workspace(self):
        from mybot.app import run_gateway
        cfg=GatewayConfig(workspace=self.repo,coding_enabled=True,mcp_enabled=False)
        with patch('mybot.app.init_workspace') as init,patch('mybot.app.build_client',return_value=N(close=AsyncMock())),patch('mybot.app.AgentLoop',return_value=N(run=AsyncMock())):
            with contextlib.redirect_stdout(io.StringIO()):await run_gateway(cfg)
            init.assert_not_called()
        cfg.workspace=self.root/'does-not-exist'
        with self.assertRaises(ValueError):await run_gateway(cfg)
        self.assertFalse(cfg.workspace.exists())

    async def test_missing_promisor_blob_does_not_launch_remote_helper(self):
        marker=self.repo/'FETCH_EXECUTED'
        script=self.write('.fetch.py',f'from pathlib import Path\nPath({str(marker)!r}).write_text("BAD")\n')
        oid=self.git('rev-parse','HEAD:src/calculator.py').decode().strip()
        (self.repo/'.git/objects'/oid[:2]/oid[2:]).unlink()
        self.git('config','extensions.partialClone','origin')
        self.git('config','remote.origin.promisor','true')
        self.git('config','remote.origin.url',f'ext::{sys.executable} {script}')
        self.git('config','protocol.ext.allow','always')
        result=await self.run_tool('git_diff')
        self.assertFalse(result.success);self.assertFalse(marker.exists())

    async def test_ambiguous_git_filter_names_fail_closed(self):
        marker=self.repo/'EXECUTED'
        script=self.write('.ambiguous-filter.py',f'from pathlib import Path\nPath({str(marker)!r}).write_text("BAD")\n')
        for driver in ('foo=bar','foo bar','foo"bar','fooKbar'):
            key='filter.'+driver+'.clean'
            self.git('config',key,f'{sys.executable} {script}')
            self.write('.gitattributes','*.py filter='+driver+'\n')
            for name in ('git_status','git_diff'):
                result=await self.run_tool(name)
                self.assertFalse(result.success)
                self.assertEqual(result.error,'unsafe_git_filter_configuration')
                self.assertFalse(marker.exists())
            self.git('config','--unset-all',key)


def check_repository_tools():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RepositoryChecks))
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':check_repository_tools()
