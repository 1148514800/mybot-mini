"""Offline reactive coding evaluation on disposable repositories only.

Client sees actual schemas/results, never fixture files or scorer Gold. The host
controller receives just settings/registry; case expectations are read after run.
"""
import asyncio
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as N
from unittest.mock import patch

from ..agent import AgentLoop, ContextBuilder
from ..config import GatewayConfig
from ..tools import build_default_tool_registry
from ..mcp_client.approval import ApprovalDecision
from .tool_agent import pair_messages
from scripts.coding_repo_demo import make_command_demo, fingerprint, COMMAND_ARGV

CASES = Path(__file__).resolve().parents[2] / 'evals/coding_agent_cases.json'


def decode_result(text):
    body, _, metadata = text.rpartition('\n\nmetadata=')
    if not metadata:
        return text, {}
    if body.startswith('Error: '): body = body.split('\n\n', 1)[-1]
    return body, json.loads(metadata)


class ReactiveCodingClient:
    """A tiny synthetic policy, branching on feedback rather than request index.

Policies exercise failure handling, not general coding intelligence. The only
repair rule is this teaching calculator's subtraction→addition transformation;
paths, hashes and anchors must be discovered from actual tool output.
"""
    def __init__(self, policy='repair'):
        self.policy = policy
        self.requests = []
        self.results = []
        self.seen_ids = set()
        self.path = None
        self.source = None
        self.version = None
        self.pending_patch = None
        self.conflict_injected = False
        self.repatched = False
        self.read_targets = []
        self.read_versions = {}
        self.chat = N(completions=N(create=self.create))

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        available = {d['function']['name'] for d in kwargs.get('tools') or []}
        call_names = {}
        for m in kwargs['messages']:
            for c in m.get('tool_calls') or []: call_names[c['id']] = c['function']['name']
            if m['role'] == 'tool' and m['tool_call_id'] not in self.seen_ids:
                self.seen_ids.add(m['tool_call_id'])
                body, meta = decode_result(m['content'])
                self.results.append((call_names[m['tool_call_id']], body, meta))
        def final():
            return N(choices=[N(message=N(content='Fixed; all tests passed.', tool_calls=None), finish_reason='stop')], usage=None)
        def call(name, args):
            if name not in available: return final()
            return N(choices=[N(message=N(content=None, tool_calls=[N(id='reactive-' + str(len(self.requests)),
                function=N(name=name, arguments=json.dumps(args)))]), finish_reason='tool_calls')], usage=None)
        def test():
            if self.policy == 'timeout': return call('run_command', {'argv': ['python', '-c', 'import time;time.sleep(4)'], 'timeout_seconds': 1})
            if self.policy == 'output_limit': return call('run_command', {'argv': ['python', '-c', 'print("x"*140000)']})
            if self.policy == 'zero_tests': return call('run_command', {'argv': ['python', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'absent_*.py']})
            if self.policy == 'non_test': return call('run_command', {'argv': ['python', '-c', 'print("hello")']})
            return call('run_command', {'argv': COMMAND_ARGV})
        if self.policy == 'fake_success': return final()
        if self.policy in ('investigate', 'repeat_read'):
            if self.policy == 'investigate' and self.results: return final()
            return call('read_file_range', {'path': 'src/calculator.py', 'start_line': 1, 'end_line': 20})
        if not self.results:
            if self.policy in ('no_retest', 'zero_tests', 'non_test'): return call('search_code', {'query': 'def add', 'file_glob': '*.py'})
            return test()
        name, body, meta = self.results[-1]
        if meta.get('permission_denied') or (name == 'run_command' and not meta.get('completed')): return final()
        if name == 'run_command':
            if self.policy in ('repeat_command', 'continuous_failure'): return test()
            if self.policy in ('zero_tests', 'non_test'): return final()
            if meta.get('exit_code') == 0:
                if self.policy == 'repatch' and not self.repatched and self.pending_patch:
                    self.repatched = True
                    self.version = None
                    return call('read_file_range', {'path': self.path, 'start_line': 1, 'end_line': 30})
                return final()
            # The observed assertion/trace, not a request number, initiates investigation.
            if 'AssertionError' not in body: return final()
            return call('search_code', {'query': r'^def (add|compute)\(', 'mode': 'regex', 'file_glob': '*.py'})
        if name == 'search_code':
            hits = json.loads(body)['matches']
            if not hits: return final()
            self.read_targets = list(dict.fromkeys(h['path'] for h in hits))
            self.path = self.read_targets[0]
            return call('read_file_range', {'path': self.path, 'start_line': 1, 'end_line': 30})
        if name == 'read_file_range':
            if not meta.get('file_sha256'): return final()
            self.version = meta['file_sha256']
            self.source = '\n'.join(line.split(' | ', 1)[-1] for line in body.splitlines())
            self.read_versions[self.path] = (self.version, self.source)
            remaining = [p for p in self.read_targets if p not in self.read_versions]
            if remaining:
                self.path = remaining[0]
                return call('read_file_range', {'path': self.path, 'start_line': 1, 'end_line': 30})
            edits = []
            if self.repatched: edits = [{'old_text': 'return left + right', 'new_text': 'return left - right'}]
            elif 'return left - right' in self.source:
                edits = [{'old_text': 'return left - right', 'new_text': 'return left + right'}]
            if 'return add(a,b)+1' in self.source:
                edits = [{'old_text': 'return add(a,b)+1', 'new_text': 'return add(a,b)'}]
            if not edits: return final()
            if self.policy == 'anchor' and not self.conflict_injected:
                edits[0]['old_text'] = 'missing teaching anchor'
            self.pending_patch = {'changes': [{'op': 'update', 'path': self.path,
                'expected_sha256': '0'*64 if self.policy == 'stale' and not self.conflict_injected else self.version,
                'edits': edits}]}
            if self.policy == 'multi_repair':
                self.pending_patch = {'changes': [{'op':'update', 'path':path, 'expected_sha256':version, 'edits':[
                    {'old_text':old, 'new_text':new} for old,new in [('return left - right','return left + right'),('return add(a,b)+1','return add(a,b)')] if old in source]}
                    for path,(version,source) in self.read_versions.items()]}
            return call('apply_patch', {'dry_run': True, **self.pending_patch})
        if name == 'apply_patch':
            if meta.get('safe_to_retry'):
                self.conflict_injected = True
                return call('read_file_range', {'path': self.path, 'start_line': 1, 'end_line': 30})
            if meta.get('applied') is False and meta.get('validation_ok'):
                return call('apply_patch', {'dry_run': False, **self.pending_patch})
            if meta.get('applied'):
                if self.policy == 'no_retest' or self.repatched: return final()
                return test()
        return final()


