"""Offline receipt contracts and deterministic synthetic comparison; no HTTP client.

--comparison PATH exports all preregistered synthetic conditions (including negatives).
These are protocol fault injections, never an estimate of real model performance.
"""
import asyncio
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

from jsonschema import Draft202012Validator
from mybot.tools.patch import ApplyPatchTool, sha, parse_arguments
from mybot.tools import build_default_tool_registry
from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.coding_controller import CodingTaskController, AutonomySettings
from mybot.agent.change_journal import ChangeJournal
from mybot.agent.git_workflow import GitBaseline, GitWorkflowSettings
from mybot.config import GatewayConfig
from mybot.evaluation.coding_metrics import CodingTrace, BenchmarkAgent
from mybot.evaluation.coding_campaign import strict_success
from mybot.evaluation.tool_agent import pair_messages
from scripts.check_session import response, call, assert_pairs
from scripts.check_tool_verification_reliability import fixture, changes, approve, TEST_ARGV

SCENARIOS = ('normal', 'multi_file', 'complex_text', 'regenerated_changes_corrupt',
             'stale', 'metadata', 'cancelled', 'tool_budget', 'write_budget',
             'unsafe_path', 'corrupt_confirmation', 'publication_uncertain')
BUDGET = {'max_model_requests': 8, 'max_tool_calls': 8,
          'max_patch_write_attempts': 2, 'max_command_attempts': 2, 'max_task_seconds': 60}


def init(root):
    fixture(root)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Receipt Test', '-c',
                    'user.email=receipt@example.invalid', 'commit', '-qm', 'fixture'], check=True, capture_output=True)


