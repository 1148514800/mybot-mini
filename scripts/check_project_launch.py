"""Small project-launch tests. Private temp repos, Mock models, no real Provider."""
import asyncio
import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

import httpx
from mybot.config import GatewayConfig
from mybot.web.launch import prepare_launch, read_config, LaunchError, inspect_project
from mybot.web.server import create_app
from mybot.web.__main__ import main
from scripts.check_session import response, call
from scripts.coding_workflow_canary_v1.fixture import git


class LaunchChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.repo=self.root/'project';self.repo.mkdir()
        git(self.repo,'init','-q','--initial-branch=example');git(self.repo,'config','user.name','Offline');git(self.repo,'config','user.email','offline@invalid.local')
        (self.repo/'example.py').write_text('VALUE = 42\n');git(self.repo,'add','example.py');git(self.repo,'commit','-qm','fixture')
        self.config=self.root/'config.json';self.document=dict(llm=dict(provider='second',providers={n:dict(api_key=n+'-private-key',base_url='https://'+n+'.invalid/v1',model=n+'-model') for n in ('first','second','third')}),workspace=dict(path=str(self.repo)))
        self.config.write_text(json.dumps(self.document));self.cfg=GatewayConfig(workspace=self.repo,provider='second',api_key='second-private-key',model='second-model',base_url='https://second.invalid/v1',skills_enabled=False,context_enabled=False,session_persist=False)

    def prepare(self,workspace=None,cfg=None):
        return prepare_launch(workspace,config_path=self.config,config_factory=lambda:cfg or self.cfg)

    def test_default_workspace_branch_and_order(self):
        before=self.images();cfg,project,r=self.prepare();self.assertEqual(cfg.workspace,self.repo);self.assertEqual(project['branch'],'example');self.assertEqual(r['provider_order'],['second','third','first']);self.assertFalse(r['coding']);self.assertEqual(r['run_command'],'off');self.assertEqual(self.images(),before)

    def images(self):return {str(p.relative_to(self.repo)):p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}

    def test_absolute_override_keeps_permissions_and_original_config(self):
        other=self.root/'other';git(self.repo,'clone','-q',str(self.repo),str(other));before=self.config.read_bytes()
        cfg,_,r=self.prepare(str(other));self.assertEqual(cfg.workspace,other);self.assertEqual(self.cfg.workspace,self.repo);self.assertFalse(cfg.coding_enabled);self.assertEqual(cfg.coding_patch_mode,'off');self.assertEqual(self.config.read_bytes(),before)

    def test_native_coding_write_permissions_preserved(self):
        cfg=replace(self.cfg,coding_enabled=True,coding_patch_mode='write',coding_preview_receipt=True,coding_command={'mode':'macos_readonly'},coding_autonomy={'enabled':True},coding_git_workflow={'enabled':True})
        loaded,_,r=self.prepare(str(self.repo),cfg);self.assertTrue(loaded.coding_enabled);self.assertEqual(r['patch_mode'],'write');self.assertTrue(r['command_requires_approval']);self.assertTrue(r['preview_receipt'])

    def test_nonexistent_path_not_created(self):
        p=self.root/'missing'
        with self.assertRaises(LaunchError) as caught:self.prepare(str(p))
        self.assertEqual(caught.exception.result['error_type'],'WORKSPACE_NOT_FOUND');self.assertFalse(p.exists())

    def test_relative_file_non_git_and_subdirectory_rejected(self):
        plain=self.root/'plain';plain.mkdir();sub=self.repo/'child';sub.mkdir()
        for p in ('relative',str(self.repo/'example.py'),str(plain),str(sub),'bad\x00path'):
            with self.subTest(path=p),self.assertRaises(LaunchError):self.prepare(p)

    def test_inaccessible_workspace(self):
        with patch('mybot.web.launch.os.access',return_value=False),self.assertRaises(LaunchError):self.prepare()

    def test_symlink_normalizes_to_actual_root(self):
        alias=self.root/'alias';alias.symlink_to(self.repo,target_is_directory=True)
        loaded,_,_=self.prepare(str(alias));self.assertEqual(loaded.workspace,self.repo)

    def test_linked_git_worktree_supported(self):
        other=self.root/'linked';git(self.repo,'worktree','add','-q','-b','linked',str(other))
        _,project,_=self.prepare(str(other));self.assertEqual(project['branch'],'linked')

    def test_detached_and_unborn_repositories(self):
        git(self.repo,'checkout','-q','--detach');self.assertTrue(self.prepare()[1]['detached'])
        empty=self.root/'empty';empty.mkdir();git(empty,'init','-q','--initial-branch=empty')
        self.assertTrue(self.prepare(str(empty))[1]['unborn'])

    def test_corrupt_index_rejected_without_repair(self):
        p=self.repo/'.git/index';p.write_bytes(b'broken-index')
        with self.assertRaises(LaunchError):self.prepare()
        self.assertEqual(p.read_bytes(),b'broken-index')

    def test_no_repository_filter_execution(self):
        marker=self.root/'filter-ran';git(self.repo,'config','filter.evil.clean','touch '+str(marker))
        (self.repo/'.gitattributes').write_text('*.py filter=evil\n');(self.repo/'example.py').write_text('VALUE = 43\n')
        before=self.images();self.prepare();self.assertFalse(marker.exists());self.assertEqual(self.images(),before)

    def test_json_error_fixed_type_line_column_and_no_credentials(self):
        self.config.write_text('{\n"api_key": "private-value",\n invalid\n}')
        factory=Mock()
        with self.assertRaises(LaunchError) as caught:prepare_launch(config_path=self.config,config_factory=factory)
        r=caught.exception.result;self.assertEqual((r['error_type'],r['line'],r['column']),('CONFIG_JSON_INVALID',3,2));self.assertNotIn('private-value',str(r));factory.assert_not_called()

    def test_nonstandard_json_constant_has_line_column(self):
        self.config.write_text('{\n"description":"NaN",\n"timeout": NaN\n}')
        with self.assertRaises(LaunchError) as caught:read_config(self.config)
        self.assertEqual(caught.exception.result,dict(ok=False,error_type='CONFIG_JSON_INVALID',line=3,column=12))

    def test_lazy_public_api_preserves_original_classes(self):
        from mybot import run_gateway
        from mybot.app import run_gateway as original
        from mybot.agent import AgentLoop
        from mybot.agent.loop import AgentLoop as original_loop
        self.assertIs(run_gateway,original);self.assertIs(AgentLoop,original_loop)

    def test_invalid_providers_and_fields(self):
        documents=[{},dict(llm=dict(provider='missing',providers=self.document['llm']['providers']))]
        for raw in ({},dict(api_key='YOUR_KEY',base_url='https://mock.invalid',model='m'),dict(api_key='secret',base_url='file:///private',model='m'),dict(api_key='secret',base_url='https://user:password@mock.invalid',model='m')):
            documents.append(dict(llm=dict(provider='x',providers=dict(x=raw))))
        for d in documents:
            self.config.write_text(json.dumps(d))
            with self.assertRaises(LaunchError):self.prepare()

    def test_report_never_contains_any_provider_key_or_base_url(self):
        _,_,r=self.prepare();text=json.dumps(r)
        for raw in self.document['llm']['providers'].values():
            self.assertNotIn(raw['api_key'],text);self.assertNotIn(raw['base_url'],text)

    def test_check_does_not_start_runtime_or_sdk(self):
        cfg,project,report=self.prepare()
        with patch('mybot.web.__main__.prepare_launch',return_value=(cfg,project,report)),patch('uvicorn.run') as run,patch('mybot.web.server.create_app') as app,patch('mybot.config.build_client') as sdk,contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['--check','--workspace',str(self.repo)]),0)
        run.assert_not_called();app.assert_not_called();sdk.assert_not_called();self.assertTrue(json.loads(out.getvalue())['ok'])

    def test_start_uses_only_process_config_and_project_metadata(self):
        cfg,project,report=self.prepare()
        with patch('mybot.web.__main__.prepare_launch',return_value=(cfg,project,report)),patch('uvicorn.run') as run,patch('mybot.web.server.create_app',return_value='app') as app:
            self.assertEqual(main(['--workspace',str(self.repo),'--port','8766']),0)
        app.assert_called_once_with(cfg,port=8766,project=project);self.assertEqual(run.call_args.kwargs['host'],'127.0.0.1')

    def test_invalid_json_cli_diagnostic_before_app_import(self):
        self.config.write_text('{\n broken\n}')
        with patch('mybot.web.launch.DEFAULT_CONFIG',self.config),contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['--check']),2)
        self.assertEqual(json.loads(out.getvalue())['error_type'],'CONFIG_JSON_INVALID')

    def test_package_and_web_entry_do_not_eagerly_import_config(self):
        code="import sys; import mybot.web.__main__; assert 'mybot.config' not in sys.modules; assert 'uvicorn' not in sys.modules; assert 'mybot.web.server' not in sys.modules"
        subprocess.run([sys.executable,'-c',code],check=True,capture_output=True)

    def test_storage_inside_project_rejected_before_runtime(self):
        cfg=replace(self.cfg,session_backend='event_sqlite',session_event_path=self.repo/'events.sqlite3')
        with self.assertRaises(LaunchError):self.prepare(cfg=cfg)
        self.assertFalse((self.repo/'events.sqlite3').exists())


