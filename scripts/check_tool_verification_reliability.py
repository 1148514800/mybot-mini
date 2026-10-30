"""Offline synthetic contracts; no historical Gold, paid client or live execution.

Run with --comparison PATH to export the deterministic two-arm experiment.
"""
import asyncio
import ast
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.coding_controller import CodingTaskController, AutonomySettings, test_runner
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from mybot.tools.patch import ApplyPatchTool
from mybot.tools.run_command import RunCommandTool
from mybot.mcp_client.approval import ApprovalDecision
from mybot.evaluation.coding_metrics import CodingTrace, failure_reason, failure_classification, FAILURE_RULE_VERSION
from mybot.evaluation.tool_agent import pair_messages
from scripts.check_session import response

BASELINE = '871510f8a682990da63448ef27ec282c376a8711'
TEST_ARGV = ['python', '-m', 'unittest', 'discover', '-s', 'tests', '-v']


def fixture(root):
    # Independent public contract, unrelated to the frozen Benchmark and its Judge.
    (root / 'tests').mkdir()
    (root / 'value.py').write_text('def double(value):\n    return value + 1\n')
    (root / 'tests/test_contract.py').write_text(
        'import unittest\nfrom value import double\n'
        'class Contract(unittest.TestCase):\n'
        '    def test_positive(self): self.assertEqual(double(3), 6)\n'
        '    def test_zero(self): self.assertEqual(double(0), 0)\n'
        '    def test_negative(self): self.assertEqual(double(-2), -4)\n')
    subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)


async def approve(_):
    # Offline unit-test provider, never an actual PTY approval.
    return ApprovalDecision.APPROVE


def registry(root, mode='host_confirm'):
    return build_default_tool_registry(root, coding_enabled=True, patch_mode='write',
        command={'mode': mode}, command_approval_provider=approve)


def changes(root, new='return value * 2'):
    return [{'op': 'update', 'path': 'value.py',
        'expected_sha256': hashlib.sha256((root / 'value.py').read_bytes()).hexdigest(),
        'edits': [{'old_text': 'return value + 1', 'new_text': new}]}]


class VerificationChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); fixture(self.root)
        self.tools = registry(self.root)
        self.c = CodingTaskController(AutonomySettings(enabled=True), self.tools)
        self.agent = AgentLoop(N(), self.cfg(), self.tools, ContextBuilder(self.root))

    def cfg(self, **extra):
        opts = dict(context_token_budget={"input_limit":160000}, workspace=self.root, coding_enabled=True, coding_patch_mode='write',
            coding_command={'mode': 'host_confirm'}, coding_autonomy={'enabled': True},
            skills_enabled=False,  mcp_enabled=False, max_react_steps=20)
        opts.update(extra)
        return GatewayConfig(**opts)

    async def native(self, name, args):
        self.assertTrue(self.c.before_tool(name, args))
        tool = self.tools.get_tool(name)
        if type(tool) is RunCommandTool: tool.execution_guard = self.c.command_guard
        result = await self.agent._execute_tool(name, args)
        self.c.observe(name, args, result)
        return result

    async def write(self, new='return value * 2'):
        args = {'dry_run': True, 'changes': changes(self.root, new)}
        self.assertTrue((await self.native('apply_patch', args)).success)
        args['dry_run'] = False
        result = await self.native('apply_patch', args)
        self.assertTrue(result.success, result.to_text())
        return result

    async def run_tests(self, argv=None):
        return await self.native('run_command', {'argv': argv or TEST_ARGV})

    async def test_preview_write_exact_structure_once(self):
        await self.write()
        self.assertEqual(self.c.committed_patches, 1)
        self.assertEqual(self.c.patch_write_attempts, 1)

    async def test_preview_does_not_write(self):
        old = (self.root / 'value.py').read_bytes()
        result = await self.native('apply_patch', {'dry_run': True, 'changes': changes(self.root)})
        self.assertTrue(result.success); self.assertEqual((self.root / 'value.py').read_bytes(), old)
        self.assertEqual(self.c.current_revision, 0)

    async def test_preview_bad_hash_feedback(self):
        args = {'dry_run': True, 'changes': changes(self.root)}
        args['changes'][0]['expected_sha256'] = 'sha256:SECRET_BODY'
        result = await self.native('apply_patch', args)
        self.assertFalse(result.success); self.assertTrue(result.metadata['safe_to_retry'])
        self.assertIn({'field': 'changes.0.expected_sha256', 'category': 'pattern'}, result.metadata['input_feedback']['issues'])
        self.assertNotIn('SECRET_BODY', result.to_text()); self.assertEqual(self.c.state, 'running')

    async def test_preview_bad_edit_type_feedback(self):
        args = {'dry_run': True, 'changes': changes(self.root)}
        args['changes'][0]['edits'][0]['new_text'] = 7
        result = await self.native('apply_patch', args)
        self.assertIn({'field': 'changes.0.edits.0.new_text', 'category': 'type'}, result.metadata['input_feedback']['issues'])

    async def test_feedback_does_not_echo_extra_key(self):
        result = await self.native('apply_patch', {'dry_run': True, 'changes': changes(self.root), '/Users/private/API_SECRET': 'SECRET_BODY'})
        self.assertNotIn('API_SECRET', result.to_text()); self.assertNotIn('SECRET_BODY', result.to_text())
        self.assertLess(len(result.to_text()), 1200)

    async def test_write_bad_parameters_stops(self):
        args = {'dry_run': False, 'changes': changes(self.root)}
        args['changes'][0]['expected_sha256'] = 'bad'
        result = await self.native('apply_patch', args)
        self.assertFalse(result.metadata['safe_to_retry']); self.assertEqual(self.c.state, 'blocked')
        self.assertEqual(self.c.committed_patches, 0)

    async def test_malformed_json_unknown_intent_stops(self):
        result = await self.native('apply_patch', '{"dry_run":true,"changes":[')
        self.assertEqual(result.metadata['failure_phase'], 'argument_parsing')
        self.assertFalse(result.metadata['safe_to_retry']); self.assertEqual(self.c.state, 'blocked')
        self.assertIn('intent_unknown', result.metadata['input_feedback']['action'])

    async def test_duplicate_json_key_stops(self):
        result = await self.native('apply_patch', '{"dry_run":true,"dry_run":false}')
        self.assertFalse(result.success); self.assertEqual(self.c.state, 'blocked')

    async def test_preview_correctable_then_repair(self):
        args = {'dry_run': True, 'changes': changes(self.root)}
        args['changes'][0]['expected_sha256'] = 'bad'
        await self.native('apply_patch', args); await self.write()
        self.assertEqual(self.c.committed_patches, 1)

    async def test_stale_preview_never_replays(self):
        args = {'dry_run': True, 'changes': changes(self.root)}
        args['changes'][0]['expected_sha256'] = '0' * 64
        result = await self.native('apply_patch', args)
        self.assertEqual(result.error, 'stale_file_hash'); self.assertEqual(self.c.stale_conflicts, 1)
        self.assertEqual(self.c.tool_calls, 1); self.assertEqual(self.c.committed_patches, 0)

    async def test_stale_write_never_replays(self):
        args = {'dry_run': False, 'changes': changes(self.root)}
        args['changes'][0]['expected_sha256'] = '0' * 64
        result = await self.native('apply_patch', args)
        self.assertFalse(result.success); self.assertEqual(self.c.patch_write_attempts, 1)
        self.assertEqual(self.c.committed_patches, 0)

    async def test_no_preview_error_cannot_verify(self):
        await self.native('apply_patch', {'dry_run': False, 'changes': []})
        self.assertFalse(self.c.can_verify()); self.c.finish(); self.assertNotEqual(self.c.state, 'verified')

    async def test_patch_text_absent_from_trace(self):
        args = {'dry_run': True, 'changes': changes(self.root, 'return "SECRET_PATCH_BODY"')}
        result = await self.native('apply_patch', args)
        trace = CodingTrace(); trace.workspace = self.root; trace.names = {'apply_patch'}
        trace.tool('apply_patch', args, result, 0)
        self.assertNotIn('SECRET_PATCH_BODY', json.dumps(trace.events))
        self.assertNotIn('SECRET_PATCH_BODY', json.dumps(self.c.snapshot()))

    async def test_unittest_current_revision_verifies(self):
        await self.write(); result = await self.run_tests()
        self.assertTrue(result.success); self.assertTrue(self.c.can_verify())
        self.c.finish(); self.assertEqual(self.c.state, 'verified')

    async def test_python_c_fake_summary_rejected(self):
        await self.write()
        result = await self.run_tests(['python', '-c', 'print("Ran 99 tests in 0.01s\\nOK")'])
        self.assertTrue(result.success); self.assertFalse(self.c.can_verify())
        self.assertEqual(self.c.test_runs, 0)
        self.assertEqual(result.metadata['revision_test_feedback']['reason'], 'unsupported_test_runner')

    async def test_no_tests_never_verified(self):
        await self.write(); self.c.finish()
        self.assertEqual(self.c.stop_reason, 'missing_current_revision_test_evidence')

    async def test_external_change_invalidates_evidence(self):
        await self.write(); await self.run_tests()
        (self.root / 'value.py').write_text('def double(value): return 99\n')
        self.assertFalse(self.c.can_verify())

    async def test_new_revision_requires_new_test(self):
        await self.write(); await self.run_tests()
        args = {'dry_run': False, 'changes': [{'op': 'update', 'path': 'value.py',
            'expected_sha256': hashlib.sha256((self.root / 'value.py').read_bytes()).hexdigest(),
            'edits': [{'old_text': 'return value * 2', 'new_text': 'return 2 * value'}]}]}
        await self.native('apply_patch', args)
        self.assertEqual(self.c.current_revision, 2); self.assertFalse(self.c.can_verify())
        await self.run_tests(); self.assertTrue(self.c.can_verify())

    async def test_failed_tests_can_repair(self):
        await self.write('return value + 2'); result = await self.run_tests()
        self.assertFalse(result.success); self.assertEqual(self.c.state, 'running')
        self.assertFalse(self.c.can_verify())
        args = {'dry_run': True, 'changes': [{'op': 'update', 'path': 'value.py',
            'expected_sha256': hashlib.sha256((self.root / 'value.py').read_bytes()).hexdigest(),
            'edits': [{'old_text': 'return value + 2', 'new_text': 'return value * 2'}]}]}
        await self.native('apply_patch', args); args['dry_run'] = False
        await self.native('apply_patch', args); await self.run_tests()
        self.assertTrue(self.c.can_verify())

    async def test_budget_exhausted_does_not_auto_finish(self):
        await self.write(); await self.run_tests(); self.c.model_requests = self.c.settings.max_model_requests
        self.assertFalse(self.c.before_request([])); self.assertFalse(self.c.can_verify())
        self.c.finish(); self.assertEqual(self.c.state, 'budget_exhausted')

    async def test_unittest_help_not_evidence(self):
        await self.write(); result = await self.run_tests(['python', '-m', 'unittest', '--help'])
        self.assertTrue(result.success); self.assertFalse(self.c.can_verify())
        self.assertIn('revision_test_feedback', result.metadata)

    def test_runner_flag_spoof_refused(self):
        self.assertIsNone(test_runner(['python', '-c', 'unittest']))
        self.assertIsNone(test_runner(['python', '-m', 'pytest', '--collect-only']))
        self.assertIsNone(test_runner(['python', '-W', 'ignore', '-m', 'unittest']))

    def test_guidance_generic_boundaries(self):
        text = self.c.instruction()
        for cue in ('False, 0, None', 'duplicate keys', 'conversion rules', 'callers', 'Retest after any edit'):
            self.assertIn(cue, text)
        self.assertNotIn('config-default-001', text); self.assertNotIn('parse-convert-001', text)

    def test_schema_full_file_hex_guidance(self):
        text = ApplyPatchTool.parameters['properties']['changes']['items']['oneOf'][0]['properties']['expected_sha256']['description']
        self.assertIn('64 hexadecimal', text); self.assertIn('metadata.file_sha256', text)

    def test_write_changes_guidance(self):
        self.assertIn('reuse the same changes structure', self.c.instruction())

    def test_hidden_pass_unverified_failure(self):
        result = {'agent_state': 'edited_unverified', 'controller': {'stop_reason': 'missing_current_revision_test_evidence'},
            'judge': {'judge_state': 'hidden_pass', 'modified_code': True, 'verified_repair_success': True}}
        before = copy.deepcopy(result)
        self.assertEqual(failure_reason(result), 'missing_current_revision_test_evidence')
        self.assertEqual(before, result)

    def test_verified_hidden_fail_remains_failure(self):
        result = {'agent_state': 'verified', 'judge': {'judge_state': 'hidden_fail', 'modified_code': True}}
        self.assertEqual(failure_reason(result), 'public_tests_only')
        self.assertFalse(result['judge'].get('verified_repair_success', False))

    def test_verified_success_null_failure(self):
        self.assertIsNone(failure_reason({'agent_state': 'verified', 'judge': {'verified_repair_success': True}}))

    def test_provider_error_precedence(self):
        self.assertEqual(failure_reason({'runtime_error': 'provider_error', 'agent_state': 'edited_unverified'}), 'provider_error')

    def test_request_budget_precedence(self):
        self.assertEqual(failure_reason({'agent_state': 'budget_exhausted', 'controller': {'stop_reason': 'max_model_requests'},
            'judge': {'verified_repair_success': True}}), 'model_request_budget')

    def test_cancelled_hidden_pass_not_success(self):
        self.assertEqual(failure_reason({'agent_state': 'cancelled', 'judge': {'verified_repair_success': True}}), 'task_cancelled')

    def test_classification_rule_version(self):
        self.assertEqual(FAILURE_RULE_VERSION, 'coding-failure-v2')

    async def test_approval_denial_still_stops(self):
        async def deny(_): return ApprovalDecision.DENY
        self.tools.get_tool('run_command').approval_provider = deny
        result = await self.run_tests()
        self.assertFalse(result.success); self.assertEqual(self.c.state, 'blocked')

    async def test_sensitive_path_still_denied(self):
        result = await self.native('apply_patch', {'dry_run': True, 'changes': [{'op': 'add', 'path': '.env', 'content': 'x'}]})
        self.assertFalse(result.success); self.assertFalse((self.root / '.env').exists())

    async def test_symlink_still_denied(self):
        (self.root / 'alias.py').symlink_to('value.py')
        args = {'dry_run': True, 'changes': changes(self.root)}; args['changes'][0]['path'] = 'alias.py'
        self.assertFalse((await self.native('apply_patch', args)).success)

    async def test_last_request_tool_call_cannot_auto_verify(self):
        policy = SyntheticPolicy('clean')
        agent = AgentLoop(policy, self.cfg(coding_autonomy={'enabled': True, 'max_model_requests': 4}),
            self.tools, ContextBuilder(self.root))
        with contextlib.redirect_stdout(io.StringIO()): await agent.handle_message('Synthetic repair and run tests')
        self.assertEqual(agent.last_coding_report['state'], 'budget_exhausted')
        self.assertEqual(agent.last_coding_report['test_passes'], 1)
        self.assertEqual(agent.last_coding_report['stop_reason'], 'max_model_requests')
        self.assertTrue(pair_messages(agent.session.history(), complete=True))

    async def test_cancellation_cannot_verify(self):
        await self.write(); await self.run_tests()
        self.c.stop('cancelled', 'task_interrupted'); self.c.finish()
        self.assertEqual(self.c.state, 'cancelled'); self.assertFalse(self.c.can_verify())

    async def test_wrong_command_start_revision_rejected(self):
        await self.write()
        tool = self.tools.get_tool('run_command')
        guard = self.c.command_guard
        def changed_revision(launch, timeout):
            limit = guard(launch, timeout)
            self.c._command_revision = 0
            return limit
        tool.execution_guard = changed_revision
        result = await tool.execute(argv=TEST_ARGV)
        self.c.observe('run_command', {'argv': TEST_ARGV}, result)
        self.assertTrue(result.success); self.assertFalse(self.c.can_verify())

    async def test_zero_test_suite_not_evidence(self):
        await self.write(); (self.root / 'tests/test_contract.py').write_text('import unittest\n')
        result = await self.run_tests()
        self.assertTrue(result.metadata['completed'])
        self.assertIn(result.metadata['exit_code'], (0, 5))  # Python versions differ for empty discovery.
        self.assertEqual(self.c.test_passes, 0); self.assertFalse(self.c.can_verify())

    async def test_preview_missing_field_safe_feedback(self):
        args = {'dry_run': True, 'changes': changes(self.root)}
        del args['changes'][0]['edits']
        result = await self.native('apply_patch', args)
        self.assertEqual(result.error, 'invalid_arguments'); self.assertTrue(result.metadata['safe_to_retry'])
        self.assertIn({'field': 'changes.0', 'category': 'required'}, result.metadata['input_feedback']['issues'])

    async def test_feedback_bounded_many_invalid_fields(self):
        args = {'dry_run': True, 'changes': changes(self.root) * 8}
        for change in args['changes']: change['expected_sha256'] = 'bad'
        result = await self.native('apply_patch', args)
        self.assertLessEqual(len(result.metadata['input_feedback']['issues']), 4)

    def test_synthetic_fixture_is_public_only(self):
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['.git', 'tests', 'value.py'])
        self.assertNotIn('hidden', (self.root / 'tests/test_contract.py').read_text())

    def test_no_new_execution_tools(self):
        self.assertIs(type(self.tools.get_tool('apply_patch')), ApplyPatchTool)
        self.assertIs(type(self.tools.get_tool('run_command')), RunCommandTool)
        self.assertFalse(self.tools.has_tool('write_file'))


    async def test_synthetic_paired_comparison(self):
        report = await comparison()
        self.assertEqual(report['label'], 'synthetic')
        self.assertEqual(report['real_model_http_requests'], 0)
        self.assertEqual(report['candidate']['verified'], 4)
        self.assertLess(report['candidate']['invalid_arguments'], report['baseline']['invalid_arguments'])
        self.assertLess(report['candidate']['unsupported_runner'], report['baseline']['unsupported_runner'])
        self.assertEqual(report['candidate']['stale_previews'], report['baseline']['stale_previews'])


