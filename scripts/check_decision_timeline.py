"""Transactional time boundaries, migration and restart, without live data."""
import json,sqlite3,unittest
from dataclasses import replace
from mybot.storage.event_schema import Event,StoreError,identifier
from mybot.storage.history import SessionHistory,open_store
from scripts import check_decision_provenance as provenance
from scripts.source_projection_fixtures import stored,pin,revoke

class TimelineChecks(provenance.DecisionFixture):
    # Only these tests belong to this suite (shared setup, not inherited tests).
    def old(self):
        mid,_=stored(self.h,'命名为 index.md。');p=pin(self.h,mid,'命名为 index.md。');return p,self.h.decisions()['boundary']
    def replaced(self):
        old,b=self.old();mid,_=stored(self.h,'命名为 catalog.md。');new=pin(self.h,mid,'命名为 catalog.md。',replace_id=old['id'],expected_revision=old['revision']);return old,b,new,self.h.decisions()['boundary']
    def active(self,b=None):return {p['pin_id'] for p in self.h.decisions(boundary=b)['items'] if p['status_at_boundary']=='active'}
    def test_add_current_and_event_evidence(self):
        p,b=self.old();v=self.h.decisions()['items'][0];self.assertEqual(v['valid_from'],b);self.assertEqual(v['confirmation_event_sequence'],b);self.assertEqual(self.active(),{p['id']})
    def test_before_replace_old_effective(self):
        old,b,new,end=self.replaced();self.assertEqual(self.active(b),{old['id']})
    def test_after_replace_history_not_retroactive(self):
        old,b,new,end=self.replaced();v={p['pin_id']:p for p in self.h.decisions()['items']};self.assertEqual(v[old['id']]['valid_until'],end);self.assertEqual(v[new['id']]['valid_from'],end);self.assertEqual(self.active(),{new['id']});self.assertEqual(v[old['id']]['current_lifecycle_status'],'superseded')
    def test_revoke_boundary(self):
        old,b,new,end=self.replaced();revoke(self.h,new);self.assertEqual(self.active(end),{new['id']});self.assertEqual(self.active(),set());self.assertEqual(self.active(b),{old['id']})
    def test_internal_replace_boundary_rejected(self):
        old,b,new,end=self.replaced()
        with self.assertRaises(StoreError):self.h.decisions(boundary=end-1)
    def test_unknown_and_future_rejected(self):
        self.old()
        for b in (-1,999999,True,'1'):
            with self.assertRaises(StoreError):self.h.decisions(boundary=b)
    def test_empty_committed_boundary(self):self.assertEqual(self.active(0),set())
    def test_restart_identical(self):
        self.replaced();before=self.h.decisions();self.s.close();self.s=open_store(self.cfg,'cli');self.addCleanup(self.s.close);self.h=SessionHistory(self.s,self.h.sid);self.assertEqual(self.h.decisions(),before)
    def test_timestamp_not_order(self):
        mid,_=stored(self.h,'abc');e=Event.create(self.h.sid,'pin.added',dict(pin_id=identifier(),category='user_constraint',content='abc',source_message_id=mid,start=0,end=3),source='user_confirmed');self.s.append(replace(e,timestamp=1.0));v=self.h.decisions()['items'][0];self.assertEqual(v['valid_from'],self.h.decisions()['boundary']);self.assertNotEqual(v['valid_from'],1)
    def test_revision_not_boundary(self):
        old,b,new,end=self.replaced();self.assertNotEqual(new['revision'],end);self.assertEqual(self.h.decisions()['items'][0]['valid_from'],end)
    def test_arbitrary_multi_add_atomic_boundary(self):
        mid,_=stored(self.h,'abc def');events=[Event.create(self.h.sid,'pin.added',dict(pin_id=identifier(),category='user_constraint',content=q,source_message_id=mid,start=a,end=a+3),source='user_confirmed') for q,a in [('abc',0),('def',4)]];a,b=self.s.append_many(events)
        with self.assertRaises(StoreError):self.h.decisions(boundary=a)
        self.assertEqual(len(self.active(b)),2);self.assertEqual({p['valid_from'] for p in self.h.decisions()['items']},{b})
    def test_failed_replace_no_commit_boundary(self):
        old,b=self.old();mid,_=stored(self.h,'new');before=self.h.decisions()
        with self.assertRaises(StoreError):pin(self.h,mid,'new',replace_id=old['id'],expected_revision=999)
        self.assertEqual(self.h.decisions(),before)
    def test_idempotent_append_no_false_commit(self):
        e=Event.create(self.h.sid,'context.cleared',{});self.s.append(e);before=self.h.decisions();self.s.append(e);self.assertEqual(self.h.decisions(),before)
    def test_namespace_isolation(self):
        self.old();other=open_store(self.cfg,'web');self.addCleanup(other.close)
        from mybot.storage.decision_timeline import DecisionTimeline
        with self.assertRaises(StoreError):DecisionTimeline(other,self.h.sid).view()
    def test_bounds_and_no_authorization(self):
        self.replaced();v=self.h.decisions(limit=1);self.assertEqual(len(v['items']),1);self.assertEqual(v['omitted'],1);self.assertFalse(v['execution_authority_restored']);self.assertNotIn('receipt',json.dumps(v).lower())
    def test_v1_migration_does_not_fabricate_history(self):
        old,b,new,end=self.replaced();self.h.clear_context();before=self.s.query('SELECT event_id,canonical FROM events ORDER BY sequence');sid=self.h.sid;self.s.close()
        with sqlite3.connect(self.cfg.session_event_path) as db:db.execute('DROP TABLE event_commits');db.execute('PRAGMA user_version=1')
        self.s=open_store(self.cfg,'cli');self.addCleanup(self.s.close);self.h=SessionHistory(self.s,sid);v=self.h.decisions();self.assertFalse(v['historical_boundaries_complete']);self.assertEqual(self.active(),{new['id']});self.assertIsNone(v['items'][0]['valid_from']);self.assertEqual(self.s.query('SELECT event_id,canonical FROM events ORDER BY sequence'),before)
        from mybot.agent.decision_provenance import render_view
        self.assertIn('边界未知',render_view(v));self.assertNotIn('失效顺序 未失效',render_view({'items':[i for i in v['items'] if i['ended_sequence'] is not None],**{k:x for k,x in v.items() if k!='items'}}))
        with self.assertRaises(StoreError):self.h.decisions(boundary=b)
    def test_invalid_commit_index_rejected(self):
        self.old();self.s.close()
        with sqlite3.connect(self.cfg.session_event_path) as db:db.execute('DELETE FROM event_commits WHERE end_sequence=(SELECT max(end_sequence) FROM event_commits)')
        with self.assertRaises(StoreError):open_store(self.cfg,'cli')
    def test_zero_length_interval_not_formerly_effective(self):
        mid,_=stored(self.h,'abc');pid=identifier()
        events=[Event.create(self.h.sid,'pin.added',dict(pin_id=pid,category='user_constraint',content='abc',source_message_id=mid,start=0,end=3),source='user_confirmed'),Event.create(self.h.sid,'pin.revoked',dict(pin_id=pid,expected_revision=1),source='user_confirmed')]
        self.s.append_many(events);v=self.h.decisions()['items'][0];self.assertFalse(v['ever_effective']);self.assertEqual(v['valid_from'],v['valid_until']);self.assertEqual(self.active(),set())
    def test_same_transaction_multiple_replacements_one_visible_state(self):
        old,b=self.old();mid,_=stored(self.h,'abc def');a=identifier();z=identifier()
        events=[Event.create(self.h.sid,'pin.added',dict(pin_id=i,category='user_constraint',content=q,source_message_id=mid,start=n,end=n+3),source='user_confirmed') for i,q,n in [(a,'abc',0),(z,'def',4)]]
        events += [Event.create(self.h.sid,'pin.superseded',dict(pin_id=old['id'],new_pin_id=a,expected_revision=old['revision']),source='user_confirmed'),Event.create(self.h.sid,'pin.superseded',dict(pin_id=a,new_pin_id=z,expected_revision=2),source='user_confirmed')]
        seqs=self.s.append_many(events);self.assertEqual(self.active(),{z});self.assertFalse(next(p for p in self.h.decisions()['items'] if p['pin_id']==a)['ever_effective'])
        for seq in seqs[:-1]:
            with self.assertRaises(StoreError):self.h.decisions(boundary=seq)
    def test_delete_cascades_commit_metadata(self):
        self.old();sid=self.h.sid;self.s.delete(sid);self.assertEqual(self.s.query('SELECT * FROM event_commits WHERE session_id=?',(sid,)),[])


def check_decision_timeline():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TimelineChecks))
    if not r.wasSuccessful():raise AssertionError('decision timeline checks failed')
if __name__=='__main__':check_decision_timeline()
