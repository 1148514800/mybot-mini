"""Lightweight static map and authenticated on-demand UI tests; Mock models only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from mybot.agent import AgentLoop,ContextBuilder
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from mybot.tools.repo_map import RepoMapTool,MAX_OUTPUT_BYTES
from mybot.web.server import create_app
from scripts.coding_workflow_canary_v1.fixture import git
from scripts.check_session import response,call


class RepoMapChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        git(self.root,'init','-q','--initial-branch=example')
        self.write('pkg/__init__.py','from .helper import answer\n')
        self.write('pkg/helper.py','def answer():\n    return 42\n')
        self.write('pkg/main.py','import os\nfrom . import helper\nfrom pkg.helper import answer as result\n\ndef run():\n    def inner(): pass\n    return result()\n\nclass App:\n    def start(self): pass\n    async def stop(self): pass\n')
        self.write('ui.js','throw Error("must not execute")\n');self.track();self.tool=RepoMapTool(self.root)

    def write(self,name,text):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p
    def track(self):git(self.root,'add','-f','.')
    async def mapping(self,**kwargs):
        result=await self.tool.execute(**kwargs);self.assertTrue(result.success,result.error);self.assertLessEqual(len(result.to_text().encode()),MAX_OUTPUT_BYTES);return json.loads(result.output)
    def image(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    async def test_functions_classes_methods_and_lines(self):
        m=await self.mapping();main=next(f for f in m['files'] if f['path']=='pkg/main.py');symbols={s['name']:(s['kind'],s['line']) for s in main['symbols']}
        self.assertEqual(symbols,{'run':('function',5),'App':('class',9),'App.start':('method',10),'App.stop':('async_method',11)})
        self.assertFalse(m['truncated']);self.assertEqual(m['scanned_files'],4)

    async def test_static_imports_relative_absolute_external(self):
        m=await self.mapping();main=next(f for f in m['files'] if f['path']=='pkg/main.py');imports=main['imports']
        self.assertEqual(imports[0]['resolution'],'external_or_unresolved')
        self.assertIn('pkg/helper.py',imports[1]['targets']);self.assertIn('pkg/helper.py',imports[2]['targets']);self.assertEqual(imports[2]['line'],3)
        self.assertEqual(imports[2]['names'],[dict(name='answer',alias='result')])

    async def test_non_python_path_only_and_untracked_omitted(self):
        self.write('untracked.py','def hidden():pass\n');m=await self.mapping()
        self.assertNotIn('untracked.py',str(m));self.assertEqual(next(f['status'] for f in m['files'] if f['path']=='ui.js'),'path_only')

    async def test_private_files_and_symlinks_never_read(self):
        for name in ('.env','config/config.json','credentials.py','data.sqlite3','weights.pt','secrets/private.py'):
            self.write(name,'DO_NOT_EXPOSE_PRIVATE');
        outside=self.root.parent/(self.root.name+'-outside.py');outside.write_text('def private_external():pass\n');self.addCleanup(outside.unlink)
        (self.root/'alias.py').symlink_to(outside);(self.root/'internal.py').symlink_to(self.root/'pkg/helper.py');self.track()
        original=self.tool.read_bytes;seen=[]
        def guarded(path,**kw):seen.append(str(path.relative_to(self.root)));return original(path,**kw)
        with patch.object(self.tool,'read_bytes',side_effect=guarded):m=await self.mapping()
        self.assertEqual(set(seen),{'pkg/__init__.py','pkg/helper.py','pkg/main.py'});self.assertNotIn('DO_NOT_EXPOSE',str(m));self.assertNotIn('private_external',str(m));self.assertEqual(m['skipped_files'],2)

    async def test_invalid_ast_does_not_abort(self):
        self.write('broken.py','def oops(\n');self.track();m=await self.mapping();self.assertEqual(next(f['status'] for f in m['files'] if f['path']=='broken.py'),'parse_error');self.assertTrue(any(f['path']=='pkg/helper.py' for f in m['files']))

    async def test_file_size_and_output_limits(self):
        self.write('big.py','#'*(512*1024+1));self.write('many.py','\n'.join('def '+('name'+str(i)+'x'*200)+'(): pass' for i in range(100)));self.track()
        m=await self.mapping();self.assertTrue(m['truncated']);self.assertTrue(any(f.get('symbols_imports_truncated') for f in m['files']));self.assertLessEqual(m['scanned_files'],120)

    async def test_120_file_bound_and_user_limit(self):
        for n in range(150):self.write(f'file{n:03}.txt','path only\n')
        self.track();m=await self.mapping();self.assertTrue(m['truncated']);self.assertEqual(m['scanned_files'],120)
        small=await self.mapping(max_files=2);self.assertTrue(small['truncated']);self.assertEqual(small['scanned_files'],2)
        for bad in (121,True,0):self.assertFalse((await self.tool.execute(max_files=bad)).success)

    async def test_no_execution_or_git_workspace_changes(self):
        marker=self.root/'executed';self.write('unsafe.py',f'open({str(marker)!r},"w").write("bad")\nraise RuntimeError("never")\n');self.track();before=self.image()
        await self.mapping();self.assertFalse(marker.exists());self.assertEqual(self.image(),before)

    async def test_control_characters_are_literal_escaped(self):
        self.write('bad\x1b\u202efile.py','def regular():pass\n');self.track();r=await self.tool.execute();m=json.loads(r.output)
        self.assertNotIn('\x1b',str(m));self.assertNotIn('\u202e',str(m));self.assertIn('\\u001b',str(m));self.assertIn('\\u202e',str(m))

    async def test_ambiguous_module_not_claimed_unique(self):
        self.write('pkg/helper/__init__.py','def other():pass\n');self.track();m=await self.mapping();main=next(f for f in m['files'] if f['path']=='pkg/main.py')
        self.assertTrue(any(i['resolution']=='ambiguous' for i in main['imports']))

    async def test_only_coding_registry_exposes_native_readonly_tool(self):
        self.assertFalse(build_default_tool_registry(self.root).has_tool('repo_map'))
        tools=build_default_tool_registry(self.root,coding_enabled=True);self.assertTrue(tools.permitted('repo_map'))
        self.assertFalse(tools.mutation_enabled);self.assertFalse((await tools.execute('repo_map',dict(workspace='/tmp'))).success)

    async def test_agent_can_call_without_auto_map_or_extra_model_requests(self):
        cfg=GatewayConfig(workspace=self.root,coding_enabled=True,skills_enabled=False,context_enabled=False,session_persist=False)
        seen=[]
        class Client:
            def __init__(self,use_map):self.use_map=use_map;self.chat=type('Chat',(),{'completions':self})();self.count=0
            async def create(self,**args):
                self.count+=1;seen.append(args)
                return response(calls=[call('map','repo_map','{}')]) if self.use_map and self.count==1 else response('done')
        for use_map in (True,False):
            client=Client(use_map);agent=AgentLoop(client,cfg,build_default_tool_registry(self.root,coding_enabled=True),ContextBuilder(self.root))
            with patch.object(RepoMapTool,'_execute',wraps=self.tool._execute) as mapped:
                await agent.handle_message('overview' if use_map else 'hello');self.assertEqual(mapped.await_count,int(use_map))
            agent.close_history();self.assertEqual(client.count,2 if use_map else 1)
        self.assertTrue(any('scanned_files' in m.get('content','') for m in seen[1]['messages'] if m['role']=='tool'))


class WebMapChecks(unittest.IsolatedAsyncioTestCase):
    async def test_on_demand_auth_csrf_and_no_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();git(root,'init','-q');(root/'sample.py').write_text('class Example: pass\n');git(root,'add','.')
            cfg=GatewayConfig(workspace=root,skills_enabled=False,context_enabled=False,session_persist=False)
            def forbidden(_):raise AssertionError('repo map must not create a model client')
            app=create_app(cfg,client_factory=forbidden);http=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8765')
            try:
                with patch.object(RepoMapTool,'execute',autospec=True) as scan:
                    await http.get('/');boot=(await http.get('/api/bootstrap')).json();scan.assert_not_called()
                self.assertEqual((await http.post('/api/repo-map',json={})).status_code,403)
                headers={'origin':'http://127.0.0.1:8765','x-mybot-csrf':boot['csrf']}
                self.assertEqual((await http.post('/api/repo-map',headers={**headers,'origin':'http://evil.invalid'},json={})).status_code,403)
                self.assertEqual((await http.post('/api/repo-map',headers=headers,json=dict(workspace='/tmp'))).status_code,400)
                result=await http.post('/api/repo-map',headers=headers,json={});self.assertEqual(result.status_code,200);self.assertIn('Example',result.text);self.assertNotIn(str(root),result.text)
                self.assertFalse(app.runtime.config.coding_enabled);self.assertEqual(len(app.runtime.conversations),0)
                app.runtime.owner='busy';self.assertEqual((await http.post('/api/repo-map',headers=headers,json={})).status_code,409)
            finally:await http.aclose();await app.runtime.close()


if __name__=='__main__':unittest.main()
