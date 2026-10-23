"""OFFLINE/SYNTHETIC prompt delivery, never a claim of model compliance."""
import unittest
from scripts import modernization_fixtures as fixtures
from mybot.agent.context import SYSTEM_RULES

class InstructionChecks(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.Base.setUp
    build=fixtures.Base.build
    async def test_requirements_optional_pending_contract_delivered(self):
        await self.agent.handle_message('只分析需求')
        prompt=self.client.requests[0]['messages'][0]['content']
        for text in ('用户已指定要求','可选建议','待确认','只分析时不得修改文件'):self.assertIn(text,prompt)
    async def test_code_search_real_implementation_contract(self):
        await self.agent.handle_message('调查函数调用关系')
        request=self.client.requests[0];self.assertIn('search_code',request['messages'][0]['content'])
        self.assertIn('type(x) is int',SYSTEM_RULES);self.assertIn('isinstance(x, int)',SYSTEM_RULES)
        self.assertIn('unknown',SYSTEM_RULES)
    async def test_no_coding_chat_and_budget(self):
        await self.agent.handle_message('你好')
        self.assertEqual(len(self.client.requests),1);self.assertEqual(self.agent.plan.steps,[])
        self.assertLessEqual(self.agent.resources.context['estimated_input_tokens'],8000)
    async def test_no_sample_specific_answers(self):
        for value in ('UTF-8','CSV','id唯一','U02','U03'):self.assertNotIn(value,SYSTEM_RULES)
    async def test_real_code_tool_offered_when_enabled(self):
        from dataclasses import replace
        from mybot.tools import build_default_tool_registry
        from mybot.agent import AgentLoop,ContextBuilder
        cfg=replace(self.config,coding_enabled=True)
        agent=AgentLoop(self.client,cfg,build_default_tool_registry(self.root,coding_enabled=True),ContextBuilder(self.root))
        await agent.handle_message('只分析函数')
        names=[t['function']['name'] for t in self.client.requests[0]['tools']]
        self.assertIn('search_code',names);self.assertIn('read_file_range',names)

if __name__=='__main__':unittest.main(verbosity=2)
