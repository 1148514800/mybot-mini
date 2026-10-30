"""Synthetic fixtures and offline investigation/patch demos; no Agent command tool."""
import argparse
import asyncio
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace as N
from mybot.agent import AgentLoop,ContextBuilder
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from mybot.tools.readonly_process import executable


def make_demo(root):
    root=Path(root).resolve()
    if root.exists() and any(root.iterdir()):raise ValueError('demo_directory_not_empty')
    root.mkdir(parents=True,exist_ok=True)
    for name,body in {
        'pyproject.toml':'[project]\nname = "synthetic-calculator"\nversion = "0.0.1"\n',
        'src/calculator.py':'def add(left, right):\n    """Add two numbers (contains a teaching bug)."""\n    return left - right\n\ndef total(values):\n    return add(values[0], values[1])\n',
        'tests/test_calculator.py':'from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n',
        'README.md':'# Synthetic calculator\nRead-only exploration fixture.\n',
        '.gitignore':'ignored.py\n',
    }.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body)
    git,_=executable('git',root)
    # Fixed test preparation, NOT a model-accessible terminal API. No host hooks/signing/config.
    import os
    env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','HOME':'/var/empty'}
    def setup(*args):
        subprocess.run([git,'-c','core.hooksPath=/dev/null','-c','commit.gpgsign=false',*args],
                       cwd=root,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=10)
    setup('init','-q');setup('add','.');setup('-c','user.name=Synthetic Demo','-c','user.email=demo@example.invalid','commit','-qm','Initial teaching fixture')
    (root/'README.md').write_text('# Synthetic calculator\nStaged teaching note.\n');setup('add','README.md')
    with (root/'src/calculator.py').open('a') as f:f.write('\n# Unstaged investigation note.\n')
    (root/'notes.txt').write_text('Untracked teaching note.\n')
    return root


def fingerprint(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts}


class InvestigationClient:
    """Use actual tool outputs for the next path/range, never fabricate the search result."""
    def __init__(self):
        self.requests=[];self.outputs={};self.chat=N(completions=N(create=self.create))
    async def create(self,**kwargs):
        self.requests.append(kwargs)
        for m in kwargs['messages']:
            if m['role']=='tool':self.outputs[m['tool_call_id']]=m['content']
        step=len(self.requests)
        if step==1:name,args='git_status',{}
        elif step==2:name,args='search_code',{'query':'def add','file_glob':'*.py'}
        else:
            text=self.outputs['investigate-2'].split('\n\nmetadata=',1)[0]
            hit=json.loads(text)['matches'][0]
            if step==3:name,args='read_file_range',{'path':hit['path'],'start_line':hit['line'],'end_line':hit['line']+3}
            elif step==4:name,args='git_diff',{'file_path':hit['path'],'scope':'unstaged'}
            else:
                status=json.loads(self.outputs['investigate-1'].split('\n\nmetadata=',1)[0])
                assert any(r['path']==hit['path'] and r['unstaged'] for r in status['files'])
                assert 'return left - right' in self.outputs['investigate-3']
                assert '# Unstaged investigation note.' in self.outputs['investigate-4']
                return N(choices=[N(message=N(content=f"{hit['path']}:{hit['line']} add uses subtraction; related file is modified. No repair or tests performed.",tool_calls=None), finish_reason='stop')],usage=None)
        return N(choices=[N(message=N(content=None,tool_calls=[N(id=f'investigate-{step}',function=N(name=name,arguments=json.dumps(args)))]), finish_reason='tool_calls')],usage=None)


async def investigate(root):
    before=fingerprint(root);index=(root/'.git/index').read_bytes()
    client=InvestigationClient()
    cfg=GatewayConfig(workspace=root,coding_enabled=True,skills_enabled=False,
                      context_enabled=True,context_token_budget={'input_limit':40000},mcp_enabled=False,debug=False)
    tools=build_default_tool_registry(root,coding_enabled=cfg.coding_enabled)
    agent=AgentLoop(client,cfg,tools,ContextBuilder(root))
    with contextlib.redirect_stdout(io.StringIO()):reply=await agent.handle_message('定位 calculator.py 中导致结果错误的函数，并检查相关文件是否已被修改。')
    assert before==fingerprint(root) and index==(root/'.git/index').read_bytes()
    from mybot.evaluation.tool_agent import pair_messages
    assert pair_messages(agent.session.history(),complete=True)
    return {'mode':'offline','actual_tokens':None,'actual_cost':None,'llm_requests':len(client.requests),
            'tools':['git_status','search_code','read_file_range','git_diff'],'reply':reply,
            'files_unchanged':True,'index_unchanged':True,'tool_call_ids_paired':True}


