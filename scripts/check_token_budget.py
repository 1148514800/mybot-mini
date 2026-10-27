"""Request preflight precision, model-specific bounds and legacy compatibility."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace as N
from unittest.mock import patch
import json

from mybot.agent.context_manager import ContextManager, ContextBudgetError
from mybot.agent.token_counter import TokenCounter, TokenBudgetError
from mybot.agent.planning import Plan
from mybot.config import GatewayConfig, build_client
from mybot.provider_failover import ProviderFailoverClient
from scripts.modernization_fixtures import Base, Client, run, response, call
from scripts.check_provider_failover import failed


class TokenChecks(Base):
    def request(self, text):return TokenCounter.request(self.config,[{'role':'user','content':text}],None)
    async def test_units_and_languages(self):
        values=[TokenCounter.measure(self.request(t)) for t in ('aaaa','中文中文','😀😀😀😀','x=12','{"a":1}')]
        self.assertEqual(values[0]['request_chars'],values[1]['request_chars'])
        self.assertLess(values[0]['estimated_input_tokens'],values[1]['estimated_input_tokens'])
        self.assertLess(values[1]['request_utf8_bytes'],values[2]['request_utf8_bytes'])
        self.assertTrue(all(v['local_tokenizer_tokens'] is None for v in values))
    async def test_schema_and_protocol_counted(self):
        request=self.request('x');before=TokenCounter.measure(request)['estimated_input_tokens']
        request['tools']=self.agent.tools.get_definitions();self.assertGreater(TokenCounter.measure(request)['estimated_input_tokens'],before)
        before=TokenCounter.measure(request)['estimated_input_tokens'];request['messages'] += [dict(role='assistant',content=None,tool_calls=[dict(id='abc',type='function',function=dict(name='read_file',arguments='{"path":"x"}'))]),dict(role='tool',tool_call_id='abc',content='中文'*100)]
        self.assertGreater(TokenCounter.measure(request)['estimated_input_tokens'],before)
    async def test_output_reserve_reduces_input_room(self):
        self.config.context_token_budget['model_windows']={'offline/synthetic':2500}
        policy=TokenCounter.policy(self.config,self.request('x'));self.assertEqual(policy['input_token_limit'],500)
        with self.assertRaises(TokenBudgetError):TokenCounter.enforce(self.config,self.request('中文'*200))
    async def test_unknown_window_explicit_cap(self):
        data=TokenCounter.enforce(self.config,self.request('hello'))
        self.assertEqual(data['model_window_status'],'unknown');self.assertIsNone(data['exact_remaining_tokens']);self.assertEqual(data['input_token_limit'],8000)
    async def test_strict_unverified_no_dispatch(self):
        self.config.context_token_budget['mode']='strict'
        with self.assertRaises(ContextBudgetError):await self.agent.handle_message('test')
        self.assertEqual(self.client.requests,[])
    async def test_strict_known_window_still_requires_tokenizer(self):
        self.config.context_token_budget.update(mode='strict',model_windows={'offline/synthetic':100000})
        with self.assertRaisesRegex(TokenBudgetError,'unverified'):TokenCounter.enforce(self.config,self.request('x'))
    async def test_protected_input_overflow_no_request(self):
        with self.assertRaises(ContextBudgetError):await self.agent.handle_message('关键请求'*10000)
        self.assertEqual(self.client.requests,[])
    async def test_legacy_character_semantics(self):
        self.config.context_token_budget['mode']='legacy_chars'
        manager=ContextManager(self.config);messages=self.agent.context.build_messages('中文')
        view,stats=manager.prepare(messages,None,[],Plan())
        self.assertEqual(stats['after'],len(json.dumps({'messages':view,'tools':None},ensure_ascii=False)))
        self.assertEqual(stats['context_budget_unit'],'chars');self.assertEqual(view,messages)
    async def test_original_history_not_modified(self):
        turns=self.history();original=deepcopy(turns);messages=self.agent.context.build_messages('CURRENT',[m for t in turns for m in t]);copy=deepcopy(messages)
        view,stats=self.agent.context_manager.prepare(messages,None,turns,Plan())
        self.assertEqual(messages,copy);self.assertEqual(turns,original);self.assertEqual(view[-1]['content'],'CURRENT');self.assertLessEqual(stats['estimated_input_tokens'],8000)
    async def test_current_tool_pairs_preserved(self):
        (self.root/'large.txt').write_text('中文'*10000)
        self.client.effects=[response(calls=[call('real-id','read_file','{"path":"large.txt"}')]),response('节选')]
        await self.agent.handle_message('读取文件')
        request=self.client.requests[-1];tool=next(m for m in request['messages'] if m['role']=='tool')
        self.assertEqual(tool['tool_call_id'],'real-id');self.assertIn(ContextManager.marker,tool['content']);self.assertIn('不能据此声称完整分析',self.agent.context_manager.marker)
    async def test_bad_budget_configuration(self):
        for value in ({'mode':'gpt_exact'},{'input_limit':True},{'input_limit':255},{'model_windows':{'x':5000}},{'model_windows':{'p/m':True}},{'extra':1}):
            with self.subTest(value=value),self.assertRaises(ValueError):replace(self.config,context_token_budget=value)
    async def test_token_mode_cannot_silently_disable_context(self):
        with self.assertRaises(ValueError):replace(self.config,context_enabled=False)
    async def test_fallback_smaller_window_refuses_before_backup(self):
        primary=Client([failed()]);backup=Client()
        cfg=replace(self.config,provider='coco',model='primary')
        secondary=replace(cfg,provider='coco2',model='backup',context_token_budget={'mode':'estimate','input_limit':8000,'model_windows':{'coco2/backup':2100}})
        gateway=ProviderFailoverClient(primary,cfg,secondary,lambda c:backup)
        agent=self.build(gateway,cfg)
        with self.assertRaises(TokenBudgetError):await agent.handle_message('test')
        self.assertEqual(len(primary.requests),1);self.assertEqual(backup.requests,[])
    async def test_sticky_backup_reprojects_step_then_new_task_resets(self):
        (self.root/'small.txt').write_text('example')
        primary=Client([failed()]);backup=Client([response(calls=[call('once','read_file','{"path":"small.txt"}')]),response('done')]);cfg=replace(self.config,provider='coco',model='primary')
        secondary=replace(cfg,provider='coco2',model='backup',context_token_budget={'mode':'estimate','input_limit':6500})
        gateway=ProviderFailoverClient(primary,cfg,secondary,lambda c:backup);agent=self.build(gateway,cfg)
        await agent.handle_message('first')
        self.assertEqual(agent.resources.context['input_token_limit'],6500);self.assertTrue(all(r['model']=='backup' for r in backup.requests))
        await agent.handle_message('second')
        self.assertEqual(agent.resources.context['input_token_limit'],8000);self.assertEqual(primary.requests[-1]['model'],'primary');self.assertEqual(len(backup.requests),2)
    async def test_single_provider_sdk_retries_disabled(self):
        with patch('mybot.config.AsyncOpenAI') as sdk:build_client(self.config)
        self.assertEqual(sdk.return_value.max_retries,0)
        client=build_client(self.config)
        try:self.assertEqual(client.max_retries,0)
        finally:await client.close()
    async def test_provider_level_option_fallback(self):
        import mybot.config as config
        with patch.object(config,'_LLM',{'provider':'coco'}),patch.object(config,'_PROVIDER_CONFIG',{'max_react_steps':7}):
            self.assertEqual(config._llm_value('max_react_steps',10),7)
        with patch.object(config,'_LLM',{'max_react_steps':9}),patch.object(config,'_PROVIDER_CONFIG',{'max_react_steps':7}):
            self.assertEqual(config._llm_value('max_react_steps',10),9)


def check_token_budget():run(TokenChecks)
if __name__=='__main__':check_token_budget()
