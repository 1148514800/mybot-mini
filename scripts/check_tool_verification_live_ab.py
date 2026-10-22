"""Offline gates for the shared A/B driver; never sends model requests."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace as N

from scripts import tool_verification_live_ab as ab
from mybot.evaluation.coding_fixtures import load_benchmark
from mybot.evaluation.coding_judge import validate_benchmark
from mybot.evaluation.coding_failover import evaluate
from mybot.evaluation.coding_live import Limits
from scripts.check_session import response


class ABChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'requests').mkdir();(self.root/'attempts').mkdir()
        self.slot=ab.plan()[0]['slot']
        frozen=dict(slots=ab.plan(),providers=[dict(provider='coco',model='test-primary'),dict(provider='coco2',model='test-backup')])
        self.manifest=dict(frozen=frozen,frozen_sha256=ab.sha(frozen),attempts={r['slot']:str(i) for i,r in enumerate(ab.plan())})
        ab.write_new(self.root/'manifest.json',self.manifest)
        self.record=dict(attempt_id='0',case_id=ab.CASES[0],physical_request=1,provider='coco',model='test-primary',http_dispatch_count=0)
        self.audit=ab.RequestAudit(self.root,self.manifest,self.slot,lambda:None)

    def finish_request(self, number=1):
        record={**self.record,'physical_request':number}
        self.audit.before(record);record['http_dispatch_count']=1;self.audit.after(record)

    def test_exact_eight_unique_slots(self):
        rows=ab.plan();self.assertEqual(len(rows),8);self.assertEqual(len({r['slot'] for r in rows}),8)
        self.assertEqual([r['arm'] for r in rows],['baseline','candidate','candidate','baseline','baseline','candidate','candidate','baseline'])

    def test_matched_original_limits(self):
        self.assertEqual(ab.LIMITS['max_requests'],16);self.assertEqual(ab.LIMITS['max_model_requests_per_case'],16)
        self.assertEqual(ab.LIMITS['max_output_tokens'],2048);self.assertEqual(ab.LIMITS['task_timeout'],480)
        self.assertEqual(ab.LIMITS['request_timeout'],90);self.assertEqual(8*ab.LIMITS['max_requests'],128)

    def test_sources_pinned(self):
        self.assertEqual({r['source_commit'] for r in ab.plan()}, {ab.BASELINE,ab.CANDIDATE})
        self.assertNotEqual(ab.BASELINE,ab.CANDIDATE)

    def test_exclusive_evidence_write(self):
        p=self.root/'evidence.json';ab.write_new(p,{'a':1})
        with self.assertRaises(FileExistsError):ab.write_new(p,{'a':2})
        self.assertEqual(ab.read(p),{'a':1})

    def test_reservation_precedes_dispatch(self):
        self.audit.before(self.record)
        self.assertTrue((self.root/'requests/0001-started.json').is_file())
        self.assertFalse((self.root/'requests/0001-finished.json').exists())
        with self.assertRaises(ValueError):ab.validate_ledger(self.root,self.manifest)

    def test_settled_roundtrip(self):
        self.finish_request();rows=ab.validate_ledger(self.root,self.manifest)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['record']['http_dispatch_count'],1)

    def test_no_second_unsettled_reservation(self):
        self.audit.before(self.record)
        with self.assertRaises(ValueError):self.audit.before(self.record)

    def test_missing_reservation_rejected(self):
        with self.assertRaises(ValueError):self.audit.after(self.record)

    def test_manifest_tamper_stops(self):
        changed=copy.deepcopy(self.manifest);changed['attempts'][self.slot]='wrong'
        (self.root/'manifest.json').write_bytes(ab.encoded(changed))
        with self.assertRaises(ValueError):self.audit.before(self.record)

    def test_wrong_provider_rejected(self):
        with self.assertRaises(ValueError):self.audit.before({**self.record,'provider':'other'})

    def test_wrong_model_rejected(self):
        with self.assertRaises(ValueError):self.audit.before({**self.record,'model':'other'})

    def test_wrong_attempt_rejected(self):
        with self.assertRaises(ValueError):self.audit.before({**self.record,'attempt_id':'other'})

    def test_wrong_case_rejected(self):
        with self.assertRaises(ValueError):self.audit.before({**self.record,'case_id':'other'})

    def test_wrong_request_number_rejected(self):
        with self.assertRaises(ValueError):self.audit.before({**self.record,'physical_request':2})

    def test_guard_runs_before_reservation(self):
        def changed():raise ValueError('source_changed')
        self.audit.guard=changed
        with self.assertRaises(ValueError):self.audit.before(self.record)
        self.assertFalse(list((self.root/'requests').iterdir()))

    def test_stopped_campaign_rejected(self):
        ab.write_new(self.root/'stopped.json',{'reason':'test'})
        with self.assertRaises(ValueError):self.audit.before(self.record)

    def test_per_attempt_sixteen_cap(self):
        for n in range(1,17):self.finish_request(n)
        with self.assertRaises(ValueError):self.audit.before({**self.record,'physical_request':17})
        self.assertEqual(len(list((self.root/'requests').glob('*-started.json'))),16)

    def test_global_128_cap(self):
        with patch.object(ab,'validate_ledger',return_value=[{'slot':'other'}]*128):
            with self.assertRaises(ValueError):self.audit.before(self.record)
        self.assertFalse(list((self.root/'requests').iterdir()))

    def test_fallback_uses_same_budget(self):
        self.finish_request()
        record={**self.record,'physical_request':2,'provider':'coco2','model':'test-backup'}
        self.audit.before(record);record['http_dispatch_count']=1;self.audit.after(record)
        self.assertEqual(len(ab.validate_ledger(self.root,self.manifest)),2)

    def test_transport_retry_observation_rejected(self):
        self.audit.before(self.record);self.record['http_dispatch_count']=2;self.audit.after(self.record)
        with self.assertRaises(ValueError):ab.validate_ledger(self.root,self.manifest)

    def test_outcome_tamper_rejected(self):
        self.finish_request();p=self.root/'requests/0001-finished.json';r=ab.read(p)
        r['record']['attempt_id']='wrong';p.write_bytes(ab.encoded(r))
        with self.assertRaises(ValueError):ab.validate_ledger(self.root,self.manifest)

    def test_reservation_hash_tamper_rejected(self):
        self.finish_request();p=self.root/'requests/0001-started.json';r=ab.read(p)
        r['record']['case_id']='other';p.write_bytes(ab.encoded(r))
        with self.assertRaises(ValueError):ab.validate_ledger(self.root,self.manifest)

    def test_slot_once_only(self):
        ab.check_slot(self.root,self.manifest,self.slot)
        (self.root/'attempts'/self.slot).mkdir()
        with self.assertRaises(ValueError):ab.check_slot(self.root,self.manifest,self.slot)

    def test_prior_incomplete_stops_next(self):
        with self.assertRaises(ValueError):ab.check_slot(self.root,self.manifest,ab.plan()[1]['slot'])

    def test_corrupt_frozen_manifest(self):
        changed=copy.deepcopy(self.manifest);changed['frozen']['slots'][0]['arm']='other'
        with self.assertRaises(ValueError):ab.check_slot(self.root,changed,self.slot)

    def test_namespace_blocks_historical(self):
        with self.assertRaises(ValueError):ab.campaign_path(ab.ROOT/'runs/coding_failover/full-batch-001')

    async def test_new_benchmark_valid_before_live(self):
        b=load_benchmark(ab.BENCHMARK);rows=await validate_benchmark(b)
        self.assertEqual(len(rows),4);self.assertTrue(all(r['status']=='valid' for r in rows))
        self.assertTrue(all(r['public_tests']==2 and r['hidden_tests']==6 for r in rows))

    def test_new_ids_disjoint_from_historical(self):
        old=load_benchmark();new=load_benchmark(ab.BENCHMARK)
        self.assertFalse({c.runtime.id for c in old.cases}&{c.runtime.id for c in new.cases})

    async def test_shared_original_harness_protocol_and_private_judge(self):
        # Explicit synthetic positive public workflow, intentionally incomplete type validation.
        # It must remain Strict Fail despite a legal Controller finish.
        class Client:
            def __init__(self):self.chat=N(completions=N(create=self.create));self.step=0;self.hash=None
            async def create(self,**kw):
                self.step+=1
                def call(name,args):return response(calls=[N(id=str(self.step),function=N(name=name,arguments=json.dumps(args)))])
                if self.step==1:return call('read_file_range',dict(path='app/buckets.py',start_line=1,end_line=20))
                if self.step==2:
                    self.hash=json.loads(kw['messages'][-1]['content'].split('metadata=')[-1])['file_sha256']
                if self.step in (2,3):return call('apply_patch',dict(dry_run=self.step==2,changes=[dict(op='update',path='app/buckets.py',expected_sha256=self.hash,edits=[dict(old_text='return sum(value > limit for limit in thresholds)',new_text='return sum(limit <= value for limit in thresholds)')])]))
                if self.step==4:return call('run_command',dict(argv=['python','-m','unittest','discover','-s','tests','-v']))
                return response('done')
        report=await evaluate(benchmark=load_benchmark(ab.BENCHMARK),case_ids=[ab.CASES[0]],provider_mode='failover',
            limits=Limits(max_cases=1,repeats=1,max_requests=6,max_model_requests_per_case=6),offline_provider_factory=lambda runtime,provider:Client())
        from mybot.evaluation.coding_campaign import strict_success
        r=report['results'][0];self.assertEqual(r['agent_state'],'verified');self.assertEqual(r['judge']['judge_state'],'hidden_fail')
        self.assertFalse(strict_success(report));self.assertTrue(r['metrics']['tool_call_ids_paired'])
        self.assertEqual(r['metrics']['committed_patches'],1)


def check_tool_verification_live_ab():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ABChecks))
    if not r.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':check_tool_verification_live_ab()
