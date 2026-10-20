"""Offline structured editing checks: real files, injected races/errors, original loop."""
import asyncio
import contextlib
import ctypes
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from copy import deepcopy
from types import SimpleNamespace as N
from unittest.mock import patch, AsyncMock

from jsonschema import Draft202012Validator
from mybot.tools import build_default_tool_registry
from mybot.tools.base import Tool, ToolResult
from mybot.tools.patch import ApplyPatchTool, sha, MAX_PATCH_BYTES
from mybot.tools.repository import MAX_FILE_BYTES
from mybot.config import GatewayConfig
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.planning import Plan
from mybot.evaluation.tool_agent import pair_messages
from scripts.coding_repo_demo import make_demo, edit_demo, fingerprint
from scripts.check_session import call, response


class PatchChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = make_demo(Path(self.tmp.name) / 'repo')
        self.tool = ApplyPatchTool(self.root, patch_mode='write')
        self.tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write')
        self.file = self.root / 'src/calculator.py'
        self.body = self.file.read_bytes()
        self.index = (self.root / '.git/index').read_bytes()

    def update(self, path='src/calculator.py', old='return left - right', new='return left + right'):
        return dict(op='update', path=path, expected_sha256=sha((self.root / path).read_bytes()),
                    edits=[dict(old_text=old, new_text=new)])

    async def run_patch(self, *changes, **args):
        return await self.tool.execute(changes=list(changes or [self.update()]), **args)

    def no_temps(self):
        self.assertEqual(list(self.root.rglob('.mybot-patch-*')), [])

    async def reject(self, change, error, **args):
        before = fingerprint(self.root)
        r = await self.run_patch(change, dry_run=False, **args)
        self.assertFalse(r.success); self.assertEqual(r.error, error)
        self.assertEqual(r.metadata['status'], 'preflight_failed')
        self.assertEqual(fingerprint(self.root), before); self.no_temps()
        return r

    async def test_default_config_and_registry(self):
        self.assertEqual(GatewayConfig().coding_patch_mode, 'off')
        self.assertEqual([t.name for t in build_default_tool_registry(self.root).iter_tools()], ['read_file','write_file','list_files'])
        off = build_default_tool_registry(self.root, coding_enabled=True)
        self.assertEqual(len(off.iter_tools()), 7)
        self.assertFalse(off.has_tool('apply_patch'))
        self.assertEqual(off.get_parameters('read_file_range'), self.tools.get_parameters('read_file_range'))

    async def test_patch_only_registry_cannot_guess_write(self):
        for mode in ('preview','write'):
            tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode=mode)
            self.assertEqual(len(tools.iter_tools()), 7)
            self.assertFalse(tools.has_tool('write_file'))
            self.assertFalse((await tools.execute('write_file', {'path':'notes.txt','content':'BAD'})).success)
            self.assertTrue(tools.has_tool('apply_patch'))
        self.assertFalse((await build_default_tool_registry(self.root).execute('apply_patch', {})).success)

    async def test_invalid_config_and_registry(self):
        for value in (True, 1, None, [], {}, 'invalid'):
            with self.assertRaises(ValueError): GatewayConfig(coding_enabled=True, coding_patch_mode=value)
            with self.assertRaises(ValueError): build_default_tool_registry(self.root,coding_enabled=True,patch_mode=value)
        for mode in ('preview','write'):
            with self.assertRaises(ValueError): GatewayConfig(coding_patch_mode=mode)
            with self.assertRaises(ValueError): build_default_tool_registry(self.root,patch_mode=mode)
        for coding in ({'patch_mode':'write'}, {'enabled':True,'unknown':1}, {'enabled':1}, None):
            with patch('mybot.config._CONFIG', {'coding':coding}):
                with self.assertRaises(ValueError): GatewayConfig()
        with patch('mybot.config._CONFIG', {'coding':{'enabled':True,'patch_mode':'preview'}}):
            self.assertEqual(GatewayConfig().coding_patch_mode, 'preview')

    async def test_gateway_explicit_mode(self):
        from mybot.app import run_gateway
        seen=[]
        cfg=GatewayConfig(workspace=self.root,coding_enabled=True,coding_patch_mode='preview',mcp_enabled=False)
        with patch('mybot.app.init_workspace') as init, patch('mybot.app.build_client',return_value=N(close=AsyncMock())),patch('mybot.app.AgentLoop',side_effect=lambda **kw: seen.append(kw['tools']) or N(run=AsyncMock())):
            with contextlib.redirect_stdout(io.StringIO()): await run_gateway(cfg)
        init.assert_not_called()
        self.assertEqual(seen[0].get_tool('apply_patch').patch_mode,'preview')
        self.assertFalse(seen[0].has_tool('write_file'))

    async def test_schema_and_illegal_fields(self):
        Draft202012Validator.check_schema(self.tool.parameters)
        bad = [{}, {'changes':[]}, {'dry_run':0,'changes':[self.update()]},
               {'changes':[dict(self.update(),extra=1)]}, {'changes':[{'op':'delete','path':'notes.txt'}]},
               {'changes':[dict(self.update(),edits=[{'old_text':'','new_text':'x'}])]},
               {'changes':[dict(self.update(),edits=[{'old_text':'x','new_text':'y','extra':1}])]},
               {'changes':[dict(self.update(),expected_sha256='x'*64)]},
               {'changes':[self.update()],'command':'touch HACKED'}]
        for args in bad:
            r=await self.tool.execute(**args); self.assertFalse(r.success, args)
        self.no_temps(); self.assertEqual(self.file.read_bytes(),self.body)

    def test_patch_schema_documents_preview_write_and_operation_shapes(self):
        schema = self.tool.to_schema()['function']['parameters']
        Draft202012Validator.check_schema(schema)
        description = self.tool.description
        for text in ('dry_run=true', 'dry_run=false', 'op, path, expected_sha256 and edits',
                     'old_text and new_text', 'op, path and content', 'No extra fields',
                     'does not grant write permission', 'Reread and rebuild', 'never replay blindly'):
            self.assertIn(text, description)
        dry = schema['properties']['dry_run']
        self.assertEqual(dry['type'], 'boolean'); self.assertIs(dry['default'], True)
        self.assertIn('true previews only', dry['description'])
        self.assertIn('false requests a write', dry['description'])
        changes = schema['properties']['changes']
        for text in ('target files', 'unchanged', 'reuse the same changes', 'only dry_run=false', 'preview again'):
            self.assertIn(text, changes['description'])
        self.assertEqual(schema['required'], ['changes'])
        self.assertFalse(schema['additionalProperties'])
        update, add = changes['items']['oneOf']
        self.assertEqual(update['required'], ['op','path','expected_sha256','edits'])
        self.assertEqual(add['required'], ['op','path','content'])
        self.assertEqual(update['properties']['edits']['items']['required'], ['old_text','new_text'])
        for spec in (update, add, update['properties']['edits']['items']):
            self.assertFalse(spec['additionalProperties'])

    async def test_same_changes_preview_then_explicit_write_without_mutation(self):
        changes = [self.update(), {'op':'add','path':'src/extra.py','content':'VALUE = 1\n'}]
        original = deepcopy(changes); before = fingerprint(self.root)
        with patch.object(self.tool, '_stage', wraps=self.tool._stage) as stage, \
                patch.object(self.tool, '_publish', wraps=self.tool._publish) as publish:
            preview = await self.tool.execute(dry_run=True, changes=changes)
            self.assertTrue(preview.success, preview.to_text())
            self.assertFalse(preview.metadata['applied'] or preview.metadata['execution_evidence'])
            stage.assert_not_called(); publish.assert_not_called()
        self.assertEqual(fingerprint(self.root), before)
        self.assertEqual((self.root/'.git/index').read_bytes(), self.index)
        self.no_temps()
        write = await self.tool.execute(dry_run=False, changes=changes)
        self.assertTrue(write.success, write.to_text())
        self.assertTrue(write.metadata['applied'])
        self.assertEqual(set(write.metadata['changed_files']), {'src/calculator.py','src/extra.py'})
        self.assertEqual(self.file.read_bytes(), self.body.replace(b'return left - right', b'return left + right'))
        self.assertEqual((self.root/'src/extra.py').read_text(), 'VALUE = 1\n')
        self.assertEqual(changes, original)
        self.assertEqual((self.root/'.git/index').read_bytes(), self.index)
        self.no_temps()

    async def test_successful_preview_does_not_enable_write_mode(self):
        tool = ApplyPatchTool(self.root, patch_mode='preview')
        changes = [self.update()]
        self.assertTrue((await tool.execute(dry_run=True, changes=changes)).success)
        result = await tool.execute(dry_run=False, changes=changes)
        self.assertEqual(result.error, 'patch_write_disabled')
        self.assertFalse(result.metadata['safe_to_retry'])
        self.assertEqual(self.file.read_bytes(), self.body)
        self.assertEqual((self.root/'.git/index').read_bytes(), self.index)
        self.no_temps()

    async def test_invalid_dry_run_types_still_fail_before_preflight(self):
        with patch.object(self.tool, '_preflight') as preflight:
            for value in (0,1,'true','false',None,[],{}):
                with self.subTest(value=value):
                    result = await self.tool.execute(dry_run=value, changes=[self.update()])
                    self.assertEqual(result.error, 'invalid_arguments')
                    self.assertEqual(result.metadata['failure_phase'], 'validation')
                    self.assertFalse(result.metadata['safe_to_retry'])
                    self.assertFalse(result.metadata['applied'] or result.metadata['execution_evidence'])
            preflight.assert_not_called()
        self.assertEqual(self.file.read_bytes(), self.body)
        self.assertEqual((self.root/'.git/index').read_bytes(), self.index)

    async def test_preview_does_not_repair_invalid_write_structures(self):
        base = {'dry_run':False,'changes':[self.update()]}
        self.assertTrue((await self.tool.execute(**{**base,'dry_run':True})).success)
        bad = [{'dry_run':False}, {**base,'changes':[]}, {**base,'extra':'PRIVATE_PATCH_FIELD'}]
        for name in ('op','path','expected_sha256','edits'):
            args = deepcopy(base); del args['changes'][0][name]; bad.append(args)
        for name in ('old_text','new_text'):
            args = deepcopy(base); del args['changes'][0]['edits'][0][name]; bad.append(args)
        for edits in ({'old_text':'x','new_text':'y'}, [{}], [{'old_text':'','new_text':'y'}],
                      [{'old_text':'x','new_text':1}], [{'old_text':'x','new_text':'y','extra':1}]):
            args = deepcopy(base); args['changes'][0]['edits'] = edits; bad.append(args)
        for value in ('x'*64, '0'*63, 123):
            args = deepcopy(base); args['changes'][0]['expected_sha256'] = value; bad.append(args)
        args = deepcopy(base); args['changes'][0]['extra'] = True; bad.append(args)
        args = deepcopy(base); args['changes'][0]['edits'] *= 17; bad.append(args)
        bad.extend([{**base,'changes':base['changes']*9},
                    {**base,'changes':[{'op':'add','path':'src/new.py'}]},
                    {**base,'changes':[{'op':'add','path':'src/new.py','content':'x','extra':1}]}])
        before = fingerprint(self.root)
        with patch.object(self.tool, '_preflight') as preflight, patch.object(self.tool, '_stage') as stage:
            for args in bad:
                with self.subTest(shape=list(args)):
                    result = await self.tool.execute(**args)
                    self.assertEqual(result.error, 'invalid_arguments')
                    self.assertEqual(result.metadata['failure_phase'], 'validation')
                    self.assertEqual(result.metadata['status'], 'preflight_failed')
                    self.assertFalse(result.metadata['safe_to_retry'])
                    self.assertFalse(result.metadata['applied'] or result.metadata['execution_evidence'])
                    self.assertEqual(fingerprint(self.root), before)
                    self.assertEqual((self.root/'.git/index').read_bytes(), self.index)
                    self.no_temps()
            preflight.assert_not_called(); stage.assert_not_called()

    async def test_stale_after_preview_requires_reread_and_new_preview(self):
        changes = [self.update()]
        self.assertTrue((await self.tool.execute(dry_run=True, changes=changes)).success)
        external = self.body+b'\n# external update\n'; self.file.write_bytes(external)
        result = await self.tool.execute(dry_run=False, changes=changes)
        self.assertEqual(result.error, 'stale_file_hash')
        self.assertTrue(result.metadata['safe_to_retry'])
        self.assertEqual(result.metadata['failure_phase'], 'preflight')
        self.assertEqual(self.file.read_bytes(), external)
        version = await self.tools.execute('read_file_range', {'path':'src/calculator.py','start_line':1,'end_line':20})
        self.assertTrue(version.success)
        changes[0]['expected_sha256'] = version.metadata['file_sha256']
        self.assertTrue((await self.tool.execute(dry_run=True, changes=changes)).success)
        self.assertTrue((await self.tool.execute(dry_run=False, changes=changes)).success)
        self.assertEqual(self.file.read_bytes(), external.replace(b'return left - right',b'return left + right'))
        self.assertEqual((self.root/'.git/index').read_bytes(), self.index)
        self.no_temps()

    async def test_full_raw_hash_even_partial_range(self):
        self.file.write_bytes(b'\xef\xbb\xbf# \xe4\xb8\xad\xe6\x96\x87\r\nabc\r\nend')
        r=await self.tools.execute('read_file_range',dict(path='src/calculator.py',start_line=2,end_line=2))
        self.assertEqual(r.output,'2 | abc\r\n')
        self.assertEqual(r.metadata['file_sha256'],sha(self.file.read_bytes()))
        self.assertEqual(r.metadata['file_bytes'],len(self.file.read_bytes()))
        old=await build_default_tool_registry(self.root,coding_enabled=True).execute('read_file_range',dict(path='src/calculator.py',start_line=1,end_line=1))
        self.assertNotIn('file_sha256',old.metadata)

    async def test_hash_only_for_complete_valid_reads(self):
        for body in (b'\xff',b'a\0',b'x'*(MAX_FILE_BYTES+1)):
            self.file.write_bytes(body)
            r=await self.tools.execute('read_file_range',dict(path='src/calculator.py',start_line=1,end_line=1))
            self.assertFalse(r.success); self.assertNotIn('file_sha256',r.metadata)
        self.file.write_bytes(b'x'*30000)
        r=await self.tools.execute('read_file_range',dict(path='src/calculator.py',start_line=1,end_line=1))
        self.assertTrue(r.metadata['truncated']); self.assertEqual(r.metadata['file_sha256'],sha(self.file.read_bytes()))

    async def test_stale_hash_retry(self):
        c=self.update(); self.file.write_bytes(self.body+b'# external\n')
        r=await self.reject(c,'stale_file_hash');self.assertTrue(r.metadata['safe_to_retry'])

    async def test_missing_anchor_retry(self):
        r=await self.reject(self.update(old='absent'),'anchor_not_found'); self.assertTrue(r.metadata['safe_to_retry'])

    async def test_ambiguous_anchor_including_overlapping_occurrences(self):
        self.file.write_bytes(b'aaa')
        r=await self.reject(self.update(old='aa'),'ambiguous_context');self.assertTrue(r.metadata['safe_to_retry'])

    async def test_overlapping_edits(self):
        c=self.update();c['edits']=[dict(old_text='return left',new_text='x'),dict(old_text='left - right',new_text='y')]
        await self.reject(c,'overlapping_edits')

    async def test_edits_use_same_snapshot(self):
        self.file.write_bytes(b'alpha beta')
        c=self.update(old='alpha',new='beta');c['edits'].append(dict(old_text='beta',new_text='gamma'))
        r=await self.run_patch(c,dry_run=False)
        self.assertTrue(r.success,r.to_text());self.assertEqual(self.file.read_bytes(),b'beta gamma')

    async def test_noop_rejected(self):
        r=await self.reject(self.update(new='return left - right'),'no_effective_changes')
        self.assertFalse(r.metadata['safe_to_retry'])

    async def test_byte_preservation_and_modes(self):
        for body in (b'alpha\n# user\n', b'alpha\r\n# user\r\n', b'alpha',
                     '\ufeffalpha\r\n# 中文 e\u0301\n'.encode()):
            for mode in (0o644,0o755):
                self.file.write_bytes(body); self.file.chmod(mode)
                r=await self.run_patch(self.update(old='alpha',new='中文'),dry_run=False)
                self.assertTrue(r.success,r.to_text())
                self.assertEqual(self.file.read_bytes(),body.replace(b'alpha','中文'.encode()))
                self.assertEqual(stat.S_IMODE(self.file.stat().st_mode),mode)

    async def test_empty_new_text(self):
        self.assertTrue((await self.run_patch(self.update(new=''),dry_run=False)).success)
        self.assertEqual(self.file.read_bytes(),self.body.replace(b'return left - right',b''))

    async def test_dry_run_no_temp_mtime_or_index_changes(self):
        before=fingerprint(self.root);mtime=self.file.stat().st_mtime_ns
        with patch.object(self.tool,'_temp',side_effect=AssertionError('dry run wrote')):
            r=await self.run_patch()
        self.assertTrue(r.success); self.assertFalse(r.metadata['applied']);self.assertFalse(r.metadata['execution_evidence'])
        self.assertTrue(r.metadata['validation_ok']);self.assertIn('-    return left - right',r.output)
        self.assertEqual(r.metadata['preview_diff'],r.output)
        self.assertEqual(before,fingerprint(self.root));self.assertEqual(mtime,self.file.stat().st_mtime_ns)
        self.assertEqual(self.index,(self.root/'.git/index').read_bytes());self.no_temps()

    async def test_preview_refuses_write(self):
        t=ApplyPatchTool(self.root,patch_mode='preview')
        r=await t.execute(changes=[self.update()],dry_run=False)
        self.assertEqual(r.error,'patch_write_disabled');self.assertEqual(self.file.read_bytes(),self.body)

    async def test_dry_run_is_not_cached_authorization(self):
        c=self.update(); self.assertTrue((await self.run_patch(c)).success)
        self.file.write_bytes(self.body+b'change')
        await self.reject(c,'stale_file_hash')

    async def test_add_utf8_no_clobber_and_mode(self):
        c=dict(op='add',path='tests/new.py',content='# 中文\r\n')
        self.assertTrue((await self.run_patch(c)).success);self.assertFalse((self.root/c['path']).exists())
        r=await self.run_patch(c,dry_run=False)
        self.assertTrue(r.success,r.to_text());self.assertEqual((self.root/c['path']).read_bytes(),c['content'].encode())
        self.assertEqual(r.metadata['after_sha256'][c['path']],sha(c['content'].encode()))
        self.assertIsNone(r.metadata['before_sha256'][c['path']]);self.assertEqual(stat.S_IMODE((self.root/c['path']).stat().st_mode),0o600)
        self.assertEqual(self.index,(self.root/'.git/index').read_bytes());self.no_temps()

    async def test_add_existing_file_directory_and_link(self):
        (self.root/'link.py').symlink_to(self.file)
        (self.root/'dangling.py').symlink_to(self.root/'absent')
        for path in ('notes.txt','src','link.py','dangling.py'):
            r=await self.run_patch(dict(op='add',path=path,content='bad'),dry_run=False)
            self.assertFalse(r.success)
        self.assertEqual(self.file.read_bytes(),self.body)

    async def test_add_missing_parent(self):
        await self.reject(dict(op='add',path='missing/a.py',content='abc'),'parent_missing')
        self.assertFalse((self.root/'missing').exists())

    async def test_add_race_cannot_overwrite(self):
        original=self.tool._publish
        def race(item):
            (self.root/item.path).write_bytes(b'user racing add')
            original(item)
        with patch.object(self.tool,'_publish',side_effect=race):
            r=await self.run_patch(dict(op='add',path='new.py',content='ours'),dry_run=False)
        self.assertFalse(r.success);self.assertEqual((self.root/'new.py').read_bytes(),b'user racing add')
        self.assertFalse(r.metadata['safe_to_retry']);self.no_temps()

    async def test_outside_and_sensitive_paths(self):
        for path in ('../escape.py', str(Path(self.tmp.name)/'outside.py'), '.git/config',
                     '.gitignore','.env','config/config.json','credentials.json','secrets/a.py','cache/a.py'):
            r=await self.run_patch(dict(op='add',path=path,content='x'),dry_run=False)
            self.assertFalse(r.success,path)
        self.no_temps()

    async def test_all_symlink_components_denied(self):
        (self.root/'alias').symlink_to(self.root/'src',target_is_directory=True)
        (self.root/'outside').symlink_to(Path(self.tmp.name),target_is_directory=True)
        for path in ('alias/calculator.py','alias/new.py','outside/new.py'):
            r=await self.run_patch(dict(op='add',path=path,content='x'),dry_run=False)
            self.assertFalse(r.success,path)
        self.assertEqual(self.file.read_bytes(),self.body)

    async def test_target_symlink_denied_update(self):
        (self.root/'link.py').symlink_to(self.file)
        self.assertFalse((await self.run_patch(self.update(path='link.py'),dry_run=False)).success)

    async def test_special_files_and_hardlinks(self):
        os.mkfifo(self.root/'fifo')
        c=dict(self.update(),path='fifo')
        r=await self.run_patch(c,dry_run=False);self.assertEqual(r.error,'not_regular_file')
        os.link(self.file,self.root/'hard.py')
        self.assertEqual((await self.run_patch(self.update(),dry_run=False)).error,'hardlink_denied')
        self.no_temps()

    async def test_binary_invalid_utf8_and_large(self):
        for body,error in ((b'a\0b','binary_file'),(b'\xff','invalid_utf8'),(b'x'*(MAX_FILE_BYTES+1),'file_too_large')):
            self.file.write_bytes(body)
            await self.reject(self.update(),error)
        for content in ('x\0','\ud800'):
            r=await self.run_patch(dict(op='add',path='new.py',content=content),dry_run=False)
            self.assertFalse(r.success);self.assertFalse((self.root/'new.py').exists())

    async def test_patch_resource_bounds(self):
        for args in ({'changes':[self.update()]*9},
                     {'changes':[dict(self.update(),edits=[dict(old_text='a',new_text='b')]*17)]},
                     {'changes':[dict(op='add',path='new.py',content='中'*(MAX_PATCH_BYTES//2))]},
                     {'changes':[dict(op='add',path='new.py',content='x'*MAX_PATCH_BYTES)]},
                     {'changes':[dict(op='add',path='new.py',content='\n'*MAX_PATCH_BYTES)]}):
            self.assertFalse((await self.tool.execute(**args)).success)
        self.no_temps()

    async def test_final_file_size_bound(self):
        self.file.write_bytes(b'a'+b'x'*(MAX_FILE_BYTES-1))
        await self.reject(self.update(old='a',new='ab'),'file_too_large')

    async def test_duplicate_normalized_paths(self):
        for path in ('src/calculator.py','./src/calculator.py',str(self.file)):
            c=dict(self.update(),path=path)
            r=await self.run_patch(self.update(),c,dry_run=False)
            self.assertEqual(r.error,'duplicate_path')
        r=await self.run_patch(self.update(),dict(op='add',path='src/calculator.py',content='x'),dry_run=False)
        self.assertEqual(r.error,'duplicate_path')

    async def test_multifile_preflight_failure_has_no_writes(self):
        before=fingerprint(self.root)
        r=await self.run_patch(self.update(),dict(op='add',path='tests/new.py',content='new'),self.update(path='notes.txt',old='absent'),dry_run=False)
        self.assertFalse(r.success);self.assertEqual(before,fingerprint(self.root));self.no_temps()
        self.assertTrue(r.metadata['safe_to_retry'])

    async def test_multifile_mixed_commit(self):
        r=await self.run_patch(self.update(),self.update(path='notes.txt',old='Untracked',new='New'),dict(op='add',path='tests/new.py',content='new'),dry_run=False)
        self.assertTrue(r.success,r.to_text());self.assertEqual(len(r.metadata['changed_files']),3)
        self.assertEqual(self.index,(self.root/'.git/index').read_bytes());self.no_temps()

    async def test_stage_failure_leaves_originals(self):
        stage=self.tool._stage
        def fail(item):
            stage(item)
            if item.op=='add': raise OSError('injected')
        with patch.object(self.tool,'_stage',side_effect=fail):
            r=await self.run_patch(self.update(),dict(op='add',path='tests/new.py',content='new'),dry_run=False)
        self.assertFalse(r.success);self.assertEqual(r.metadata['status'],'preflight_failed')
        self.assertEqual(self.file.read_bytes(),self.body);self.assertFalse((self.root/'tests/new.py').exists());self.no_temps()

    async def test_version_changed_after_staging(self):
        stage=self.tool._stage
        def race(item): stage(item); self.file.write_bytes(self.body+b'# new user change\n')
        with patch.object(self.tool,'_stage',side_effect=race): r=await self.run_patch(dry_run=False)
        self.assertEqual(r.error,'stale_file_hash');self.assertTrue(r.metadata['safe_to_retry'])
        self.assertTrue(self.file.read_bytes().endswith(b'# new user change\n'));self.no_temps()

    async def test_parent_replaced_after_staging(self):
        stage=self.tool._stage
        def race(item):
            stage(item);(self.root/'src').rename(self.root/'moved');(self.root/'src').symlink_to(self.root/'moved',target_is_directory=True)
        with patch.object(self.tool,'_stage',side_effect=race):r=await self.run_patch(dry_run=False)
        self.assertFalse(r.success);self.assertEqual((self.root/'moved/calculator.py').read_bytes(),self.body);self.no_temps()

    async def test_caught_publish_failure_rolls_back(self):
        publish=self.tool._publish; before=fingerprint(self.root)
        def fail(item):
            if item.op=='add': raise OSError('injected')
            publish(item)
        with patch.object(self.tool,'_publish',side_effect=fail):
            r=await self.run_patch(self.update(),dict(op='add',path='tests/new.py',content='new'),dry_run=False)
        self.assertEqual(r.metadata['status'],'commit_failed_rolled_back',r.to_text())
        self.assertEqual(before,fingerprint(self.root));self.assertFalse(r.metadata['safe_to_retry']);self.no_temps()

    async def test_error_after_publication_recovers_add_and_update(self):
        for changes in ([self.update(),dict(op='add',path='new.py',content='new')],
                        [dict(op='add',path='new.py',content='new'),self.update()]):
            publish=self.tool._publish;before=fingerprint(self.root)
            def fail(item): publish(item);raise OSError('after syscall')
            with patch.object(self.tool,'_publish',side_effect=fail):r=await self.run_patch(*changes,dry_run=False)
            self.assertEqual(r.metadata['status'],'commit_failed_rolled_back',r.to_text())
            self.assertEqual(before,fingerprint(self.root));self.no_temps()

    async def test_rollback_does_not_clobber_user_change(self):
        publish=self.tool._publish
        def fail(item):
            if item.op=='add': self.file.write_bytes(b'external user content');raise OSError('injected')
            publish(item)
        with patch.object(self.tool,'_publish',side_effect=fail):
            r=await self.run_patch(self.update(),dict(op='add',path='new.py',content='new'),dry_run=False)
        self.assertEqual(r.metadata['status'],'rollback_conflict',r.to_text())
        self.assertEqual(self.file.read_bytes(),b'external user content');self.assertFalse(r.metadata['safe_to_retry']);self.no_temps()

    async def test_changed_backup_is_not_published(self):
        publish=self.tool._publish
        def fail(item):
            publish(item)
            (self.root/'src'/item.backup).write_bytes(b'changed backup')
            raise OSError('publish later failed')
        with patch.object(self.tool,'_publish',side_effect=fail):r=await self.run_patch(dry_run=False)
        self.assertEqual(r.metadata['status'],'rollback_conflict',r.to_text())
        self.assertNotEqual(self.file.read_bytes(),b'changed backup');self.no_temps()

    async def test_cleanup_does_not_delete_replaced_temp(self):
        stage=self.tool._stage; replacement=[]
        def fail(item):
            stage(item)
            p=self.root/'src'/item.stage
            old=p.with_name(p.name+'-held');p.rename(old)
            p.write_bytes(b'user replacement');replacement.extend([p,old])
            raise OSError('stage failed')
        with patch.object(self.tool,'_stage',side_effect=fail):r=await self.run_patch(dry_run=False)
        self.assertEqual(r.metadata['status'],'partial_failure_possible',r.to_text())
        self.assertEqual(replacement[0].read_bytes(),b'user replacement')
        self.assertEqual(self.file.read_bytes(),self.body)

    async def test_uncertain_recovery_reports_partial(self):
        publish=self.tool._publish; replace=os.replace
        def fail(item):
            if item.op=='add': raise OSError('second publication failed')
            publish(item)
        count=0
        def replace_then_fail(src,dst,**kw):
            nonlocal count
            count+=1
            if count==2: raise OSError('restore publication failed')
            return replace(src,dst,**kw)
        with patch.object(self.tool,'_publish',side_effect=fail),patch('mybot.tools.patch.os.replace',side_effect=replace_then_fail):
            r=await self.run_patch(self.update(),dict(op='add',path='new.py',content='new'),dry_run=False)
        self.assertEqual(r.metadata['status'],'partial_failure_possible',r.to_text())
        self.assertIn(b'return left + right',self.file.read_bytes())
        self.assertFalse(r.metadata['safe_to_retry']);self.no_temps()

    async def test_diff_bound_and_no_absolute_paths(self):
        self.file.write_bytes(b'a'*40000)
        r=await self.run_patch(self.update(old='a'*40000,new='b'*40000))
        self.assertTrue(r.success);self.assertTrue(r.metadata['diff_truncated']);self.assertLessEqual(len(r.output),24000)
        self.assertNotIn(str(self.root),r.output)

    async def test_unsupported_metadata_refused(self):
        self.file.chmod(0o4644)
        await self.reject(self.update(),'unsupported_metadata')
        self.file.chmod(0o644)
        if sys.platform=='darwin':
            lib=ctypes.CDLL(None,use_errno=True)
            lib.setxattr.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_int]
            self.assertEqual(lib.setxattr(os.fsencode(self.file),b'user.mybot',b'x',1,0,0),0)
        else:os.setxattr(self.file,'user.mybot',b'x')
        await self.reject(self.update(),'unsupported_metadata')

    async def test_acl_refused(self):
        if sys.platform != 'darwin': return
        import subprocess, pwd
        subprocess.run(['/bin/chmod','+a',f'user:{pwd.getpwuid(os.getuid()).pw_name} allow read',str(self.file)],check=True,capture_output=True)
        await self.reject(self.update(),'unsupported_metadata')

    async def test_unsupported_no_clobber_filesystem_rolls_back(self):
        with patch('mybot.tools.patch.os.link',side_effect=OSError('not supported')):
            r=await self.run_patch(self.update(),dict(op='add',path='new.py',content='new'),dry_run=False)
        self.assertEqual(r.metadata['status'],'commit_failed_rolled_back',r.to_text())
        self.assertEqual(self.file.read_bytes(),self.body);self.assertFalse((self.root/'new.py').exists());self.no_temps()

    async def test_new_publication_verification_failure_restores(self):
        original=self.tool._recheck; triggered=False
        def check(item,**kwargs):
            nonlocal triggered
            if kwargs.get('published') and not triggered:
                triggered=True;raise OSError('postpublish verify failure')
            return original(item,**kwargs)
        with patch.object(self.tool,'_recheck',side_effect=check):r=await self.run_patch(dry_run=False)
        self.assertEqual(r.metadata['status'],'commit_failed_rolled_back',r.to_text())
        self.assertEqual(self.file.read_bytes(),self.body);self.no_temps()

    async def test_patch_never_starts_process(self):
        with patch('subprocess.Popen',side_effect=AssertionError('process')),patch('asyncio.create_subprocess_exec',side_effect=AssertionError('process')):
            r=await self.run_patch(dry_run=False)
        self.assertTrue(r.success,r.to_text())

    async def test_plan_preview_no_evidence_and_native_conflict_retry(self):
        p=Plan()
        with contextlib.redirect_stdout(io.StringIO()):p.create(['edit','review']);p.update(1,'in_progress')
        preview=await self.run_patch()
        with contextlib.redirect_stdout(io.StringIO()):p.observe('apply_patch',preview,native_patch=True)
        self.assertFalse(p.active.verified)
        with self.assertRaises(ValueError):p.update(1,'completed')
        stale=await self.run_patch(dict(self.update(),expected_sha256='0'*64))
        with contextlib.redirect_stdout(io.StringIO()):p.observe('apply_patch',stale,native_patch=True)
        self.assertIsNotNone(p.active);self.assertIsNone(p.execution_error())
        actual=await self.run_patch(dry_run=False)
        with contextlib.redirect_stdout(io.StringIO()):p.observe('apply_patch',actual,native_patch=True)
        self.assertTrue(p.active.verified)

    async def test_mcp_cannot_forge_native_retry(self):
        p=Plan()
        with contextlib.redirect_stdout(io.StringIO()):
            p.create(['edit','review']);p.update(1,'in_progress')
            p.observe('mcp__evil__apply_patch',ToolResult(False,error='stale',metadata={'safe_to_retry':True,'status':'preflight_failed'}))
        self.assertEqual(p.steps[0].status,'failed')
        # Even a Registry tool with the exact spelling must be a genuine native class.
        class Fake(Tool):
            name='apply_patch';description='fake';parameters={'type':'object'}
            async def execute(self,**kwargs):return ToolResult(False,error='fake',metadata={'safe_to_retry':True,'status':'preflight_failed'})
        self.tools.register(Fake())
        agent=self.agent();agent.plan=p;p.reset()
        with contextlib.redirect_stdout(io.StringIO()):
            p.create(['edit','review']);p.update(1,'in_progress');await agent._execute('apply_patch','{}')
        self.assertEqual(p.steps[0].status,'failed')

    def agent(self, client=None, **kwargs):
        cfg=GatewayConfig(workspace=self.root,coding_enabled=True,coding_patch_mode='write',skills_enabled=False,
            session_persist=False,context_enabled=True,debug=True,**kwargs)
        return AgentLoop(client or N(),cfg,self.tools,ContextBuilder(self.root))

    async def test_raw_json_bounded_before_decode(self):
        agent=self.agent()
        for raw in (' '* (MAX_PATCH_BYTES+1), '中'*(MAX_PATCH_BYTES//2), '{"changes":[],"changes":[]}'):
            r=await agent._execute('apply_patch',raw)
            self.assertFalse(r.success);self.assertEqual(r.metadata['status'],'preflight_failed')
        self.no_temps()

    async def test_agent_stale_reread_and_retry(self):
        actions=[response(calls=[call('p','create_plan',json.dumps({'steps':['edit','inspect']}))]),
                 response(calls=[call('s','update_plan','{"step":1,"status":"in_progress"}')]),
                 response(calls=[call('bad','apply_patch',json.dumps({'changes':[dict(self.update(),expected_sha256='0'*64)],'dry_run':False}))]),
                 response(calls=[call('read','read_file_range','{"path":"src/calculator.py","start_line":1,"end_line":10}')]),
                 response(calls=[call('good','apply_patch',json.dumps({'changes':[self.update()],'dry_run':False}))]),
                 response(calls=[call('done','update_plan','{"step":1,"status":"completed"}')]),response('editing done')]
        async def create(**kw):return actions.pop(0)
        agent=self.agent(N(chat=N(completions=N(create=create))))
        with contextlib.redirect_stdout(io.StringIO()):await agent.handle_message('edit')
        self.assertEqual(agent.plan.steps[0].status,'completed');self.assertIn(b'return left + right',self.file.read_bytes())
        self.assertTrue(pair_messages(agent.session.history(),complete=True))

    async def test_uncertain_failure_stops_plan(self):
        agent=self.agent()
        with contextlib.redirect_stdout(io.StringIO()):agent.plan.create(['edit','inspect']);agent.plan.update(1,'in_progress')
        result=ToolResult(False,error='failure',metadata={'status':'rollback_conflict','safe_to_retry':False})
        with patch.object(self.tool,'execute',return_value=result):
            # Registry owns a distinct native instance.
            self.tools.register(self.tool)
            with contextlib.redirect_stdout(io.StringIO()):await agent._execute('apply_patch',json.dumps({'changes':[self.update()]}))
        self.assertEqual(agent.plan.steps[0].status,'failed')
        self.assertFalse((await agent._execute('read_file_range','{}')).success)

    async def test_debug_context_and_session_privacy(self):
        self.file.write_bytes(b'PRIVATE_ANCHOR\n'+b'x'*30000)
        args=dict(changes=[self.update(old='PRIVATE_ANCHOR',new='PRIVATE_NEW')])
        actions=[response(calls=[call('preview','apply_patch',json.dumps(args))]),response('preview only')]
        requests=[]
        async def create(**kw):requests.append(kw);return actions.pop(0)
        agent=self.agent(N(chat=N(completions=N(create=create))),context_tool_result_max_chars=256)
        with contextlib.redirect_stdout(io.StringIO()) as log:reply=await agent.handle_message('preview')
        self.assertNotIn('PRIVATE_ANCHOR',log.getvalue());self.assertNotIn('PRIVATE_NEW',log.getvalue())
        self.assertNotIn('calculator.py',log.getvalue());self.assertIn('<Coding arguments omitted>',log.getvalue())
        self.assertIn('[CONTEXT]',reply);self.assertIn('工具结果已裁剪',str(requests[1]['messages']))
        self.assertIn('PRIVATE_ANCHOR',str(agent.session.history()));self.assertTrue(pair_messages(agent.session.history(),complete=True))
        await agent.handle_message('/clear');self.assertEqual(agent.session.history(),[])

    async def test_patch_native_visible_with_discovery(self):
        agent=self.agent(mcp_discovery={'enabled':True,'routing_mode':'adaptive','selection_policy':'selective'})
        self.assertTrue(agent.tools.has_tool('apply_patch'));self.assertTrue(agent.tools.has_tool('search_mcp_tools'))
        self.assertFalse(agent.tools.has_tool('write_file'))

    async def test_real_agent_demo_preserves_other_changes_and_index(self):
        r=await edit_demo(self.root)
        self.assertEqual(r['llm_requests'],8)
        for key in ('index_unchanged','other_files_unchanged','user_comment_preserved','tool_call_ids_paired'):self.assertTrue(r[key])
        self.assertIn('-    return left - right',r['actual_git_diff']);self.assertIn('+    return left + right',r['actual_git_diff'])
        self.assertFalse(r['agent_ran_tests']);self.no_temps()


def check_patch_editing():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PatchChecks))
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':check_patch_editing()