class EditingClient(InvestigationClient):
    """Fixed offline orchestration; versions and diffs come from real tool results."""
    async def create(self, **kwargs):
        self.requests.append(kwargs)
        for m in kwargs['messages']:
            if m['role'] == 'tool': self.outputs[m['tool_call_id']] = m['content']
        step = len(self.requests)
        if step == 1: name, args = 'git_status', {}
        elif step == 2: name, args = 'search_code', {'query': 'def add', 'file_glob': '*.py'}
        else:
            hit = json.loads(self.outputs['edit-2'].split('\n\nmetadata=', 1)[0])['matches'][0]
            path = hit['path']
            if step in (3, 6):
                name, args = 'read_file_range', {'path': path, 'start_line': 1, 'end_line': 20}
            elif step in (4, 5):
                version = json.loads(self.outputs['edit-3'].split('\n\nmetadata=', 1)[1])['file_sha256']
                name, args = 'apply_patch', {'dry_run': step == 4, 'changes': [{
                    'op': 'update', 'path': path, 'expected_sha256': version,
                    'edits': [{'old_text': 'return left - right', 'new_text': 'return left + right'}]}]}
            elif step == 7: name, args = 'git_diff', {'file_path': path}
            else:
                assert 'return left + right' in self.outputs['edit-6']
                assert '+    return left + right' in self.outputs['edit-7']
                return N(choices=[N(message=N(content='Applied precise edit and reread actual file/diff; no tests executed by Agent.', tool_calls=None), finish_reason='stop')], usage=None)
        return N(choices=[N(message=N(content=None, tool_calls=[N(id=f'edit-{step}',
            function=N(name=name, arguments=json.dumps(args)))]), finish_reason='tool_calls')], usage=None)


async def edit_demo(root):
    before = fingerprint(root); index = (root / '.git/index').read_bytes()
    original = (root / 'src/calculator.py').read_bytes()
    client = EditingClient()
    cfg = GatewayConfig(workspace=root, coding_enabled=True, coding_patch_mode='write',
        skills_enabled=False,  mcp_enabled=False, context_enabled=True,
        context_token_budget={'input_limit':80000}, context_tool_result_max_chars=16000, debug=False)
    agent = AgentLoop(client, cfg, build_default_tool_registry(root, coding_enabled=True, patch_mode='write'), ContextBuilder(root))
    with contextlib.redirect_stdout(io.StringIO()):
        reply = await agent.handle_message('Read, preview and precisely repair add; preserve all other changes. No commands or tests.')
    after = fingerprint(root)
    assert (root / 'src/calculator.py').read_bytes() == original.replace(b'return left - right', b'return left + right')
    assert {p: h for p, h in before.items() if p != 'src/calculator.py'} == {p: h for p, h in after.items() if p != 'src/calculator.py'}
    assert (root / '.git/index').read_bytes() == index
    from mybot.evaluation.tool_agent import pair_messages
    assert pair_messages(agent.session.history(), complete=True)
    preview = json.loads(client.outputs['edit-4'].split('\n\nmetadata=', 1)[1])
    applied = json.loads(client.outputs['edit-5'].split('\n\nmetadata=', 1)[1])
    assert not preview['applied'] and applied['applied']
    return {'mode': 'offline-fixed-model', 'llm_requests': len(client.requests), 'reply': reply,
        'before_sha256': sha256_hex(original), 'after_sha256': after['src/calculator.py'],
        'preview_diff': preview['preview_diff'], 'actual_git_diff': client.outputs['edit-7'].split('\n\nmetadata=', 1)[0],
        'index_unchanged': True, 'other_files_unchanged': True, 'user_comment_preserved': True,
        'tool_call_ids_paired': True, 'agent_ran_tests': False, 'actual_tokens': None, 'actual_cost': None}


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