class SyntheticPolicy:
    """Deliberately cue-sensitive script; measures feedback plumbing, not intelligence."""
    def __init__(self, case):
        self.case = case; self.chat = N(completions=N(create=self.create))
        self.calls = 0; self.stage = 'read'; self.invalids = 0; self.stale = False
        self.prepared = None; self.hash = None

    async def create(self, **kw):
        self.calls += 1
        text = kw['messages'][0]['content']
        last = kw['messages'][-1]['content'] or ''
        def emit(name, args):
            return response(calls=[N(id='synthetic-' + str(self.calls), function=N(name=name, arguments=json.dumps(args)))])
        if self.stage == 'read':
            self.stage = 'preview'
            return emit('read_file_range', {'path': 'value.py', 'start_line': 1, 'end_line': 5})
        if self.stage == 'preview':
            if 'metadata=' in last:
                meta = json.loads(last.split('metadata=')[-1])
                if 'file_sha256' in meta: self.hash = meta['file_sha256']
            schema_text = json.dumps(kw['tools'])
            bad = self.case == 'bad_hash' and 'no prefix' not in schema_text and self.invalids < 2
            if bad: self.invalids += 1
            stale = self.case == 'stale' and not self.stale
            if stale: self.stale = True
            self.prepared = [{'op': 'update', 'path': 'value.py', 'expected_sha256':
                ('sha256:' + self.hash) if bad else ('0' * 64 if stale else self.hash),
                'edits': [{'old_text': 'return value + 1', 'new_text': 'return value * 2'}]}]
            self.stage = 'preview_result'
            return emit('apply_patch', {'dry_run': True, 'changes': self.prepared})
        if self.stage == 'preview_result':
            if last.startswith('Error:'):
                self.stage = 'preview'
                return emit('read_file_range', {'path': 'value.py', 'start_line': 1, 'end_line': 5})
            self.stage = 'test'
            return emit('apply_patch', {'dry_run': False, 'changes': self.prepared})
        if self.stage == 'test':
            self.stage = 'finish'
            argv = (['python', '-c', 'print("Ran 3 tests in 0.01s\\nOK")']
                if self.case == 'runner' and 'python -c, printed OK' not in text else TEST_ARGV)
            return emit('run_command', {'argv': argv})
        return response('Synthetic repair complete; verification is determined by the host.')