async def synthetic_case(mode, scenario):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve(); init(root)
        candidate = mode == 'receipt'
        tools = build_default_tool_registry(root, coding_enabled=True, patch_mode='write',
            preview_receipt=candidate, command={'mode': 'macos_readonly'}, command_approval_provider=approve)
        tool = tools.get_tool('apply_patch')
        original_publish = tool._publish
        if scenario == 'publication_uncertain':
            def uncertain(item):
                original_publish(item)
                (root / item.path).write_text('external concurrent writer\n')
                raise OSError('injected publication fault')
            tool._publish = uncertain
        planned = changes(root)
        if scenario == 'multi_file':
            (root / 'other.py').write_text('OLD = 1\n')
            planned.append({'op': 'update', 'path': 'other.py', 'expected_sha256': sha((root / 'other.py').read_bytes()),
                            'edits': [{'old_text': 'OLD = 1', 'new_text': 'OLD = 2'}]})
        if scenario == 'complex_text':
            complex_text = '\n# unicode 中文 "quotes" \\ literal\\n\n'
            (root / 'value.py').write_text((root / 'value.py').read_text() + complex_text)
            planned = changes(root)
            planned[0]['edits'].append({'old_text': complex_text, 'new_text': complex_text.replace('quotes', 'updated')})
        if scenario == 'unsafe_path': planned = [{'op': 'add', 'path': '.env', 'content': 'synthetic-secret'}]
        trace = CodingTrace(); trace.workspace = root; trace.names = {t.name for t in tools.iter_tools()}
        trace.paths = {'value.py', 'other.py'}
        counters = {'requests': 0}
        async def create(**kwargs):
            step = counters['requests']; counters['requests'] += 1
            assert_pairs(unittest.TestCase(), kwargs['messages'])
            if step == 0:
                args = {'dry_run': True, 'changes': planned}
            elif step == 1:
                if scenario == 'cancelled': raise asyncio.CancelledError()
                if scenario == 'stale': (root / 'value.py').write_text('external\n')
                if scenario == 'metadata': os.chmod(root / 'value.py', 0o400)
                if scenario == 'tool_budget': agent.coding_controller.tool_calls = BUDGET['max_tool_calls']
                if scenario == 'write_budget': agent.coding_controller.patch_write_attempts = BUDGET['max_patch_write_attempts']
                meta = json.loads(kwargs['messages'][-1]['content'].split('metadata=', 1)[1])
                args = ({'dry_run': False, 'preview_receipt': meta['preview_receipt']} if candidate
                        else {'dry_run': False, 'changes': copy.deepcopy(planned)})
                if scenario == 'corrupt_confirmation':
                    args = {'dry_run': False, 'preview_receipt': '0' * 64} if candidate else {'dry_run': False, 'changes': []}
                if scenario == 'regenerated_changes_corrupt' and not candidate:
                    return response(calls=[call('commit', 'apply_patch', '{"dry_run":false,"changes":[')])
            elif step == 2:
                return response(calls=[call('test', 'run_command', json.dumps({'argv': TEST_ARGV}))])
            else: return response('done')
            return response(calls=[call(str(step), 'apply_patch', json.dumps(args))])
        config = GatewayConfig(workspace=root, coding_enabled=True, coding_patch_mode='write',
            coding_preview_receipt=candidate, coding_command={'mode': 'macos_readonly'},
            coding_autonomy={'enabled': True, **BUDGET}, coding_git_workflow={'enabled': True},
            context_enabled=False, skills_enabled=False, session_persist=False, mcp_enabled=False, max_react_steps=8)
        agent = BenchmarkAgent(N(chat=N(completions=N(create=create))), config, tools, ContextBuilder(root), trace=trace)
        with contextlib.redirect_stdout(io.StringIO()):
            try: await agent.handle_message('Repair double using public unittest contract.')
            except asyncio.CancelledError: pass
        report = agent.last_coding_report
        assert tool._receipt is None and tool._receipt_scope is None
        committed = sum(e.get('patch_committed', False) for e in trace.events)
        events = [e for e in trace.events if e.get('event') == 'tool']
        invalid = sum(e.get('error') == 'invalid_arguments' for e in events)
        # Count formal argument parsing failure exactly once (already included in trace).
        verified = report['state'] == 'verified'
        contract = (root / 'value.py').read_text().find('return value * 2') >= 0
        synthetic_contract = verified and contract and trace.protocol_valid()
        if scenario == 'multi_file': synthetic_contract &= (root / 'other.py').read_text() == 'OLD = 2\n'
        # Preserve the original Strict eligibility gate: offline public contracts have no Live/private Judge.
        strict = strict_success({'mode': 'offline_synthetic', 'results': []})
        paired = pair_messages(agent.session.history(), complete=True)
        assert paired
        security_codes = {'stale_file_hash', 'sensitive_path_denied', 'path_outside_workspace',
            'symlink_denied', 'hardlink_denied', 'unsupported_ownership', 'unsupported_metadata',
            'patch_write_disabled', 'target_exists', 'path_changed'}
        capability_errors = {'malformed_receipt', 'unknown_receipt', 'expired_receipt', 'consumed_receipt',
            'wrong_attempt', 'metadata_changed', 'patch_write_disabled', 'stale_file_hash'}
        security_rejections = sum(e['name'] == 'apply_patch' and not e['success'] and
            (e.get('error') in security_codes or e.get('receipt_error_category') in capability_errors) for e in events)
        return {'synthetic': True, 'scenario': scenario, 'mode': mode, 'state': report['state'],
            'patch_committed': committed, 'formal_commit_attempts': sum(e.get('patch_write', False) for e in events)
                + int(scenario == 'regenerated_changes_corrupt' and not candidate),
            'invalid_arguments': invalid, 'tool_calls': len(events),
            'logical_model_requests': counters['requests'], 'physical_model_requests_synthetic': counters['requests'],
            'actual_http_requests': 0, 'controller_verified': int(verified), 'strict_success': int(strict), 'strict_eligible': False, 'synthetic_contract_success': int(synthetic_contract),
            'security_rejections': security_rejections,
            'tool_failures': sum(not e['success'] for e in events),
            'execution_uncertain': int(report['state'] == 'execution_uncertain'),
            'receipt_destroyed': tool._receipt is None, 'tool_ids_paired': paired}