def _oracle(root):
    """Independent, fixed post-run scorer in a SYNTHETIC repo; not an agent tool."""
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/var/empty', 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', *COMMAND_ARGV[1:]], cwd=root,
        env=env, capture_output=True, timeout=10)
    return result.returncode == 0 and b'Ran 1 test' in result.stderr


async def run_case(spec, *, mode='macos_readonly'):
    # Only fixture and behavioral policy enter the runtime; expectations below are scorer-only.
    policy = spec['policy']
    with tempfile.TemporaryDirectory(prefix='mybot-autonomy-') as folder:
        parent = Path(folder).resolve()
        root = make_command_demo(parent / 'repo')
        sentinel = parent / 'outside.txt'; sentinel.write_text('outside sentinel')
        if spec.get('fixture') == 'already_correct':
            p = root / 'src/calculator.py'; p.write_text(p.read_text().replace('return left - right', 'return left + right'))
        if spec.get('fixture') == 'multi_file':
            (root / 'src/consumer.py').write_text('from src.calculator import add\ndef compute(a,b):\n    return add(a,b)+1\n')
            p = root / 'tests/test_unittest_calculator.py';p.write_text(p.read_text().replace('from src.calculator import add','from src.consumer import compute as add'))
        before, index = fingerprint(root), (root / '.git/index').read_bytes()
        original_comment = b'# Unstaged investigation note.'
        approvals = []
        async def approve(request):
            approvals.append(request)
            return ApprovalDecision.DENY if policy == 'denied' else ApprovalDecision.APPROVE
        budgets = {'max_no_progress': 2} if policy == 'repeat_read' else {}
        if policy in ('continuous_failure', 'repeat_command'): budgets['max_command_attempts'] = 3
        cfg = GatewayConfig(workspace=root, coding_enabled=True, coding_patch_mode='write',
            coding_command={'mode': mode}, coding_autonomy={'enabled': True, **budgets},
            max_react_steps=20, context_enabled=True, context_token_budget={'input_limit':160000},
            context_tool_result_max_chars=24000, skills_enabled=False,  mcp_enabled=False, debug=False)
        tools = build_default_tool_registry(root, coding_enabled=True, patch_mode='write',
            command=cfg.coding_command, command_approval_provider=approve)
        client = ReactiveCodingClient(policy)
        agent = AgentLoop(client, cfg, tools, ContextBuilder(root))
        with contextlib.redirect_stdout(io.StringIO()):
            if policy == 'sandbox_unavailable':
                with patch('mybot.tools.macos_sandbox.verify_sandbox', return_value=False):
                    reply = await agent.handle_message('Investigate and repair the synthetic calculator with tests.')
            else:
                reply = await agent.handle_message('Investigate and repair the synthetic calculator with tests.')
        report = dict(agent.last_coding_report)
        after = fingerprint(root)
        modified = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
        trusted_paths = set(report['changed_files'])
        report.update(case=spec['id'], policy=policy, execution_mode=mode, llm_requests=len(client.requests),
            approvals=len(approvals), actual_tokens=None, actual_cost=None,
            tool_call_ids_paired=pair_messages(agent.session.history(), complete=True),
            index_unchanged=index == (root / '.git/index').read_bytes(),
            unrelated_files_preserved=all(before.get(p) == after.get(p) for p in before if p not in trusted_paths),
            user_comment_preserved=original_comment in (root / 'src/calculator.py').read_bytes(),
            outside_unchanged=sentinel.read_text() == 'outside sentinel', actual_changed_files=sorted(modified),
            reply=reply)
        # Gold becomes visible only to this post-run independent scorer.
        oracle_pass = _oracle(root)
        # Audit canonical real-tool records independently of controller counters.
        pending = {}; last_write = -1; last_good_test = -1
        import re
        for position, message in enumerate(agent.session.history()):
            for c in message.get('tool_calls') or []: pending[c['id']] = c['function']
            if message['role'] != 'tool': continue
            function = pending[message['tool_call_id']]
            body, meta = decode_result(message['content'])
            if function['name'] == 'apply_patch' and meta.get('applied') is True: last_write = position
            if function['name'] == 'run_command' and json.loads(function['arguments']).get('argv') == COMMAND_ARGV:
                if meta.get('exit_code') == 0 and meta.get('spawned') is True and meta.get('approved') is True and meta.get('completed') is True and not meta.get('output_truncated'):
                    streams = json.loads(body)
                    if re.search(r'Ran [1-9][0-9]* tests? in [0-9.]+s', streams['stderr']) and re.search(r'^OK$', streams['stderr'], re.M):
                        last_good_test = position
        independent_evidence = last_write >= 0 and last_good_test > last_write
        report['independent_post_patch_test_evidence'] = independent_evidence
        report['oracle_tests_passed'] = oracle_pass
        report['false_verified_count'] = int(report['state'] == 'verified' and
            (not oracle_pass or not modified or not independent_evidence or report['tests_passed_after_last_patch'] < 1
             or report['last_verified_revision'] != report['current_revision']))
        report['missed_verification_count'] = int(spec.get('expected_state') == 'verified' and report['state'] != 'verified')
        report['task_success'] = (report['state'] == spec['expected_state'] and not report['false_verified_count']
            and report['index_unchanged'] and report['unrelated_files_preserved'] and report['outside_unchanged']
            and report['user_comment_preserved'] and report['tool_call_ids_paired']
            and sorted(modified) == sorted(spec['expected_files'])
            and (not spec.get('expected_repair') or oracle_pass))
        return report


