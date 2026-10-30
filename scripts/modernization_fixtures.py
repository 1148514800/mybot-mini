"""Offline helpers shared by the three modernization contract suites."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as N
import unittest

from mybot.agent import AgentLoop, ContextBuilder
from mybot.agent.context_compactor import FIELDS, PROMPT
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from scripts.check_session import response, call, assert_pairs


def summary_response(request, *, invalid=False):
    sources=json.loads(request['messages'][-1]['content'])
    doc={key:[] for key in FIELDS}
    for source in sources:
        for message in source['messages']:
            text=message['content']
            if message['role']=='user':
                for key in ('current_goal','user_constraints','pending_work','uncertainty'):
                    marker={'current_goal':'GOAL:', 'user_constraints':'CONSTRAINT:', 'pending_work':'PENDING:', 'uncertainty':'UNKNOWN:'}[key]
                    if marker in text:
                        quote=text[text.index(marker):].split('\n')[0][:180]
                        doc[key].append(dict(turn=source['turn'],message=message['message'],quote=quote))
            elif message['role']=='tool' and text.startswith('Error:'):
                doc['unresolved_issues'].append(dict(turn=source['turn'],message=message['message'],quote=text[:180]))
    if invalid:doc['completed_work']=[dict(turn=1,message=1,quote='fabricated success')]
    return response(json.dumps(doc,ensure_ascii=False))


class Client:
    def __init__(self, effects=None, summary=None):
        self.requests=[];self.effects=list(effects or []);self.summary=summary;self.closed=False
        self.chat=N(completions=N(create=self.create))
    async def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        if kwargs['messages'][0]['content']==PROMPT:
            if self.summary:return await self.summary(kwargs)
            return summary_response(kwargs)
        assert_pairs(unittest.TestCase(), kwargs['messages'])
        effect=self.effects.pop(0) if self.effects else response('offline complete')
        if isinstance(effect,BaseException):raise effect
        if callable(effect):return await effect(kwargs)
        return effect
    async def close(self):self.closed=True


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.config=GatewayConfig(workspace=self.root,provider='offline',model='synthetic',api_key='synthetic-private-key',
            context_enabled=True,context_max_chars=6000,context_tool_result_max_chars=256,context_summary_max_chars=3000,
            context_recent_turns=0,session_max_turns=12,skills_enabled=False,mcp_enabled=False,
            context_token_budget={'mode':'estimate','input_limit':8000})
        self.client=Client();self.agent=self.build()
    def build(self, client=None, config=None, **kwargs):
        config=config or self.config
        return AgentLoop(client or self.client,config,build_default_tool_registry(self.root),ContextBuilder(self.root),**kwargs)
    def history(self, size=7000):
        return [[{'role':'user','content':'GOAL: 保持项目兼容\nCONSTRAINT: 不删除用户文件\nPENDING: 尚未运行测试\nUNKNOWN: 真实供应商行为未知\n'+ 'x'*size},
                 {'role':'assistant','content':'计划下一步测试，尚未完成。'}],
                [{'role':'user','content':'CONSTRAINT: 改为只读检查\n'+'y'*size},{'role':'assistant','content':'记住新的约束。'}]]
    def semantic(self, **changes):
        self.config.context_compaction.update(mode='semantic',allow_extra_requests=True,input_tokens=40000,output_tokens=1200,**changes)
        self.agent=self.build();self.agent.session.restore(self.history())


def run(cls):
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    if not result.wasSuccessful():raise AssertionError(cls.__name__+' failed')