def frozen(module, path):
    source = subprocess.check_output(['git', 'show', BASELINE + ':' + path], stderr=subprocess.DEVNULL, text=True)
    namespace = dict(vars(module))
    if path == 'mybot/agent/loop.py':
        # Compare the exact historical dispatch method, not retired JSON runtime imports.
        # No baseline constructor or persistence backend is instantiated by this experiment.
        from mybot.agent import tool_dispatch
        namespace.update(vars(tool_dispatch))
        tree = ast.parse(source)
        loop = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AgentLoop')
        loop.body = [n for n in loop.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_execute_tool']
        assert len(loop.body) == 1
        source = ast.Module(body=[ast.parse('from __future__ import annotations').body[0], loop], type_ignores=[])
        ast.fix_missing_locations(source)
    exec(compile(source, '<trusted-frozen-baseline>', 'exec'), namespace)
    return namespace


@contextlib.contextmanager
def baseline_behavior():
    from mybot.tools import patch as patch_module
    from mybot.agent import coding_controller as controller_module
    from mybot.agent import loop as loop_module
    old_patch = frozen(patch_module, 'mybot/tools/patch.py')['ApplyPatchTool']
    old_controller = frozen(controller_module, 'mybot/agent/coding_controller.py')['CodingTaskController']
    old_loop = frozen(loop_module, 'mybot/agent/loop.py')['AgentLoop']
    with contextlib.ExitStack() as stack:
        for cls, old, names in ((ApplyPatchTool, old_patch, ('execute', 'parameters', 'description')),
                (CodingTaskController, old_controller, ('instruction', '_observe_command')),
                (AgentLoop, old_loop, ('_execute_tool',))):
            for name in names: stack.enter_context(patch.object(cls, name, getattr(old, name)))
        yield


async def synthetic_arm(case, baseline):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder); fixture(root); tools = registry(root, 'macos_readonly')
        cfg = GatewayConfig(context_token_budget={"input_limit":160000}, workspace=root, coding_enabled=True, coding_patch_mode='write',
            coding_command={'mode': 'macos_readonly'}, coding_autonomy={'enabled': True, 'max_model_requests': 10},
            skills_enabled=False,  mcp_enabled=False, max_react_steps=12)
        policy = SyntheticPolicy(case); events = []
        class ObservedAgent(AgentLoop):
            async def _execute(self, name, raw):
                result = await super()._execute(name, raw)
                args = json.loads(raw)
                events.append({'name': name, 'error': result.error, 'success': result.success,
                    'preview': name == 'apply_patch' and args.get('dry_run') is True,
                    'write': name == 'apply_patch' and args.get('dry_run') is False,
                    'unsupported_runner': name == 'run_command' and '-c' in args.get('argv', [])})
                return result
        agent = ObservedAgent(policy, cfg, tools, ContextBuilder(root))
        with baseline_behavior() if baseline else contextlib.nullcontext():
            with contextlib.redirect_stdout(io.StringIO()):
                await agent.handle_message('Synthetic public contract: double each integer; run tests/test_contract.py using unittest.')
        state = agent.last_coding_report
        # Native runner evidence for this PUBLIC fixture only; no private Judge is consulted.
        public_pass = state['test_passes'] > 0 and state['tests_passed_after_last_patch'] > 0
        verified = state['state'] == 'verified'
        return {'case': case, 'state': state['state'], 'verified': verified,
            'strict_success': verified and public_pass and pair_messages(agent.session.history(), complete=True),
            'patched_unverified': state['committed_patches'] > 0 and not verified,
            'invalid_arguments': sum(e['error'] == 'invalid_arguments' for e in events),
            'stale_previews': sum(e['preview'] and e['error'] == 'stale_file_hash' for e in events),
            'unsupported_runner': sum(e['unsupported_runner'] for e in events),
            'logical_requests': policy.calls, 'tool_calls': len(events),
            'write_attempts': sum(e['write'] for e in events), 'committed_patches': state['committed_patches'],
            'stop_reason': state['stop_reason'], 'paired_tool_ids': pair_messages(agent.session.history(), complete=True)}