COMMAND_TEST = """import unittest
from src.calculator import add

class CalculatorTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)
"""
COMMAND_ARGV = ['python', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_unittest_calculator.py', '-v']


def make_command_demo(root):
    root = make_demo(root)
    (root / 'tests/test_unittest_calculator.py').write_text(COMMAND_TEST)
    return root


class CommandClient(InvestigationClient):
    """Offline sequence branches on actual command exit/output and file versions."""
    async def create(self, **kwargs):
        self.requests.append(kwargs)
        for m in kwargs['messages']:
            if m['role'] == 'tool': self.outputs[m['tool_call_id']] = m['content']
        step = len(self.requests)
        def metadata(number):return json.loads(self.outputs[f'command-{number}'].split('\n\nmetadata=', 1)[1])
        if step == 1: calls = [('create_plan', {'steps': ['Diagnose and precisely repair', 'Run tests again and inspect diff']})]
        elif step == 2: calls = [('update_plan', {'step': 1, 'status': 'in_progress'})]
        elif step == 3: calls = [('run_command', {'argv': COMMAND_ARGV})]
        elif step == 4:
            actual = metadata(3)
            assert actual['completed'] and actual['exit_code'] != 0 and 'AssertionError' in self.outputs['command-3']
            calls = [('search_code', {'query': 'def add', 'file_glob': '*.py'})]
        else:
            hit = json.loads(self.outputs['command-4'].split('\n\nmetadata=', 1)[0])['matches'][0]
            if step == 5:calls = [('read_file_range', {'path': hit['path'], 'start_line': 1, 'end_line': 20})]
            elif step in (6, 7):
                calls = [('apply_patch', {'dry_run': step == 6, 'changes': [{'op': 'update', 'path': hit['path'],
                    'expected_sha256': metadata(5)['file_sha256'],
                    'edits': [{'old_text': 'return left - right', 'new_text': 'return left + right'}]}]})]
            elif step == 8:calls = [('update_plan', {'step': 1, 'status': 'completed'}), ('update_plan', {'step': 2, 'status': 'in_progress'})]
            elif step == 9:calls = [('run_command', {'argv': COMMAND_ARGV})]
            elif step == 10:
                assert metadata(9)['completed'] and metadata(9)['exit_code'] == 0 and 'OK' in self.outputs['command-9']
                calls = [('git_diff', {'file_path': hit['path']})]
            elif step == 11:calls = [('update_plan', {'step': 2, 'status': 'completed'})]
            else:
                assert '+    return left + right' in self.outputs['command-10']
                return N(choices=[N(message=N(content=f"真实 unittest：修复前 exit_code={metadata(3)['exit_code']}，精确 Patch 后 exit_code={metadata(9)['exit_code']}，1 项测试通过。", tool_calls=None), finish_reason='stop')], usage=None)
        return N(choices=[N(message=N(content=None, tool_calls=[N(id=f'command-{step}' if i == 0 else f'command-{step}-{i}',
            function=N(name=name, arguments=json.dumps(args))) for i, (name, args) in enumerate(calls)]), finish_reason='tool_calls' if [N(id=f'command-{step}' if i == 0 else f'command-{step}-{i}',
            function=N(name=name, arguments=json.dumps(args))) for i, (name, args) in enumerate(calls)] else 'stop')], usage=None)


async def command_demo(root, *, mode='macos_readonly'):
    from mybot.mcp_client.approval import ApprovalDecision
    approvals = []
    async def approve(request): approvals.append(request);return ApprovalDecision.APPROVE
    before = fingerprint(root); index = (root / '.git/index').read_bytes()
    original = (root / 'src/calculator.py').read_bytes()
    cfg = GatewayConfig(workspace=root, coding_enabled=True, coding_patch_mode='write', coding_command={'mode': mode},
        skills_enabled=False,  mcp_enabled=False, context_enabled=True,
        context_token_budget={'input_limit':120000}, context_tool_result_max_chars=20000, max_react_steps=16, debug=False)
    tools = build_default_tool_registry(root, coding_enabled=True, patch_mode='write',
        command=cfg.coding_command, command_approval_provider=approve)
    client = CommandClient();agent = AgentLoop(client, cfg, tools, ContextBuilder(root))
    with contextlib.redirect_stdout(io.StringIO()):
        reply = await agent.handle_message('运行 calculator 的测试，定位失败原因，精确修改加法 Bug，并重新执行测试。')
    after = fingerprint(root)
    assert (root / 'src/calculator.py').read_bytes() == original.replace(b'return left - right', b'return left + right')
    assert {k: v for k, v in before.items() if k != 'src/calculator.py'} == {k: v for k, v in after.items() if k != 'src/calculator.py'}
    assert index == (root / '.git/index').read_bytes()
    from mybot.evaluation.tool_agent import pair_messages
    assert pair_messages(agent.session.history(), complete=True)
    assert len(approvals) == 2 and all(s.status == 'completed' for s in agent.plan.steps)
    results = [json.loads(client.outputs[f'command-{n}'].split('\n\nmetadata=', 1)[1]) for n in (3, 9)]
    return {'mode': mode, 'response_source': 'fixed_offline_model', 'llm_requests': len(client.requests),
        'approvals': len(approvals), 'approval_source': 'synthetic provider for disposable fixture only',
        'before_exit_code': results[0]['exit_code'], 'after_exit_code': results[1]['exit_code'],
        'sandbox_applied': [r['sandbox_applied'] for r in results], 'reply': reply,
        'failed_assertion_observed': True, 'index_unchanged': True, 'other_files_unchanged': True,
        'user_comment_preserved': True, 'plan_completed': True, 'tool_call_ids_paired': True,
        'actual_git_diff': client.outputs['command-10'].split('\n\nmetadata=', 1)[0],
        'actual_tokens': None, 'actual_cost': None}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--create',type=Path);parser.add_argument('--edit',action='store_true');parser.add_argument('--command',action='store_true');parser.add_argument('--command-mode',choices=['host_confirm','macos_readonly'],default='macos_readonly')
    args=parser.parse_args()
    if args.create:make_demo(args.create);print('Created synthetic fixture:',args.create)
    else:
        with tempfile.TemporaryDirectory(prefix='mybot-coding-demo-') as folder:
            if args.command:result=asyncio.run(command_demo(make_command_demo(Path(folder)/'repo'),mode=args.command_mode))
            else:result=asyncio.run((edit_demo if args.edit else investigate)(make_demo(Path(folder)/'repo')))
            print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
