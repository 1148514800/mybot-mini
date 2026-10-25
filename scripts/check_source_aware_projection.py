"""Provenance and independent fact preservation, with real private temporary SQLite."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import tempfile,unittest,json
from mybot.storage.history import SessionHistory,open_store
from mybot.agent.session import Session,HistoryTurn
from mybot.storage.context_projection import MASK,SOURCE_LABEL
from mybot.storage.event_schema import identifier
from scripts.eventstore_fixtures import configuration
from scripts.source_projection_fixtures import stored,pin,revoke,source_fixture,OLD,NEW,UNITS,baseline_projection

class SourceChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.cfg=configuration(self.root);self.store=open_store(self.cfg,'cli');self.addCleanup(self.store.close);self.h=SessionHistory(self.store)
    def sample(self,text='撤销规则。保留事实。',rule='撤销规则。'):
        mid,t=stored(self.h,text);p=pin(self.h,mid,rule);revoke(self.h,p);return mid,t,p
    def test_exact_source_and_preservation(self):
        _,t,_=self.sample();v=self.h.context_turns([t]);self.assertIn('保留事实。',v[0][0]['content']);self.assertNotIn('撤销规则。',str(v));self.assertIn(MASK,str(v));self.assertEqual(self.h.projection_diagnostics['redacted_source_spans'],1)
    def test_unicode_codepoints(self):
        _,t,_=self.sample('👩🏽‍💻前缀。撤销规则。保留🧭事实。');v=self.h.context_turns([t]);self.assertIn('👩🏽‍💻前缀。',v[0][0]['content']);self.assertIn('保留🧭事实。',v[0][0]['content'])
    def test_same_sentence_twice_masks_only_bound_span(self):
        _,t,_=self.sample('撤销规则。保留事实。撤销规则。');v=self.h.context_turns([t]);self.assertEqual(v[0][0]['content'].count('撤销规则。'),1)
    def test_equal_messages_have_distinct_identity(self):
        _,t,_=self.sample();_,other=stored(self.h,'撤销规则。保留事实。');v=self.h.context_turns([t,other]);self.assertEqual(v[1][0]['content'],'撤销规则。保留事实。')
    def test_cross_session_provenance_rejected(self):
        _,t,_=self.sample();other=SessionHistory(self.store);_,foreign=stored(other,'撤销规则。保留事实。');self.assertEqual(self.h.context_turns([foreign]),[]);self.assertIn('turn_identity_unavailable',self.h.projection_diagnostics['source_mapping_failure_reasons'])
    def test_missing_source_id(self):
        _,t,p=self.sample();records=self.h.pins.list();records[0]['source_message_id']=identifier()
        with patch.object(self.h.pins,'list',return_value=records):self.h.context_turns([t])
        self.assertIn('source_missing',self.h.projection_diagnostics['source_mapping_failure_reasons'])
    def test_invalid_pin_source_session(self):
        _,t,p=self.sample();other=SessionHistory(self.store);mid,_=stored(other,'撤销规则。');records=self.h.pins.list();records[0]['source_message_id']=mid
        with patch.object(self.h.pins,'list',return_value=records):self.h.context_turns([t])
        self.assertIn('source_session_mismatch',self.h.projection_diagnostics['source_mapping_failure_reasons'])
    def test_assistant_source_rejected(self):
        _,t,p=self.sample();records=self.h.pins.list();records[0]['source_message_id']=self.h.messages()[-1]['id']
        with patch.object(self.h.pins,'list',return_value=records):self.h.context_turns([t])
        self.assertIn('source_role_mismatch',self.h.projection_diagnostics['source_mapping_failure_reasons'])
    def test_stale_span_fails_closed(self):
        _,t,p=self.sample();records=self.h.pins.list();records[0]['source_span']=[1,3]
        with patch.object(self.h.pins,'list',return_value=records):self.assertEqual(self.h.context_turns([t]),[])
        self.assertIn('source_span_mismatch',self.h.projection_diagnostics['source_mapping_failure_reasons'])
    def test_multiple_pins_one_source(self):
        mid,t=stored(self.h,'甲规则。乙规则。独立事实。');a=pin(self.h,mid,'甲规则。');b=pin(self.h,mid,'乙规则。');revoke(self.h,a);revoke(self.h,b);v=self.h.context_turns([t]);self.assertIn('独立事实。',str(v));self.assertEqual(self.h.projection_diagnostics['redacted_source_spans'],1)
    def test_active_other_pin_preserved(self):
        mid,t=stored(self.h,'甲规则。乙规则。独立事实。');a=pin(self.h,mid,'甲规则。');pin(self.h,mid,'乙规则。');revoke(self.h,a);self.assertIn('乙规则。',str(self.h.context_turns([t])))
    def test_active_overlap_not_removed(self):
        mid,t=stored(self.h,'甲规则。独立事实。');a=pin(self.h,mid,'甲规则。');pin(self.h,mid,'甲规则。');revoke(self.h,a);self.assertIn('甲规则。',str(self.h.context_turns([t])))
    def test_restart_retains_id_not_text_guessing(self):
        _,t,_=self.sample();sid=self.h.sid;self.store.close();self.store=open_store(self.cfg,'cli');self.addCleanup(self.store.close);h=SessionHistory(self.store,sid);v=h.context_turns(h.model_turns());self.assertIn('保留事实。',str(v));self.assertNotIn('撤销规则。',str(v))
    def test_legacy_ids_missing_fallback(self):
        _,t,_=self.sample();self.assertEqual(self.h.context_turns([list(t)]),[]);self.assertEqual(self.h.projection_diagnostics['source_mapping_failures'],1)
    def test_modified_source_cannot_shift_span(self):
        _,t,_=self.sample();t[0]['content']='prefix'+t[0]['content'];self.assertEqual(self.h.context_turns([t]),[])
    def test_truncated_source_safe_fallback(self):
        mid,t=stored(self.h,'撤销规则。'+'长'*12000);p=pin(self.h,mid,'撤销规则。');revoke(self.h,p);self.assertEqual(self.h.context_turns([t]),[]);self.assertIn('source_truncated',self.h.projection_diagnostics['source_mapping_failure_reasons'])
    def test_redacted_source_safe_fallback(self):
        mid,t=stored(self.h,'撤销规则。 API_KEY=synthetic-secret-value');p=pin(self.h,mid,'撤销规则。');revoke(self.h,p);self.assertEqual(self.h.context_turns([t]),[]);self.assertIn('source_redacted',self.h.projection_diagnostics['source_mapping_failure_reasons'])
    def test_sqlite_events_and_messages_unchanged(self):
        _,t,_=self.sample();before=[dict(x) for x in self.store.query('select * from events')];msgs=self.h.messages();self.h.context_turns([t]);self.assertEqual(before,[dict(x) for x in self.store.query('select * from events')]);self.assertEqual(msgs,self.h.messages())
    def test_diagnostics_no_text(self):
        _,t,_=self.sample();self.h.context_turns([t]);s=json.dumps(self.h.projection_diagnostics,ensure_ascii=False);self.assertNotIn('撤销规则',s);self.assertNotIn('保留事实',s);self.assertTrue(self.h.projection_diagnostics['history_projection_incomplete'])
    def test_metadata_does_not_escape_api_dict(self):
        _,t,_=self.sample();session=Session();session.add_turn(t);v=self.h.context_turns(session.export_turns());self.assertEqual(set(v[0][0]),{'role','content'});self.assertTrue(v[0][0]['content'].startswith(SOURCE_LABEL))
    def test_public_l02_all_five_retained_after_replace_and_revoke(self):
        with tempfile.TemporaryDirectory() as d:
            cfg,s,h,turns,new=source_fixture(d)
            try:
                before=h.messages();v=h.context_turns(turns);self.assertTrue(all(x in str(v) for x in UNITS));self.assertFalse(any(x in str(baseline_projection(turns,[OLD])) for x in UNITS[:3]));revoke(h,new);v=h.context_turns(turns);self.assertTrue(all(x in str(v) for x in UNITS));self.assertFalse(any(x in str(baseline_projection(turns,[OLD,NEW])) for x in UNITS));self.assertEqual(before,h.messages());self.assertNotIn(OLD,str(v));self.assertNotIn(NEW,str(v))
            finally:s.close()

def check_source_aware_projection():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceChecks))
    if not r.wasSuccessful():raise AssertionError('source-aware projection failed')
if __name__=='__main__':check_source_aware_projection()