async def comparison():
    rows = [await synthetic_case(mode, scenario) for scenario in SCENARIOS for mode in ('legacy', 'receipt')]
    totals = {}
    for mode in ('legacy', 'receipt'):
        group = [r for r in rows if r['mode'] == mode]
        keys = ('patch_committed', 'formal_commit_attempts', 'invalid_arguments', 'tool_calls',
                'logical_model_requests', 'physical_model_requests_synthetic', 'controller_verified',
                'strict_success', 'synthetic_contract_success', 'security_rejections', 'tool_failures', 'execution_uncertain')
        totals[mode] = {k: sum(r[k] for r in group) for k in keys}
        totals[mode]['tasks'] = len(group)
        totals[mode]['task_commit_rate'] = totals[mode]['patch_committed'] / len(group)
        attempts = totals[mode]['formal_commit_attempts']
        totals[mode]['formal_commit_rate'] = totals[mode]['patch_committed'] / attempts if attempts else None
    return {'synthetic': True, 'actual_http_requests': 0, 'actual_pty_yes': 0,
            'budget_per_task': BUDGET, 'order': 'scenario order, legacy then receipt',
            'denominator': 'all 12 preregistered conditions including failures, cancellation and budget exhaustion',
            'security_rejection_definition': 'Patch capability/path/version/permission rejection; excludes argument errors, failed tests and uncertain publication (reported separately).',
            'strict_definition': 'Unmodified coding_campaign.strict_success; offline_synthetic is ineligible (no Live/private Judge).',
            'synthetic_contract_definition': 'original Controller verified AND current-hash native test evidence AND public contract repaired; not Strict Success',
            'limitation': 'Deterministic protocol fault injection; no real-model success-rate or cost inference.',
            'conditions': list(SCENARIOS), 'totals': totals, 'rows': rows}


class ReceiptChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); init(self.root)
        self.tool = ApplyPatchTool(self.root, patch_mode='write', preview_receipt=True)
        self.tool.begin_receipt_scope()

    async def preview(self, changes_=None):
        result = await self.tool.execute(dry_run=True, changes=changes_ or changes(self.root))
        self.assertTrue(result.success, result.to_text())
        return result.metadata['preview_receipt']

    async def commit(self, token):
        return await self.tool.execute(dry_run=False, preview_receipt=token)

    async def reject(self, token, category=None):
        before = {str(p): p.read_bytes() for p in self.root.glob('*.py')}
        result = await self.commit(token)
        self.assertFalse(result.success)
        if category: self.assertEqual(result.metadata['receipt_error_category'], category)
        self.assertFalse(result.metadata['safe_to_retry'])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.glob('*.py')})
        return result

    async def test_preview_opaque(self):
        token = await self.preview(); self.assertRegex(token, '^[a-f0-9]{64}$')
        self.assertNotIn('value', token); self.assertNotIn('return', token)

    async def test_preview_no_disk_write(self):
        before = (self.root / 'value.py').stat(); await self.preview()
        self.assertEqual(before, (self.root / 'value.py').stat())
        self.assertEqual(list(self.root.glob('.mybot-patch-*')), [])

    async def test_explicit_commit(self):
        result = await self.commit(await self.preview())
        self.assertTrue(result.success); self.assertTrue(result.metadata['receipt_commit_success'])
        self.assertTrue(result.metadata['preview_to_commit_consistent']); self.assertTrue(result.metadata['file_revision_verified'])

    async def test_no_preview(self): await self.reject('a' * 64, 'unknown_receipt')
    async def test_forged(self):
        await self.preview(); await self.reject('a' * 64, 'unknown_receipt')
    async def test_consumed(self):
        token = await self.preview(); self.assertTrue((await self.commit(token)).success)
        await self.reject(token, 'consumed_receipt')
    async def test_new_preview_revokes(self):
        token = await self.preview(); await self.preview(); await self.reject(token, 'unknown_receipt')
    async def test_wrong_attempt(self):
        token = await self.preview(); self.tool.begin_receipt_scope(); await self.reject(token, 'wrong_attempt')
    async def test_end_scope(self):
        token = await self.preview(); self.tool.end_receipt_scope(); self.assertIsNone(self.tool._receipt)
        await self.reject(token, 'wrong_attempt')
    async def test_cross_workspace_instance(self):
        token = await self.preview()
        with tempfile.TemporaryDirectory() as tmp:
            other = ApplyPatchTool(Path(tmp), patch_mode='write', preview_receipt=True); other.begin_receipt_scope()
            self.assertEqual((await other.execute(dry_run=False, preview_receipt=token)).error, 'unknown_receipt')
    async def test_workspace_rebound(self):
        token = await self.preview()
        with tempfile.TemporaryDirectory() as tmp:
            self.tool.workspace = Path(tmp); await self.reject(token, 'wrong_attempt')
    async def test_expiry(self):
        token = await self.preview()
        with patch('mybot.tools.patch.time.monotonic', return_value=self.tool._receipt.expires + 1):
            await self.reject(token, 'expired_receipt')
    async def test_restart_no_recovery(self):
        token = await self.preview(); self.tool = ApplyPatchTool(self.root, patch_mode='write', preview_receipt=True)
        self.tool.begin_receipt_scope(); await self.reject(token, 'unknown_receipt')
    async def test_stale_bytes(self):
        token = await self.preview(); (self.root / 'value.py').write_text('external\n')
        await self.reject(token, 'stale_file_hash')
    async def test_restored_bytes_version(self):
        token = await self.preview(); p = self.root / 'value.py'; body = p.read_bytes()
        p.write_text('external\n'); p.write_bytes(body); await self.reject(token, 'metadata_changed')
    async def test_same_bytes_new_inode(self):
        token = await self.preview(); p = self.root / 'value.py'; other = self.root / 'swap.py'
        other.write_bytes(p.read_bytes()); os.replace(other, p); await self.reject(token, 'metadata_changed')
    async def test_mode_changed(self):
        token = await self.preview(); os.chmod(self.root / 'value.py', 0o400)
        await self.reject(token, 'metadata_changed')
    async def test_symlink(self):
        token = await self.preview(); p = self.root / 'value.py'; p.rename(self.root / 'target.py'); p.symlink_to('target.py')
        await self.reject(token)
    async def test_parent_replaced(self):
        d = self.root / 'src'; d.mkdir(); (d / 'x.py').write_text('old\n')
        c = [{'op': 'update', 'path': 'src/x.py', 'expected_sha256': sha(b'old\n'), 'edits': [{'old_text': 'old', 'new_text': 'new'}]}]
        token = await self.preview(c); d.rename(self.root / 'saved'); d.mkdir(); (d / 'x.py').write_text('old\n')
        await self.reject(token, 'metadata_changed'); self.assertEqual((d / 'x.py').read_text(), 'old\n')
    async def test_multifile_all_checked(self):
        c = changes(self.root) + [{'op': 'add', 'path': 'added.py', 'content': 'new\n'}]
        token = await self.preview(c); (self.root / 'added.py').write_text('external\n')
        await self.reject(token); self.assertIn('value + 1', (self.root / 'value.py').read_text())
    async def test_add_success(self):
        token = await self.preview([{'op': 'add', 'path': 'added.py', 'content': 'new\n'}])
        self.assertTrue((await self.commit(token)).success); self.assertEqual((self.root / 'added.py').read_text(), 'new\n')
    async def test_snapshot_immutable(self):
        c = changes(self.root); token = await self.preview(c); c[0]['edits'][0]['new_text'] = 'INJECTED'
        self.assertTrue((await self.commit(token)).success); self.assertNotIn('INJECTED', (self.root / 'value.py').read_text())
    async def test_original_pipeline(self):
        token = await self.preview()
        with patch.object(self.tool, '_preflight', wraps=self.tool._preflight) as pre, patch.object(self.tool, '_stage', wraps=self.tool._stage) as stage, patch.object(self.tool, '_publish', wraps=self.tool._publish) as pub, patch.object(self.tool, '_recheck', wraps=self.tool._recheck) as check:
            self.assertTrue((await self.commit(token)).success)
            self.assertEqual(pre.call_count, 1); self.assertEqual(stage.call_count, 1); self.assertEqual(pub.call_count, 1)
            self.assertGreaterEqual(check.call_count, 3)
    async def test_write_failure_rolled_back(self):
        c = changes(self.root) + [{'op': 'add', 'path': 'added.py', 'content': 'new\n'}]
        token = await self.preview(c); original = self.tool._publish
        def fail(item):
            if item.op == 'add': raise OSError('injected')
            original(item)
        with patch.object(self.tool, '_publish', side_effect=fail):
            result = await self.commit(token)
        self.assertFalse(result.success); self.assertEqual(result.metadata['status'], 'commit_failed_rolled_back')
        self.assertIn('value + 1', (self.root / 'value.py').read_text()); self.assertFalse((self.root / 'added.py').exists())
        await self.reject(token, 'consumed_receipt')
    async def test_uncertain_stops_controller(self):
        tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write', preview_receipt=True)
        tools.register(self.tool); controller = CodingTaskController(AutonomySettings(enabled=True), tools)
        token = await self.preview(); original = self.tool._publish
        def race(item): original(item); (self.root / item.path).write_text('external'); raise OSError('fault')
        with patch.object(self.tool, '_publish', side_effect=race): result = await self.commit(token)
        controller.observe('apply_patch', {'dry_run': False, 'preview_receipt': token}, result)
        self.assertEqual(controller.state, 'execution_uncertain'); self.assertEqual(result.metadata['receipt_error_category'], 'cleanup_uncertain')
    async def test_python_c_not_revision_evidence(self):
        tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write', preview_receipt=True,
            command={'mode': 'macos_readonly'}, command_approval_provider=approve)
        tools.register(self.tool); c = CodingTaskController(AutonomySettings(enabled=True), tools)
        token = await self.preview(); args = {'dry_run': False, 'preview_receipt': token}
        c.before_tool('apply_patch', args); c.observe('apply_patch', args, await self.commit(token))
        command = tools.get_tool('run_command'); command.execution_guard = c.command_guard
        args = {'argv': ['python', '-c', 'print("Ran 99 tests in 0.01s\\nOK")']}
        c.before_tool('run_command', args); result = await command.execute(**args); c.observe('run_command', args, result)
        self.assertTrue(result.success); self.assertFalse(c.can_verify()); self.assertEqual(c.tests_passed_after_last_patch, 0)

    async def test_mutation_during_stage_stops_all(self):
        token = await self.preview(); original = self.tool._stage
        def race(item):
            original(item); (self.root / item.path).write_text('external writer')
        with patch.object(self.tool, '_stage', side_effect=race), patch.object(self.tool, '_publish', wraps=self.tool._publish) as publish:
            result = await self.commit(token); self.assertFalse(result.success); publish.assert_not_called()
        self.assertEqual((self.root / 'value.py').read_text(), 'external writer')
        self.assertEqual(list(self.root.glob('.mybot-patch-*')), [])

    async def test_tampered_receipt_consumes_active(self):
        token = await self.preview(); await self.reject('g' * 64, 'malformed_receipt')
        await self.reject(token, 'consumed_receipt')

    async def test_token_not_in_evidence(self):
        token = await self.preview(); result = await self.commit(token)
        trace = CodingTrace(); trace.tool('apply_patch', {'dry_run': False, 'preview_receipt': token}, result, 0)
        self.assertNotIn(token, json.dumps(trace.events)); self.assertNotIn('return value', json.dumps(trace.events))
    async def test_history_redaction(self):
        token = await self.preview(); secret = 'synthetic-api-key'
        history = [{'role': 'assistant', 'tool_calls': [{'id': '1', 'function': {'name': 'apply_patch', 'arguments': json.dumps({'changes': secret})}}]}, {'role': 'tool', 'tool_call_id': '1', 'content': token + secret}]
        clean = self.tool.redact_receipt_history(history); self.assertNotIn(token, json.dumps(clean)); self.assertNotIn(secret, json.dumps(clean))
        self.assertIn(token, json.dumps(history)); assert_pairs(self, clean)
    async def test_oversize_token(self): await self.reject('x' * 300000, 'malformed_receipt')
    async def test_nonstring_token(self): await self.reject({'secret': 'synthetic'}, 'malformed_receipt')
    async def test_sensitive_path(self):
        result = await self.tool.execute(dry_run=True, changes=[{'op': 'add', 'path': '.env', 'content': 'synthetic'}])
        self.assertFalse(result.success); self.assertIsNone(self.tool._receipt); self.assertNotIn('synthetic', result.to_text())
    async def test_path_escape(self):
        result = await self.tool.execute(changes=[{'op': 'add', 'path': '../escape.py', 'content': 'x'}])
        self.assertFalse(result.success); self.assertIsNone(self.tool._receipt)
    async def test_preview_cannot_grant_write(self):
        self.tool.patch_mode = 'preview'; token = await self.preview(); await self.reject(token, 'patch_write_disabled')
    async def test_legacy_default(self):
        legacy = ApplyPatchTool(self.root, patch_mode='write'); c = changes(self.root)
        self.assertNotIn('preview_receipt', (await legacy.execute(changes=c)).metadata)
        self.assertTrue((await legacy.execute(changes=c, dry_run=False)).success)
    async def test_receipt_mode_forbids_full_write(self):
        await self.preview(); result = await self.tool.execute(dry_run=False, changes=changes(self.root))
        self.assertFalse(result.success); self.assertFalse(result.metadata['safe_to_retry'])
    async def test_schema(self):
        schema = self.tool.to_schema()['function']['parameters']; Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertTrue(validator.is_valid({'dry_run': False, 'preview_receipt': 'a' * 64}))
        self.assertFalse(validator.is_valid({'dry_run': False, 'preview_receipt': 'a' * 64, 'changes': changes(self.root)}))
    async def test_strict_raw_parsing(self):
        for raw in ('{"dry_run":false,"dry_run":true}', '{"preview_receipt":', '[1]', '{"x":NaN}'):
            with self.assertRaises(ValueError): parse_arguments(raw)
    async def test_journal_actual_commit(self):
        journal = ChangeJournal(await GitBaseline.capture(self.root), self.tool, GitWorkflowSettings(enabled=True))
        self.tool.observer = journal; token = await self.preview(); self.assertEqual(journal.entries, {})
        result = await self.commit(token); self.assertTrue(result.success, result.to_text())
        self.assertEqual(journal.revision, 1); self.assertEqual(set(journal.entries), {'value.py'})
        self.assertEqual(journal.entries['value.py'].final_sha256, result.metadata['after_sha256']['value.py'])
    async def test_journal_rejects_ownership(self):
        journal = ChangeJournal(await GitBaseline.capture(self.root), self.tool, GitWorkflowSettings(enabled=True))
        self.tool.observer = journal; token = await self.preview(); journal.close()
        await self.reject(token); self.assertEqual(journal.entries, {})
    async def test_controller_revision_once(self):
        tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write', preview_receipt=True); tools.register(self.tool)
        c = CodingTaskController(AutonomySettings(enabled=True), tools)
        args = {'changes': changes(self.root), 'dry_run': True}; result = await self.tool.execute(**args); c.observe('apply_patch', args, result)
        self.assertEqual(c.current_revision, 0)
        args = {'dry_run': False, 'preview_receipt': result.metadata['preview_receipt']}
        self.assertTrue(c.before_tool('apply_patch', args)); c.observe('apply_patch', args, await self.tool.execute(**args))
        self.assertEqual(c.current_revision, 1); self.assertEqual(c.patch_write_attempts, 1); self.assertFalse(c.can_verify())
    async def test_controller_batch_budget(self):
        tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write', preview_receipt=True); tools.register(self.tool)
        c = CodingTaskController(AutonomySettings(enabled=True, max_patch_write_attempts=1), tools); c.patch_write_attempts = 1
        token = await self.preview(); self.assertFalse(c.before_batch([call('1', 'apply_patch', json.dumps({'dry_run': False, 'preview_receipt': token}))]))
        self.assertEqual(c.current_revision, 0)
    async def test_loop_completed_scope_and_session_disk(self):
        captured = []
        async def create(**kwargs):
            if not captured:
                captured.append(True); return response(calls=[call('1', 'apply_patch', json.dumps({'changes': changes(self.root)}))])
            captured.append(json.loads(kwargs['messages'][-1]['content'].split('metadata=', 1)[1])['preview_receipt']); return response('done')
        tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write', preview_receipt=True)
        cfg = GatewayConfig(workspace=self.root, coding_enabled=True, coding_patch_mode='write', coding_preview_receipt=True,
            session_persist=True, session_path=self.root.parent / (self.root.name + '-session.json'), skills_enabled=False, context_enabled=False)
        self.addCleanup(lambda: cfg.session_path.unlink(missing_ok=True))
        agent = AgentLoop(N(chat=N(completions=N(create=create))), cfg, tools, ContextBuilder(self.root))
        await agent.handle_message('preview'); token = captured[-1]
        self.assertNotIn(token, cfg.session_path.read_text()); self.assertNotIn(token, json.dumps(agent.session.history()))
        self.assertIsNone(tools.get_tool('apply_patch')._receipt)
        await agent.handle_message('/clear'); self.assertIsNone(tools.get_tool('apply_patch')._receipt_scope)
    async def test_expired_during_preflight(self):
        token = await self.preview(); original = self.tool._preflight
        expiry = self.tool._receipt.expires
        def delayed(args, items):
            original(args, items)
            self.clock.return_value = expiry + 1
        with patch('mybot.tools.patch.time.monotonic', return_value=expiry - 1) as self.clock, patch.object(self.tool, '_preflight', side_effect=delayed):
            await self.reject(token, 'expired_receipt')

    async def test_deadline_fence_before_stage(self):
        token = await self.preview()
        def stop(): raise ValueError('receipt_controller_stopped')
        self.tool.receipt_commit_guard = stop
        with patch.object(self.tool, '_stage', wraps=self.tool._stage) as stage:
            await self.reject(token); stage.assert_not_called()

    async def test_failed_preview_revokes(self):
        token = await self.preview(); result = await self.tool.execute(changes=[])
        self.assertFalse(result.success); await self.reject(token, 'unknown_receipt')

    async def test_no_active_scope(self):
        self.tool.end_receipt_scope()
        result = await self.tool.execute(changes=changes(self.root))
        self.assertFalse(result.success); self.assertIsNone(self.tool._receipt)

    async def test_malformed_raw_revokes_without_guessing(self):
        token = await self.preview()
        tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write', preview_receipt=True)
        tools.register(self.tool)
        agent = AgentLoop(N(), GatewayConfig(workspace=self.root, skills_enabled=False), tools, ContextBuilder(self.root))
        result = await agent._execute_tool('apply_patch', '{"dry_run":false,')
        self.assertEqual(result.metadata['failure_phase'], 'argument_parsing')
        self.assertFalse(result.metadata['safe_to_retry']); await self.reject(token, 'unknown_receipt')

    async def test_loop_timeout_cleanup(self):
        seen = []
        async def create(**kwargs):
            if not seen:
                seen.append(True); return response(calls=[call('1', 'apply_patch', json.dumps({'changes': changes(self.root)}))])
            self.assertIsNotNone(tool._receipt)
            raise TimeoutError('synthetic timeout')
        tools = build_default_tool_registry(self.root, coding_enabled=True, patch_mode='write', preview_receipt=True)
        tool = tools.get_tool('apply_patch')
        agent = AgentLoop(N(chat=N(completions=N(create=create))), GatewayConfig(workspace=self.root, skills_enabled=False,
            session_persist=False, context_enabled=False), tools, ContextBuilder(self.root))
        reply = await agent.handle_message('preview then timeout')
        self.assertIsInstance(reply, str); self.assertEqual(len(seen), 1)
        self.assertIsNone(tool._receipt); self.assertIsNone(tool._receipt_scope)
        self.assertIn('value + 1', (self.root / 'value.py').read_text())

    async def test_failover_never_replays_commit(self):
        from dataclasses import replace
        from mybot.evaluation.coding_failover import FailoverCodingClient
        from mybot.evaluation.coding_live import Limits, RequestBudget
        from mybot.evaluation.coding_lifecycle import Attempt
        from scripts.check_coding_failover import client, connection
        token = await self.preview()
        with patch.object(self.tool, '_publish', wraps=self.tool._publish) as publish:
            self.assertTrue((await self.commit(token)).success)
            cfg = GatewayConfig(provider='coco', model='deepseek-v4.1-flash', api_key='synthetic', workspace=self.root)
            backup = replace(cfg, provider='coco2', model='glm-5.3-flash')
            primary = client([connection()]); secondary = client([response(calls=[call('repeat', 'apply_patch', json.dumps({'dry_run': False, 'preview_receipt': token}))])])
            adapter = FailoverCodingClient((cfg, backup), CodingTrace(), RequestBudget(Limits()), Attempt(), 'receipt-test',
                lambda config: primary if config.provider == 'coco' else secondary)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = await adapter.create(model=cfg.model, messages=[{'role': 'user', 'content': 'continue'}], tools=[self.tool.to_schema()])
                self.assertEqual(adapter.summary()['physical_model_requests'], 2)
                self.assertEqual(publish.call_count, 1)  # Model fallback itself never invokes Patch.
                args = json.loads(result.choices[0].message.tool_calls[0].function.arguments)
                self.assertFalse((await self.tool.execute(**args)).success)
                self.assertEqual(publish.call_count, 1)  # Even an explicit duplicate cannot republish.
            finally: await adapter.close()

    async def test_config_flag_validation(self):
        with self.assertRaises(ValueError): GatewayConfig(coding_preview_receipt=True)
        with self.assertRaises(ValueError): ApplyPatchTool(self.root, patch_mode='write', preview_receipt=1)
        self.assertFalse(GatewayConfig().coding_preview_receipt)
        legacy_positional = GatewayConfig(True, 'preview', {})
        self.assertFalse(legacy_positional.coding_preview_receipt)
        self.assertEqual(legacy_positional.coding_command['mode'], 'off')
    async def test_synthetic_all_conditions(self):
        data = await comparison(); self.assertEqual(len(data['rows']), 24)
        by = {(r['mode'], r['scenario']): r for r in data['rows']}
        self.assertEqual(data['actual_http_requests'], 0)
        self.assertEqual(data['totals']['legacy']['security_rejections'], 2)
        self.assertEqual(data['totals']['receipt']['security_rejections'], 4)
        self.assertEqual(data['totals']['legacy']['formal_commit_rate'], .5)
        self.assertEqual(data['totals']['receipt']['formal_commit_rate'], .5)
        self.assertEqual(by['receipt', 'normal']['synthetic_contract_success'], 1)
        self.assertEqual(by['legacy', 'normal']['synthetic_contract_success'], 1)
        self.assertEqual(by['receipt', 'regenerated_changes_corrupt']['synthetic_contract_success'], 1)
        self.assertEqual(by['legacy', 'regenerated_changes_corrupt']['synthetic_contract_success'], 0)
        for mode in ('legacy', 'receipt'):
            for scenario in SCENARIOS[4:]:
                expected = int(mode == 'legacy' and scenario == 'metadata')
                self.assertEqual(by[mode, scenario]['synthetic_contract_success'], expected, (mode, scenario))
            self.assertEqual(by[mode, 'publication_uncertain']['execution_uncertain'], 1)
            self.assertEqual(by[mode, 'cancelled']['state'], 'cancelled')
        self.assertTrue(all(r['strict_success'] == 0 and r['strict_eligible'] is False for r in data['rows']))
        self.assertTrue(all(r['receipt_destroyed'] and r['tool_ids_paired'] for r in data['rows']))


def check_patch_preview_receipt():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReceiptChecks))
    if not result.wasSuccessful(): raise AssertionError('receipt checks failed')
    return result.testsRun


if __name__ == '__main__':
    check_patch_preview_receipt()
    if '--comparison' in sys.argv:
        path = Path(sys.argv[sys.argv.index('--comparison') + 1]); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asyncio.run(comparison()), indent=2) + '\n')
