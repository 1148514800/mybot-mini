"""Synthetic instruction-policy checks; never evidence of real model improvement."""
import asyncio
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace as N
from dataclasses import replace
from unittest.mock import patch
from mybot.agent.coding_controller import CodingTaskController,AutonomySettings
from mybot.config import GatewayConfig
from mybot.tools import build_default_tool_registry
from mybot.evaluation.coding_benchmark import evaluate
from mybot.evaluation.coding_live import Limits
from scripts.coding_benchmark_demo import DemoClient
from scripts.check_session import response,call


class EfficiencyChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=CodingTaskController(AutonomySettings(enabled=True,max_model_requests=5),build_default_tool_registry(Path(self.temp.name)))
    def ready(self):
        self.c.committed_patches=1;self.c.current_revision=self.c.last_verified_revision=1
        self.c.verification='valid';self.c.tests_passed_after_last_patch=2;self.c.check_hashes=lambda:True
    def state(self):
        s=self.c.instruction();return json.loads(s[s.rfind('{'):])
    def test_initial_never_ready(self):self.assertFalse(self.state()['ready_to_finish'])
    def test_last_request_explicit(self):
        self.c.model_requests=4;self.assertIn('LAST model request',self.c.instruction());self.assertEqual(self.state()['model_requests_remaining'],1)
    def test_valid_revision_finishes(self):
        self.ready();self.assertTrue(self.state()['ready_to_finish']);self.assertIn('finish with a concise final reply now',self.c.instruction())
    def test_last_valid_finalizes(self):
        self.ready();self.c.model_requests=4;self.assertIn('finalize using the valid evidence',self.c.instruction())
    def test_last_incomplete_honest(self):
        self.c.model_requests=4;self.assertIn('report the incomplete state honestly',self.c.instruction())
    def test_patch_without_test(self):
        self.ready();self.c.verification='pending';self.assertFalse(self.state()['ready_to_finish'])
    def test_stale_revision_not_ready(self):
        self.ready();self.c.current_revision=2;self.assertFalse(self.state()['ready_to_finish'])
    def test_zero_tests_not_ready(self):
        self.ready();self.c.tests_passed_after_last_patch=0;self.assertFalse(self.state()['ready_to_finish'])
    def test_changed_hash_not_ready(self):
        self.ready();self.c.check_hashes=lambda:False;self.assertFalse(self.state()['ready_to_finish'])
    def test_cancelled_not_ready(self):
        self.ready();self.c.stop('cancelled','task_cancelled');self.assertFalse(self.state()['ready_to_finish'])
    def test_uncertain_not_ready(self):
        self.ready();self.c.stop('execution_uncertain','tool');self.assertFalse(self.state()['ready_to_finish'])
    def test_budget_stop_still_invalid(self):
        self.ready();self.c.model_requests=5;self.assertFalse(self.c.before_request([]));self.assertEqual(self.c.state,'budget_exhausted');self.assertEqual(self.c.verification,'invalid')
    def test_instruction_never_auto_verifies(self):
        self.ready();self.c.instruction();self.assertEqual(self.c.state,'running');self.assertEqual(self.c.model_requests,0)
    def test_cross_module_guidance_retained(self):
        for s in ('trace entry, transformation, validation and return paths','callers','integrated behavior'):self.assertIn(s,self.c.instruction())
    def test_constraints_retained(self):
        for s in ('expected_sha256','dry_run=false','approved','Denial/uncertain execution stops','One write OR command','budgets cannot increase'):self.assertIn(s,self.c.instruction())
    def test_avoid_unnecessary_exploration(self):
        self.assertIn('avoid repeated listings or unrelated README/notes',self.c.instruction())
    def test_shorter_than_frozen_instruction(self):
        source=subprocess.check_output(['git','show','3ccd2df:mybot/agent/coding_controller.py'],stderr=subprocess.DEVNULL,text=True)
        namespace=dict(vars(__import__('mybot.agent.coding_controller',fromlist=['x'])))
        exec(compile(source,'<frozen-controller>','exec'),namespace)
        original=namespace['CodingTaskController'].instruction
        for used in (0,4):
            self.c.model_requests=used
            self.assertLess(len(self.c.instruction()),len(original(self.c)))
    async def test_synthetic_before_after_original_loop_real_tools(self):
        # Explicitly synthetic response policy: optional extra action without closing cue.
        # Both arms run the same original AgentLoop, real patch, sandboxed unittest and Judge.
        class Policy(DemoClient):
            def __init__(self):super().__init__();self.optional=False
            async def create(self,**kw):
                result=await super().create(**kw)
                if not result.choices[0].message.tool_calls and not self.optional:
                    if 'finish with a concise final reply now' not in kw['messages'][0]['content']:
                        self.optional=True
                        return N(choices=[N(message=N(content=None,tool_calls=[N(id='synthetic-optional',function=N(name='read_file',arguments=json.dumps({'path':'notes.txt'})))]),finish_reason='tool_calls')],usage=None)
                return result
        baseline=subprocess.check_output(['git','show','3ccd2df:mybot/agent/coding_controller.py'],text=True,stderr=subprocess.DEVNULL)
        namespace=dict(vars(__import__('mybot.agent.coding_controller',fromlist=['x'])))
        # Trusted frozen source, offline only; original instruction method for comparison.
        exec(compile(baseline,'<frozen-controller>','exec'),namespace)
        original=namespace['CodingTaskController'].instruction
        options=dict(base_config=GatewayConfig(context_token_budget={'input_limit':160000}),limits=Limits(max_cases=1,max_requests=5,max_model_requests_per_case=5),case_ids=['cache-ttl-001'],offline_client_factory=lambda public:Policy())
        with patch.object(CodingTaskController,'instruction',original):old=await evaluate(**options)
        new=await evaluate(**options)
        self.assertEqual(old['results'][0]['agent_state'],'budget_exhausted',json.dumps(old['results'][0]))
        self.assertEqual(new['results'][0]['agent_state'],'verified')
        self.assertTrue(new['results'][0]['metrics']['tool_call_ids_paired'])
        self.assertEqual(new['results'][0]['metrics']['committed_patches'],1)
        self.assertEqual(new['results'][0]['metrics']['real_test_runs'],1)
        self.assertEqual(new['results'][0]['judge']['judge_state'],'hidden_pass')
        self.assertEqual(old['mode'],'offline');self.assertFalse(new['ability_score'])


def check_request_budget_efficiency():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EfficiencyChecks))
    if not r.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':check_request_budget_efficiency()