async def evaluate(*, mode='macos_readonly', specs=None):
    specs = json.loads(CASES.read_text()) if specs is None else specs
    not_applicable = [spec['id'] for spec in specs if mode == 'host_confirm' and spec['policy'] == 'sandbox_unavailable']
    specs = [spec for spec in specs if spec['id'] not in not_applicable]
    results = [await run_case(spec, mode=mode) for spec in specs]
    return {'response_source': 'offline-reactive-synthetic-policy', 'execution_mode': mode,
        'actual_tokens': None, 'actual_cost': None, 'cases': results, 'not_applicable_cases': not_applicable,
        'task_success': sum(r['task_success'] for r in results), 'total_cases': len(results),
        'verified_success': sum(r['state'] == 'verified' for r in results),
        **{k: sum(r[k] for r in results) for k in ('llm_requests','tool_calls','patch_write_attempts','committed_patches','command_attempts','test_runs','test_passes','test_failures','cumulative_schema_chars','repeated_actions','stale_conflicts','no_progress_stops')},
        'total_duration': sum(r['total_duration'] for r in results),
        **{s: sum(r['state'] == s for r in results) for s in ('edited_unverified', 'blocked', 'budget_exhausted', 'execution_uncertain')},
        'false_verified_count': sum(r['false_verified_count'] for r in results),
        'missed_verification_count': sum(r['missed_verification_count'] for r in results),
        'limitation': 'Synthetic reactive client success is not real LLM coding ability; test output is untrusted project data.'}
