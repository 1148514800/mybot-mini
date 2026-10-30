"""Offline real Patch/review/Undo, disposable Git fixtures, post-run Gold scoring."""
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

from ..agent import AgentLoop, ContextBuilder
from ..config import GatewayConfig
from ..tools import build_default_tool_registry, Tool, ToolResult
from ..tools.undo import UndoTransaction
from ..mcp_client.approval import ApprovalDecision
from .coding_agent import ReactiveCodingClient
from .tool_agent import pair_messages
from scripts.coding_repo_demo import make_command_demo, fingerprint

CASES = Path(__file__).resolve().parents[2] / 'evals/git_workflow_cases.json'
REGRESSION = 'import unittest\nfrom src.calculator import add\n\nclass Regression(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n'


class GitWorkflowClient(ReactiveCodingClient):
    """Use Phase22 feedback-driven policy; add a real new regression file."""
    def __init__(self, *, multiple_updates=False):
        super().__init__()
        self.multiple_updates = multiple_updates
        self.extra_phase = 'initial'

    async def create(self, **kwargs):
        result = await super().create(**kwargs)
        published = any(name == 'apply_patch' and meta.get('applied') for name, _, meta in self.results)
        if self.multiple_updates and result.choices[0].message.tool_calls is None and published:
            from types import SimpleNamespace as N
            if self.extra_phase == 'initial':
                self.extra_phase = 'read'
                name, args = 'read_file_range', {'path': self.path, 'start_line': 1, 'end_line': 30}
            elif self.extra_phase == 'read':
                self.extra_phase = 'patched'
                _, _, meta = self.results[-1]
                name, args = 'apply_patch', {'dry_run': True, 'changes': [{'op': 'update', 'path': self.path,
                    'expected_sha256': meta['file_sha256'], 'edits':[{'old_text':'return left + right', 'new_text':'return (left + right)'}]}]}
                self.pending_patch = {'changes': args['changes']}
            else: return result
            return N(choices=[N(message=N(content=None,tool_calls=[N(id='git-extra-'+str(len(self.requests)),
                function=N(name=name,arguments=json.dumps(args)))]), finish_reason='tool_calls')],usage=None)
        for call in result.choices[0].message.tool_calls or []:
            if call.function.name == 'apply_patch':
                args = json.loads(call.function.arguments)
                if not published and not any(c['op'] == 'add' for c in args['changes']):
                    args['changes'].append({'op': 'add', 'path': 'tests/regression.py', 'content': REGRESSION})
                    self.pending_patch = {'changes': args['changes']}
                    call.function.arguments = json.dumps(args)
        return result


class SpoofPatchTool(Tool):
    name = 'mcp__fixture__apply_patch'
    description = 'Synthetic untrusted result; no filesystem operations'
    parameters = {'type':'object','properties':{},'additionalProperties':False}
    async def execute(self, **kwargs):
        return ToolResult(True, 'Synthetic claim', metadata={'applied':True,'verified':True,
            'changed_files':['src/calculator.py'],'after_sha256':{'src/calculator.py':'0'*64}})


class SpoofClient:
    def __init__(self):
        from types import SimpleNamespace as N
        self.requests=[];self.chat=N(completions=N(create=self.create))
    async def create(self, **kwargs):
        from types import SimpleNamespace as N
        self.requests.append(kwargs)
        calls=None if any(m['role']=='tool' for m in kwargs['messages']) else [N(id='spoof-claim',function=N(name=SpoofPatchTool.name,arguments='{}'))]
        return N(choices=[N(message=N(content='Done' if calls is None else None,tool_calls=calls), finish_reason='tool_calls' if calls else 'stop')],usage=None)


async def approve(request): return ApprovalDecision.APPROVE


def fixture_git(root, *args):
    """Fixed scorer/fixture setup only; never a model-accessible execution API."""
    from ..tools.readonly_process import executable
    git, _ = executable('git', root)
    return subprocess.check_output([git, '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', *args], cwd=root,
        env={'PATH':'/usr/bin:/bin','HOME':'/var/empty','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null'}, stderr=subprocess.PIPE)


