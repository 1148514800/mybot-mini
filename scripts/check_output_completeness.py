"""Protocol delivery, canonical Session and real native coding E2E. OFFLINE only."""
import asyncio
import contextlib
import io
from types import SimpleNamespace as N
from unittest.mock import patch

from mybot.agent import AgentLoop, ContextBuilder
from mybot.runtime_accounting import response_status
from mybot.web.runtime import ChatRuntime
from scripts.modernization_fixtures import Base, Client, response, call, run


def delivered(text='partial body', reason='stop', calls=None):
    value=response(text,calls);value.choices[0].finish_reason=reason
    value.usage=N(prompt_tokens=7,completion_tokens=3,total_tokens=10)
    return value


class OutputChecks(Base):
    async def output(self, reason, text='partial body'):
        self.client.effects=[delivered(text,reason)]
        reply=await self.agent.handle_message('Cover all requested sections concisely')
        return reply,self.agent.last_runtime_report

    async def test_length_keeps_text_user_and_no_automatic_request(self):
        reply,r=await self.output('length')
        self.assertIn('partial body',reply);self.assertIn('输出长度限制',reply)
        self.assertEqual(r['outcome'],'output_truncated');self.assertFalse(r['output']['complete'])
        self.assertEqual((len(self.client.requests),r['physical_requests']),(1,1))
        turns=self.agent.session.export_turns();self.assertEqual(turns[0][0]['role'],'user');self.assertIn('partial body',turns[0][-1]['content'])

    async def test_complete_is_delivery_not_correctness(self):
        reply,r=await self.output('stop','complete text')
        self.assertEqual(reply,'complete text');self.assertEqual(r['outcome'],'completed')
        self.assertEqual(r['task_correctness'],'unknown');self.assertTrue(r['output']['complete'])

    async def test_filter_does_not_complete(self):
        _,r=await self.output('content_filter');self.assertEqual(r['outcome'],'content_filtered')

    async def test_empty_response_does_not_complete(self):
        _,r=await self.output('stop','  ');self.assertEqual(r['outcome'],'empty_response')

    async def test_unknown_and_missing_finish_are_unconfirmed(self):
        for reason in ('unrecognized',None):
            with self.subTest(reason=reason):
                _,r=await self.output(reason);self.assertEqual(r['outcome'],'response_unconfirmed')
                self.assertEqual(r['output']['finish_reason'],'unknown')

    async def test_bad_choices_preserve_user_input(self):
        for value in (N(choices=[],usage=None),N(choices=[N(message=None,finish_reason='stop')],usage=None)):
            self.client.effects=[value];await self.agent.handle_message('user survives')
            self.assertEqual(self.agent.last_runtime_report['outcome'],'provider_error')
            self.assertEqual(self.agent.session.export_turns()[-1][0]['content'],'user survives')

    async def test_truncated_prose_survives_unfinished_plan(self):
        self.client.effects=[response(calls=[call('plan','create_plan','{"steps":["inspect","report"]}')]),delivered('partial planned reply','length')]
        reply=await self.agent.handle_message('inspect and report')
        self.assertIn('partial planned reply',reply);self.assertIn('partial planned reply',self.agent.session.history()[-1]['content'])
        self.assertEqual(self.agent.resources.outcome,'output_truncated');self.assertEqual(len(self.client.requests),2)

    async def test_provider_error_not_full_success(self):
        v=delivered();v.error={'sensitive':'not to expose'};self.client.effects=[v]
        reply=await self.agent.handle_message('hello');self.assertEqual(self.agent.resources.outcome,'provider_error')
        self.assertNotIn('sensitive',reply)

    async def test_partial_tool_arguments_never_execute(self):
        self.client.effects=[delivered('partial','length',[call('partial','write_file','{"path":"bad","content":"x"}')])]
        await self.agent.handle_message('no incomplete side effects')
        self.assertFalse((self.root/'bad').exists());self.assertEqual(len(self.client.requests),1)
        self.assertFalse(any(m.get('tool_calls') for m in self.agent.session.history()))

    async def test_conflicting_stop_with_calls_does_not_execute(self):
        v=delivered('','stop',[call('bad','write_file','{"path":"bad","content":"x"}')]);self.client.effects=[v]
        await self.agent.handle_message('hello');self.assertEqual(self.agent.resources.outcome,'provider_error');self.assertFalse((self.root/'bad').exists())

    async def test_existing_tool_pairs_survive_truncated_final(self):
        self.client.effects=[response(calls=[call('list-id','list_files','{"path":"."}')]),delivered('partial','length')]
        await self.agent.handle_message('inspect');turn=self.agent.session.export_turns()[0]
        self.assertEqual(turn[1]['tool_calls'][0]['id'],turn[2]['tool_call_id']);self.assertEqual(len(self.client.requests),2)

    async def test_tool_failure_remains_distinct(self):
        self.client.effects=[response(calls=[call('missing','read_file','{"path":"absent"}')]),delivered('cannot inspect')]
        await self.agent.handle_message('inspect missing');r=self.agent.last_runtime_report
        self.assertEqual(r['tool_failures'],1);self.assertTrue(r['output']['complete']);self.assertEqual(r['task_correctness'],'unknown')

    async def test_cli_and_web_match_protocol_evidence(self):
        self.client.effects=[delivered('partial','length')]
        with patch('builtins.input',side_effect=['hello','exit']),contextlib.redirect_stdout(io.StringIO()) as out:
            await self.agent.run()
        self.assertIn('output_truncated',out.getvalue());self.assertIn('complete=False',out.getvalue())
        runtime=ChatRuntime(self.config,client_factory=lambda c:Client([delivered('partial','length')]))
        try:
            c=runtime.new();await runtime.start(c,'hello');await c.task
            self.assertEqual(c.status,'output_truncated');self.assertEqual(c.resources['output'],self.agent.last_runtime_report['output'])
            self.assertEqual(c.events[-1]['type'],'message_incomplete');self.assertIn('partial',c.messages[-1]['content'])
        finally:await runtime.close()

    async def test_native_patch_and_revision_survive_truncated_final(self):
        from scripts.check_patch_preview_receipt import init
        from scripts.check_web_ui import config,SyntheticClient
        from scripts.check_tool_verification_reliability import approve
        from mybot.tools import build_default_tool_registry
        init(self.root);cfg=config(self.root,True)
        class TruncatedClient(SyntheticClient):
            async def create(self,**kw):
                v=await super().create(**kw)
                if not v.choices[0].message.tool_calls:
                    v.choices[0].finish_reason='length';v.choices[0].message.content='partial final after test'
                return v
        client=TruncatedClient(cfg)
        tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write',preview_receipt=True,
            command={'mode':'macos_readonly'},command_approval_provider=approve)
        a=AgentLoop(client,cfg,tools,ContextBuilder(self.root))
        try:
            reply=await a.handle_message('修复')
            self.assertEqual(a.last_coding_report['state'],'verified');self.assertEqual(a.last_coding_report['current_revision'],1)
            self.assertEqual(a.last_coding_report['committed_patches'],1);self.assertGreater(a.last_coding_report['tests_passed_after_last_patch'],0)
            self.assertEqual(a.resources.outcome,'output_truncated');self.assertIn('partial final',reply)
            self.assertNotIn('return 1', (self.root/'value.py').read_text())
        finally:
            if a._git_capsule:a._git_capsule.close()

    async def test_failover_budget_and_usage_unchanged(self):
        from dataclasses import replace
        from mybot.provider_failover import ProviderFailoverClient
        from scripts.check_provider_failover import failed
        cfg=replace(self.config,provider='coco');backup=Client([delivered('partial','length')])
        gateway=ProviderFailoverClient(Client([failed()]),cfg,replace(cfg,provider='coco2'),lambda c:backup)
        a=self.build(gateway,cfg)
        await a.handle_message('hello');r=a.last_runtime_report
        self.assertEqual(r['physical_requests'],2);self.assertTrue(r['fallback_used']);self.assertEqual(r['outcome'],'output_truncated')
        self.assertEqual(len(backup.requests),1)


def check_output_completeness():run(OutputChecks)
if __name__=='__main__':check_output_completeness()