async def comparison():
    result = {'label': 'synthetic', 'baseline_sha': BASELINE, 'real_model_http_requests': 0,
        'budgets_per_arm_case': {'model_requests': 10, 'tool_calls': 48, 'patch_writes': 3, 'commands': 6},
        'policy': 'Deterministic cue-sensitive script; both arms use original Loop, native Patch, real approved Seatbelt unittest. No historical Judge.',
        'limitation': 'Public synthetic contract success only; no evidence about real model success rates, tokens or costs.'}
    for label in ('baseline', 'candidate'):
        rows = [await synthetic_arm(case, label == 'baseline') for case in ('clean', 'bad_hash', 'stale', 'runner')]
        result[label] = {'cases': rows, 'total': len(rows)}
        for key in ('verified', 'strict_success', 'patched_unverified', 'invalid_arguments', 'stale_previews',
                    'unsupported_runner', 'logical_requests', 'tool_calls'):
            result[label][key] = sum(row[key] for row in rows)
        patched = sum(row['committed_patches'] > 0 for row in rows)
        result[label]['patched_cases'] = patched
        result[label]['patched_unverified_rate'] = sum(row['patched_unverified'] for row in rows) / patched if patched else None
    return result


def reanalyze_history():
    """Read only existing sanitized reports. Never open private assertions or solutions."""
    source = Path(__file__).resolve().parent.parent / 'docs/reports/request-budget-full-batch/evidence'
    rows = []
    for path in sorted(source.glob('*/raw.json')):
        body = path.read_bytes()
        raw = json.loads(body)
        for result in raw['results']:
            rows.append({'case': result['case_id'], 'source': path.relative_to(source.parent.parent).as_posix(),
                'source_sha256': hashlib.sha256(body).hexdigest(), 'old_failure': result.get('failure'),
                'classification': failure_classification(result), 'agent_state': result['agent_state'],
                'stop_reason': result.get('controller', {}).get('stop_reason'),
                'judge_state': result.get('judge', {}).get('judge_state'),
                'original_strict_success': result.get('judge', {}).get('verified_repair_success', False)
                    and result['agent_state'] == 'verified',
                'historical_patch_arguments': 'unknown'})
    return {'version': FAILURE_RULE_VERSION, 'derived_only': True, 'new_model_requests': 0, 'results': rows}


def check_tool_verification_reliability():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(VerificationChecks))
    if not result.wasSuccessful(): raise SystemExit(1)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--comparison':
        Path(sys.argv[2]).write_text(json.dumps(asyncio.run(comparison()), indent=2) + '\n')
    elif len(sys.argv) == 3 and sys.argv[1] == '--reanalyze':
        Path(sys.argv[2]).write_text(json.dumps(reanalyze_history(), indent=2) + '\n')
    else:
        check_tool_verification_reliability()