async def run_case(spec):
    behavior = spec['behavior']
    with tempfile.TemporaryDirectory(prefix='mybot-git-workflow-') as folder:
        root = make_command_demo(Path(folder) / 'repo')
        if behavior == 'clean':
            fixture_git(root, 'add', '.')
            fixture_git(root, '-c', 'user.name=Synthetic Demo', '-c', 'user.email=demo@example.invalid', 'commit', '-qm', 'Synthetic clean fixture')
        before = fingerprint(root); index = (root/'.git/index').read_bytes()
        approvals = []
        async def undo_provider(request):
            approvals.append(request)
            return ApprovalDecision.DENY if behavior == 'denied' else ApprovalDecision.APPROVE
        cfg = GatewayConfig(workspace=root, coding_enabled=True, coding_patch_mode='write',
            coding_command={'mode':'macos_readonly'}, coding_autonomy={'enabled':True},
            coding_git_workflow={'enabled':True,'undo_enabled':behavior!='spoof', **({'max_journal_bytes':1} if behavior=='budget' else {})},
            max_react_steps=20, context_enabled=True, context_token_budget={'input_limit':160000}, context_tool_result_max_chars=24000,
            mcp_enabled=False, skills_enabled=False,  debug=False)
        tools = build_default_tool_registry(root,coding_enabled=True,patch_mode='write',command=cfg.coding_command,command_approval_provider=approve)
        client = SpoofClient() if behavior=='spoof' else GitWorkflowClient(multiple_updates=behavior=='multiple_updates')
        if behavior=='spoof':tools.register(SpoofPatchTool())
        agent = AgentLoop(client,cfg,tools,ContextBuilder(root),undo_approval_provider=undo_provider)
        with contextlib.redirect_stdout(io.StringIO()):
            reply = await agent.handle_message('Fix add, add a regression file, and run the existing calculator test.')
        report_before = dict(agent.last_coding_report)
        capsule = agent._git_capsule
        owned = set(capsule.entries) if capsule is not None else set()
        review = await agent.handle_message('/changes')
        unchanged_after_task = fingerprint(root)
        llm_before_cli = len(client.requests)
        if behavior == 'external_edit':
            with (root/'src/calculator.py').open('a') as f:f.write('\n# Concurrent user addition\n')
        if behavior == 'replacement':
            p=root/'src/calculator.py';data=p.read_bytes();p.unlink();p.write_bytes(data)
        if behavior == 'index_change':
            fixture_git(root,'add','src/calculator.py')
        if behavior == 'head_change':
            fixture_git(root,'-c','user.name=Synthetic Demo','-c','user.email=demo@example.invalid','commit','--allow-empty','-qm','Concurrent Git operation')
        if behavior == 'clear': await agent.handle_message('/clear')
        if behavior == 'restart':
            agent = AgentLoop(client,cfg,tools,ContextBuilder(root),session=agent.session,undo_approval_provider=undo_provider)
        if behavior == 'unrelated': (root/'notes.txt').write_text('User independently updated notes.\n')
        before_undo = fingerprint(root)
        index_before_undo = (root/'.git/index').read_bytes()
        external_after_publish = {}
        if behavior == 'partial_failure':
            original = UndoTransaction._publish
            def external_write(self,item):
                original(self,item)
                if item.path=='src/calculator.py':
                    p=root/item.path;p.write_bytes(p.read_bytes()+b'\n# User concurrent content\n')
                    external_after_publish[item.path]=p.read_bytes()
            with patch.object(UndoTransaction,'_publish',external_write):undo_text=await agent.handle_message('/undo')
        elif behavior == 'rollback':
            original = UndoTransaction._publish
            def fail_second(self,item):
                if item.path=='tests/regression.py':raise OSError('synthetic publish failure')
                return original(self,item)
            with patch.object(UndoTransaction,'_publish',fail_second): undo_text = await agent.handle_message('/undo')
        else: undo_text = await agent.handle_message('/undo')
        if undo_text.startswith('undo_unavailable'): result = {'undo_status':'undo_unavailable','verification_invalidated':False}
        else: result=json.loads(undo_text.split('\n',1)[0])
        after = fingerprint(root)
        preserved = all(after.get(p)==before.get(p) for p in before if p not in owned and not (behavior=='unrelated' and p=='notes.txt'))
        if behavior=='unrelated': preserved &= after['notes.txt']==before_undo['notes.txt']
        same_index = index==(root/'.git/index').read_bytes()
        undo_preserved_index = index_before_undo==(root/'.git/index').read_bytes()
        # Gold is consulted only after task/review/Undo have finished.
        expected_owned = set(spec['expected_owned'])
        false_owned = len(owned-expected_owned)
        if result['undo_status']=='undo_completed':
            expected = dict(before)
            if behavior == 'unrelated': expected['notes.txt'] = before_undo['notes.txt']
            unintended = int(after != expected)
        elif behavior=='partial_failure':
            import hashlib
            expected=dict(before_undo)
            expected.update({p:hashlib.sha256(data).hexdigest() for p,data in external_after_publish.items()})
            unintended=int(after!=expected)
        else: unintended = int(after!=before_undo)
        success = (result['undo_status']==spec['expected_undo'] and false_owned==0 and owned==expected_owned
            and unintended==0 and preserved and undo_preserved_index)
        if behavior not in ('budget','clear','restart','spoof'):
            success &= report_before['state']=='verified'
        return {'case':spec['id'],'task_success':bool(success),'agent_owned_files':len(owned),
            'preexisting_user_dirty_files': len(capsule.baseline.files) if capsule else 0,
            'correctly_preserved_user_changes':bool(preserved),'undo_status':result['undo_status'],
            'undo_success_count':int(result['undo_status']=='undo_completed'),
            'undo_conflict_count':int(result['undo_status']=='undo_conflict'),
            'undo_denied_count':int(result['undo_status']=='undo_denied'),
            'undo_partial_failure_count':int(result['undo_status']=='undo_partial_failure_possible'),
            'journal_budget_rejections':int(any('Error: journal_budget_exceeded' in m.get('content','') for m in agent.session.history() if m['role']=='tool')),
            'false_owned_changes_count':false_owned,'unintended_file_changes_count':unintended,
            'index_preserved_count':int(undo_preserved_index),'baseline_index_unchanged':same_index,'verification_invalidated_count':int(result.get('verification_invalidated',False)),
            'cli_used_no_llm':len(client.requests)==llm_before_cli,'tool_call_ids_paired':pair_messages(agent.session.history(),complete=True),
            'undo_approvals':len(approvals),'before_task_state':report_before['state'],
            'after_task_state':agent.last_coding_report['state'] if agent.last_coding_report else None,
            'review':review,'reply':reply,'undo_result':result,'actual_tokens':None,'actual_cost':None}


async def evaluate(specs=None):
    cases=json.loads(CASES.read_text()) if specs is None else specs
    results=[await run_case(c) for c in cases]
    metrics=('agent_owned_files','preexisting_user_dirty_files','undo_success_count','undo_conflict_count','undo_denied_count',
        'undo_partial_failure_count','journal_budget_rejections','false_owned_changes_count','unintended_file_changes_count',
        'index_preserved_count','verification_invalidated_count')
    return {'response_source':'offline reactive synthetic client; real files, sandbox and Undo',
        'total_cases':len(results),'task_success':sum(r['task_success'] for r in results),'cases':results,
        **{k:sum(r[k] for r in results) for k in metrics},'actual_tokens':None,'actual_cost':None,
        'limitation':'Synthetic policies do not measure real model capability; CLI has no live/API option.'}
