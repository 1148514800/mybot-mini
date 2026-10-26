import tempfile,unittest
from pathlib import Path
from mybot.agent.steer import SteerInbox
from mybot.storage.history import SessionHistory,open_store
from mybot.storage.event_schema import StoreError,Event,identifier
from scripts.eventstore_fixtures import configuration

class SteerChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.cfg=configuration(Path(self.tmp.name).resolve());self.s=open_store(self.cfg,'web');self.addCleanup(self.s.close);self.h=SessionHistory(self.s);self.h.start('原始任务');self.inbox=SteerInbox(self.h)
    def submit(self,**kw):return self.inbox.submit(**(dict(expected_turn_id=self.h.turn_id,client_request_id='request-1',text='先查看测试，不要修改文件。')|kw))
    def test_queued_source_separate(self):
        r=self.submit();self.assertEqual(r['status'],'queued');self.assertEqual(len(self.h.messages()),1);self.assertEqual(self.h.pins.list(),[]);self.assertEqual(self.h.decisions()['items'],[])
    def test_idle_rejected(self):
        self.h.finish('done');h=SessionHistory(self.s);inbox=SteerInbox(h)
        with self.assertRaises(StoreError):inbox.submit(None,'a','text')
    def test_old_turn_rejected(self):
        with self.assertRaises(StoreError):self.submit(expected_turn_id=identifier())
    def test_cross_session_rejected(self):
        other=SessionHistory(self.s);other.start('other')
        with self.assertRaises(StoreError):self.submit(expected_turn_id=other.turn_id)
        other.finish('done')
    def test_duplicate_idempotent(self):
        a=self.submit();self.assertEqual(self.submit(),a);self.assertEqual(len(self.s.query("SELECT * FROM events WHERE event_type='steer.queued'")),1)
    def test_id_same_different_text_rejected(self):
        self.submit()
        with self.assertRaises(StoreError):self.submit(text='different')
    def test_capacity_one(self):
        self.submit()
        with self.assertRaises(StoreError):self.submit(client_request_id='second')
    def test_resolve_and_next_slot(self):
        self.submit();self.inbox.resolve('applied','next_step');r=self.submit(client_request_id='second');self.assertEqual(r['status'],'queued')
    def test_replay_applied_id_does_not_apply_twice(self):
        self.submit();self.inbox.resolve('applied','next_step');self.assertEqual(self.submit()['status'],'applied');self.assertIsNone(self.inbox.pending)
    def test_empty_rejected(self):
        with self.assertRaises(StoreError):self.submit(text=' ')
    def test_length_rejected(self):
        with self.assertRaises(StoreError):self.submit(text='x'*2001)
    def test_secret_rejected(self):
        with self.assertRaises(StoreError):self.submit(text='password=private-value')
    def test_invalid_client_id(self):
        with self.assertRaises(StoreError):self.submit(client_request_id='../file')
    def test_not_applied_no_extra_model(self):
        self.submit();self.inbox.resolve('not_applied','no_next_step');self.assertIsNone(self.inbox.pending);self.assertEqual(self.inbox.records['request-1']['status'],'not_applied')
    def test_stop_discards(self):
        self.submit();self.inbox.resolve('discarded_on_stop','stop');self.assertIsNone(self.inbox.reference())
    def test_restart_never_restores_queue(self):
        self.submit();sid=self.h.sid;self.h.interrupt('process_stopped');self.s.close();self.s=open_store(self.cfg,'web');self.addCleanup(self.s.close);self.h=SessionHistory(self.s,sid);rows=SteerInbox.audit(self.h);self.assertEqual(rows[0]['status'],'not_applied');self.assertIsNone(SteerInbox(self.h).pending)
    def test_model_cannot_emit_steer(self):
        p=dict(turn_id=self.h.turn_id,steer_id=identifier(),client_request_id='m',text='model')
        with self.assertRaises(StoreError):self.s.append(Event.create(self.h.sid,'steer.queued',p,source='model'))
    def test_schema_version_separate(self):
        self.submit();row=self.s.query("SELECT schema_version FROM events WHERE event_type='steer.queued'")[0];self.assertEqual(row['schema_version'],2);self.assertEqual(self.s.query("SELECT schema_version FROM events WHERE event_type='user.message'")[0]['schema_version'],1)
    def test_unpaired_resolution_rejected(self):
        with self.assertRaises(StoreError):self.h.event('steer.resolved',dict(turn_id=self.h.turn_id,steer_id=identifier(),state='applied',cause='next_step'))
    def test_applied_reference_not_original_user(self):
        r=self.submit();ref=self.inbox.reference();self.assertEqual(ref['role'],'user');self.assertIn(r['source_event_id'],ref['content']);self.assertEqual(self.h.messages()[0]['content'],'原始任务')
    def test_audit_applied_state(self):
        self.submit();self.inbox.resolve('applied','next_step');self.assertEqual(SteerInbox.audit(self.h)[0]['status'],'applied')
    def test_queued_event_does_not_make_new_turn(self):
        before=self.s.query('SELECT count(*) AS n FROM turns')[0]['n'];self.submit();self.assertEqual(self.s.query('SELECT count(*) AS n FROM turns')[0]['n'],before)

def check_steer_inbox():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SteerChecks))
    if not r.wasSuccessful():raise AssertionError('steer inbox checks failed')
if __name__=='__main__':check_steer_inbox()
