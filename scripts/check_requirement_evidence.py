"""Claim vs test record vs independent assertion, including native end-to-end tasks."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from mybot.agent.task_contract import TaskContract
from mybot.agent.coding_controller import CodingTaskController, AutonomySettings
from mybot.tools import build_default_tool_registry
from scripts.authority_contract_fixtures import (agent,configuration,prepare,requirement,
    PROMPTS,SyntheticClient)


class EvidenceChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        c=CodingTaskController(AutonomySettings(enabled=True),build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write'))
        self.contract=TaskContract(PROMPTS['A'],c);self.contract.record(requirements=[requirement()]);self.c=c

    def row(self):return self.contract.snapshot()['requirements'][0]
    def observed(self):
        self.c.verification='valid';self.c.last_verified_revision=0;self.c.test_runs=1;self.c.tests_passed_after_last_patch=2
        self.contract.observe_test()

    async def test_level_zero(self):
        self.assertEqual(self.row()['evidence_level'],0);self.assertEqual(self.row()['status'],'identified')

    async def test_claim_level_one_not_pass(self):
        self.contract.record(claims=['R1']);self.assertEqual(self.row()['evidence_level'],1)
        self.assertEqual(self.contract.snapshot()['requirement_coverage'],'unknown')

    async def test_fake_test_ref_rejected(self):
        with self.assertRaises(ValueError):self.contract.record(evidence_links=[{'requirement_id':'R1','evidence_ref':'Ran 10 tests OK'}])
        self.assertEqual(self.row()['evidence_level'],0)

    async def test_public_tests_no_automatic_coverage(self):
        self.observed();self.assertEqual(self.row()['evidence_level'],0)
        self.assertEqual(self.contract.snapshot()['requirement_coverage'],'unknown')

    async def test_declared_link_level_two_still_unknown(self):
        self.observed();self.contract.record(evidence_links=[{'requirement_id':'R1','evidence_ref':'test-1'}])
        self.assertEqual(self.row()['status'],'test_evidence_observed');self.assertEqual(self.row()['evidence_level'],2)
        self.assertEqual(self.row()['reason'],'test_execution_observed_coverage_unknown')
        self.assertEqual(self.contract.snapshot()['task_correctness'],'unknown')

    async def test_new_revision_invalidates_test(self):
        self.observed();self.contract.record(evidence_links=[{'requirement_id':'R1','evidence_ref':'test-1'}]);self.c.current_revision+=1
        self.assertEqual(self.row()['evidence_level'],0);self.assertEqual(self.row()['evidence_refs'],[])

    async def test_host_independent_assertion_level_three(self):
        self.assertTrue(self.contract.verify_independently('R1','independent-input',lambda:1+4==5))
        self.assertEqual(self.row()['evidence_level'],3)
        self.assertEqual(self.contract.snapshot()['requirement_coverage'],'verified')
        self.assertEqual(self.contract.snapshot()['task_correctness'],'unknown')

    async def test_failed_or_exception_assertion_no_verification(self):
        self.assertFalse(self.contract.verify_independently('R1','failed',lambda:False))
        def error():raise RuntimeError('not evidence')
        self.assertFalse(self.contract.verify_independently('R1','error',error));self.assertEqual(self.row()['evidence_level'],0)

    async def test_independent_revision_and_hash_invalidated(self):
        path=self.root/'core.py';path.write_text('safe');self.c.expected_hashes={'core.py':hashlib.sha256(path.read_bytes()).hexdigest()}
        # check_hashes uses native Patch tools, so attach a real one.
        self.c.tools=build_default_tool_registry(self.root,coding_enabled=True,patch_mode='write')
        self.assertTrue(self.contract.verify_independently('R1','current',lambda:True))
        path.write_text('user edit');self.assertNotEqual(self.row()['status'],'independently_verified')

    async def test_undo_invalidation(self):
        self.contract.verify_independently('R1','before-undo',lambda:True);self.contract.invalidate()
        self.assertEqual(self.row()['evidence_level'],0)

    async def test_public_payload_privacy_bounds(self):
        text='private prompt /Users/private/project token=never-publish'
        self.contract=TaskContract(text,self.c)
        self.contract.record(requirements=[requirement(text=text)])
        payload=json.dumps(self.contract.public_snapshot())
        for secret in ('private prompt','/Users/','never-publish','source_reference'):self.assertNotIn(secret,payload)
        self.assertLess(len(payload),16000)

    async def test_synthetic_A_real_receipt_test_revision(self):
        prepare(self.root,'A');events=[];a,c=agent(self.root,'A',callback=events.append)
        reply=await a.handle_message(PROMPTS['A']);r=a.last_coding_report;s=a.last_task_contract
        self.assertEqual(r['state'],'verified');self.assertEqual(r['committed_patches'],1)
        self.assertEqual(r['tests_passed_after_last_patch'],1);self.assertEqual(r['current_revision'],1)
        self.assertEqual(s['user_explicit_count'],1);self.assertEqual(s['test_evidence_count'],1)
        self.assertEqual(s['independently_verified_count'],0);self.assertEqual(s['task_correctness'],'unknown')
        self.assertIn('task_correctness=unknown',reply);self.assertEqual(len(c.requests),6)
        self.assertIn('return n + 1',(self.root/'core.py').read_text())
        self.assertTrue(any(e['type']=='tool_finished' and e['metadata'].get('receipt_commit_success') for e in events))

    async def test_synthetic_B_partial_business_coverage(self):
        prepare(self.root,'B');a,c=agent(self.root,'B');await a.handle_message(PROMPTS['B'])
        self.assertEqual(a.last_coding_report['state'],'verified')
        s=a.last_task_contract;self.assertEqual(s['user_explicit_count'],2)
        self.assertEqual(s['test_evidence_count'],1);self.assertEqual(s['missing_acceptance_count'],2)
        self.assertEqual(s['requirements'][1]['status'],'identified')
        self.assertEqual(s['requirement_coverage'],'unknown');self.assertEqual(s['task_correctness'],'unknown')
        # External acceptance demonstrates the uncovered request is actually unsatisfied.
        import subprocess,sys
        result=subprocess.run([sys.executable,'-c','from service import handle; assert handle(None)==[]'],cwd=self.root,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(a.last_coding_report['state'],'verified')

    async def test_web_contract_matches_cli_evidence(self):
        from mybot.web.runtime import ChatRuntime
        prepare(self.root,'B');runtime=ChatRuntime(configuration(self.root,'B'),client_factory=lambda cfg:SyntheticClient('B'))
        c=runtime.new();await runtime.start(c,PROMPTS['B'])
        # Synthetic approval by the harness, using the actual Web nonce resolver.
        while not c.task.done():
            if c.approval.pending:
                self.assertTrue(c.approval.resolve(c.approval.pending['id'],True))
            await asyncio.sleep(.01)
        await c.task
        self.assertEqual(c.report['state'],'verified');self.assertEqual(c.state()['contract']['requirement_coverage'],'unknown')
        self.assertEqual(c.contract['missing_acceptance_count'],2)
        event=json.dumps([e for e in c.events if e['type']=='task_contract'])
        self.assertNotIn(PROMPTS['B'],event);self.assertNotIn('preview_receipt',event)
        self.assertIn('缺少独立验收=2',c.messages[-1]['content']);await runtime.close()

    async def test_cancel_real_loop_preserves_contract(self):
        started=asyncio.Event();hold=asyncio.Event()
        class Client(SyntheticClient):
            async def create(inner,**kw):
                if inner.requests:started.set();await hold.wait()
                return await super().create(**kw)
        prepare(self.root,'A');a,_=agent(self.root,'A',client=Client('A'))
        task=asyncio.create_task(a.handle_message(PROMPTS['A']));await asyncio.wait_for(started.wait(),2);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(a.last_task_contract['established']);self.assertEqual(a.last_task_contract['requirements'][0]['status'],'blocked')
        self.assertEqual(a.last_task_contract['task_correctness'],'unknown');self.assertEqual(a.last_coding_report['committed_patches'],0)

    async def test_ui_has_no_success_inference_from_test_link(self):
        js=(Path(__file__).resolve().parents[1]/'mybot/web/static/app.js').read_text()
        self.assertIn('真实测试记录关联，覆盖未知',js);self.assertIn('任务正确性 unknown',js)
        self.assertIn(".textContent",js);self.assertNotIn('contract.innerHTML',js)


def check_requirement_evidence():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EvidenceChecks))
    if not result.wasSuccessful():raise AssertionError('requirement evidence checks failed')
if __name__=='__main__':check_requirement_evidence()
