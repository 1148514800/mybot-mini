"""Isolated synthetic tasks for real AgentLoop, native tools, Web and browser QA."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace as N

from mybot.agent import AgentLoop, ContextBuilder
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from mybot.mcp_client.approval import ApprovalDecision
from scripts.check_session import call, response

PROMPTS = {
    'A': '修复偏移计算。输入 4 应返回 5。通过项目测试。',
    'B': '修复服务入口的倍数计算。输入 3 应返回 6。缺失输入应返回空列表。通过项目测试。',
    'C': '请查看项目，不授权文件写入。',
}


def requirement(ident='R1', text='输入 4 应返回 5。', source='user_explicit', ref='current-user', category='functional'):
    return dict(requirement_id=ident, requirement_text=text, source_type=source,
                source_reference=ref, category=category)


async def approve(request): return ApprovalDecision.APPROVE


def configuration(root, scenario='A', **changes):
    base = dict(workspace=root, api_key=None, provider='offline', model='synthetic',
                skills_enabled=False, mcp_enabled=False,  context_enabled=False, context_token_budget={'input_limit':64000},
                max_react_steps=10, coding_enabled=scenario != 'C',
                coding_patch_mode='write' if scenario != 'C' else 'off',
                coding_preview_receipt=scenario != 'C',
                coding_command={'mode': 'host_confirm'} if scenario != 'C' else {},
                coding_autonomy={'enabled': scenario != 'C'})
    return GatewayConfig(**(base | changes))


def prepare(root, scenario):
    if scenario == 'C':
        from mybot.workspace import init_workspace
        init_workspace(root)  # Baseline includes normal host bootstrap, before any denial check.
    (root/'core.py').write_text('def transform(n):\n    return n - 1\n' if scenario == 'A' else
                               'def transform(n):\n    return n + 2\n')
    (root/'service.py').write_text('from core import transform\ndef handle(n):\n    return transform(n)\n')
    (root/'test_project.py').write_text('import unittest\nfrom service import handle\nclass Public(unittest.TestCase):\n'
        + ('    def test_value(self): self.assertEqual(handle(4), 5)\n' if scenario=='A' else
           '    def test_value(self): self.assertEqual(handle(3), 6)\n'))
    (root/'README.md').write_text(PROMPTS.get(scenario, PROMPTS['C']))


def metadata(messages, name):
    calls = {}
    for m in messages:
        for c in m.get('tool_calls', []): calls[c['id']] = c['function']['name']
    for m in reversed(messages):
        if m['role']=='tool' and calls.get(m.get('tool_call_id')) == name:
            text=m['content'];return json.loads(text.rsplit('metadata=',1)[1])
    raise AssertionError('missing real tool result: '+name)


class SyntheticClient:
    def __init__(self, scenario='A'):
        self.scenario=scenario;self.requests=[];self.closed=False
        self.chat=N(completions=N(create=self.create))

    async def create(self, **kwargs):
        step=len(self.requests);self.requests.append(deepcopy(kwargs));messages=kwargs['messages']
        if self.scenario == 'C':
            assert step == 0, 'denial must stop without a repair request'
            return response(calls=[call('forged-write','write_file','{"path":"forbidden.txt","content":"bad"}')])
        reqs=[requirement(text='输入 4 应返回 5。' if self.scenario=='A' else '输入 3 应返回 6。')]
        if self.scenario=='B':reqs.append(requirement('R2','缺失输入应返回空列表。',category='boundary'))
        if step == 0:
            return response(calls=[call('contract','record_task_contract',json.dumps({'requirements':reqs})),
                call('entry','read_file_range','{"path":"service.py","start_line":1,"end_line":20}'),
                call('read','read_file_range','{"path":"core.py","start_line":1,"end_line":20}')])
        if step == 1:
            version=metadata(messages,'read_file_range')['file_sha256']
            old,new=('return n - 1','return n + 1') if self.scenario=='A' else ('return n + 2','return n * 2')
            return response(calls=[call('preview','apply_patch',json.dumps({'changes':[
                {'op':'update','path':'core.py','expected_sha256':version,'edits':[{'old_text':old,'new_text':new}]}], 'dry_run':True}))])
        if step == 2:
            return response(calls=[call('commit','apply_patch',json.dumps(metadata(messages,'apply_patch')['commit_arguments']))])
        if step == 3:
            return response(calls=[call('test','run_command','{"argv":["python","-m","unittest","test_project"]}')])
        if step == 4:
            refs=metadata(messages,'run_command')['contract_test_refs']
            return response(calls=[call('link','record_task_contract',json.dumps({'claims':['R1'],
                'evidence_links':[{'requirement_id':'R1','evidence_ref':refs[-1]}]}))])
        assert step == 5
        return response('实现已提交并通过指定测试；完整需求正确性仍未知。')

    async def close(self): self.closed=True


def agent(root, scenario='A', *, callback=None, client=None, config=None):
    config=config or configuration(root,scenario)
    tools=build_default_tool_registry(root,coding_enabled=config.coding_enabled,
        patch_mode=config.coding_patch_mode,preview_receipt=config.coding_preview_receipt,
        command=config.coding_command,command_approval_provider=approve)
    client=client or SyntheticClient(scenario)
    return AgentLoop(client,config,tools,ContextBuilder(root),event_callback=callback),client