class ProjectWebChecks(unittest.IsolatedAsyncioTestCase):
    async def test_native_read_in_selected_project_no_seed_and_no_switch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();repo=root/'project';repo.mkdir();(repo/'source.py').write_text('VALUE = 42\n')
            git(repo,'init','-q','--initial-branch=project');git(repo,'add','.');git(repo,'-c','user.name=Offline','-c','user.email=offline@invalid.local','commit','-qm','fixture')
            project=await inspect_project(repo);cfg=GatewayConfig(workspace=repo,skills_enabled=False,context_enabled=False,session_persist=False,coding_enabled=True,coding_patch_mode='off',provider='mock',model='mock',api_key='synthetic-key')
            seen=[]
            class Client:
                def __init__(self):self.chat=type('Chat',(),{'completions':self})();self.step=0
                async def create(self,**args):
                    seen.append(args);self.step+=1
                    return response(calls=[call('read','read_file_range','{"path":"source.py","start_line":1,"end_line":10}')]) if self.step==1 else response('read complete')
                async def close(self):pass
            before={str(p.relative_to(repo)):p.read_bytes() for p in repo.rglob('*') if p.is_file()}
            app=create_app(cfg,project=project,client_factory=lambda cfg:Client());http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8765')
            try:
                await http.get('/');boot=(await http.get('/api/bootstrap')).json();headers={'origin':'http://127.0.0.1:8765','x-mybot-csrf':boot['csrf']}
                self.assertEqual(boot['project']['branch'],'project');self.assertTrue(boot['coding']);self.assertEqual(boot['patch_mode'],'off')
                sid=(await http.post('/api/conversations',headers=headers)).json()['id']
                denied=await http.post('/api/conversations/'+sid+'/messages',headers=headers,json=dict(message='read',workspace='/tmp/other'));self.assertEqual(denied.status_code,400)
                accepted=await http.post('/api/conversations/'+sid+'/messages',headers=headers,json=dict(message='read'));self.assertEqual(accepted.status_code,202)
                await app.runtime.conversations[sid].task
                self.assertTrue(any('VALUE = 42' in m.get('content','') for m in seen[-1]['messages'] if m['role']=='tool'))
                self.assertEqual(app.runtime.config.workspace,repo)
            finally:await http.aclose();await app.runtime.close()
            self.assertFalse((repo/'instructions').exists());self.assertEqual(before,{str(p.relative_to(repo)):p.read_bytes() for p in repo.rglob('*') if p.is_file()})

    async def test_non_coding_project_chat_does_not_seed_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();(root/'source.py').write_text('VALUE=1\n')
            cfg=GatewayConfig(workspace=root,skills_enabled=False,context_enabled=False,session_persist=False)
            class Client:
                def __init__(self):self.chat=type('Chat',(),{'completions':self})()
                async def create(self,**args):return response('hello')
                async def close(self):pass
            app=create_app(cfg,project=dict(name='project',branch='main'),client_factory=lambda cfg:Client())
            try:
                c=app.runtime.new();await app.runtime.start(c,'hello');await c.task;self.assertEqual(c.status,'completed')
                self.assertFalse(app.runtime.config.coding_enabled);self.assertEqual(list(root.iterdir()),[root/'source.py'])
            finally:await app.runtime.close()

    async def test_project_mode_readonly_chat_skips_initialization_and_lease_still_applies(self):
        from mybot.workspace_lease import WorkspaceLease
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();cfg=GatewayConfig(workspace=root,skills_enabled=False,context_enabled=False,session_persist=False)
            class Client:
                async def close(self):pass
            factory=Mock(return_value=Client())
            app=create_app(cfg,project=dict(name='project',branch='main'),client_factory=factory)
            c=app.runtime.new();lease=WorkspaceLease(root).acquire()
            try:
                await app.runtime.start(c,'read');await c.task;self.assertEqual(c.status,'failed');factory.assert_not_called();self.assertTrue(any(e['type']=='workspace_busy' for e in c.events))
            finally:lease.release();await app.runtime.close()
            self.assertFalse((root/'instructions').exists())


if __name__=='__main__':unittest.main()
