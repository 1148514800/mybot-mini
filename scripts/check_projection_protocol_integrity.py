"""Atomic tool protocol fallback and unchanged authority, entirely synthetic."""
from copy import deepcopy
import tempfile,unittest,json
from mybot.agent.session import HistoryTurn
from mybot.storage.history import SessionHistory,open_store
from mybot.storage.session_store import validate_turns
from mybot.storage.context_projection import MASK
from scripts.eventstore_fixtures import configuration
from scripts.source_projection_fixtures import stored,pin,revoke
from scripts.check_session import assert_pairs

class ProtocolChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.cfg=configuration(__import__('pathlib').Path(self.tmp.name).resolve());self.s=open_store(self.cfg,'cli');self.addCleanup(self.s.close);self.h=SessionHistory(self.s)
        mid,self.source=stored(self.h,'旧要求。保留事实。');p=pin(self.h,mid,'旧要求。');revoke(self.h,p)
    def tool_turn(self,*,affected=False,echo=False):
        if affected:t=deepcopy(self.source)
        else:_,t=stored(self.h,'独立工具问题。')
        t[1:]=[{'role':'assistant','content':None,'tool_calls':[{'id':'call-a','type':'function','function':{'name':'list_files','arguments':'{}'}},{'id':'call-b','type':'function','function':{'name':'read_file','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'call-a','content':'原始结果A'}, {'role':'tool','tool_call_id':'call-b','content':'旧要求。' if echo else '原始结果B'}, {'role':'assistant','content':'工具历史，不是当前执行。'}];validate_turns([t]);return t
    def test_affected_protocol_group_omitted_atomically(self):
        t=self.tool_turn(affected=True);self.assertEqual(self.h.context_turns([t]),[]);self.assertEqual(self.h.projection_diagnostics['omitted_protocol_turns'],1);self.assertEqual(self.h.projection_diagnostics['omitted_user_messages'],1)
    def test_unaffected_call_ids_pairs_and_order_preserved(self):
        t=self.tool_turn();v=self.h.context_turns([t]);validate_turns(v);assert_pairs(self,v[0]);self.assertEqual(v[0][1:4],t[1:4])
    def test_tool_results_not_fabricated(self):
        t=self.tool_turn();before=deepcopy(t);self.h.context_turns([t]);self.assertEqual(t,before);self.assertEqual([m['content'] for m in t if m['role']=='tool'],['原始结果A','原始结果B'])
    def test_echo_in_tool_result_omits_group(self):
        t=self.tool_turn(echo=True);self.assertEqual(self.h.context_turns([t]),[]);self.assertEqual(self.h.projection_diagnostics['omitted_protocol_turns'],1)
    def test_unknown_protocol_identity_conservative(self):
        t=list(self.tool_turn());self.assertEqual(self.h.context_turns([t]),[]);self.assertGreater(self.h.projection_diagnostics['source_mapping_failures'],0)
    def test_other_user_identical_rule_does_not_invalidate_new_source(self):
        mid,t=stored(self.h,'旧要求。保留新事实。');self.assertIn('旧要求。',self.h.context_turns([t])[0][0]['content']);self.assertEqual(self.h.projection_diagnostics['redacted_source_spans'],0)
    def test_restored_text_does_not_restore_tool_evidence(self):
        t=self.tool_turn();sid=self.h.sid;h=SessionHistory(self.s,sid);v=h.context_turns(h.model_turns());self.assertFalse(any('tool_calls' in m or m['role']=='tool' for turn in v for m in turn));self.assertFalse(h.status()['execution_evidence_restored'])
    def test_projection_does_not_emit_events_or_authority(self):
        before=[dict(x) for x in self.s.query('select * from events')];self.h.context_turns([self.tool_turn(affected=True)]);self.assertEqual(before,[dict(x) for x in self.s.query('select * from events')]);self.assertEqual(self.s.query('select * from tools'),[])
    def test_api_message_fields_still_standard(self):
        v=self.h.context_turns([self.source,self.tool_turn()]);validate_turns(v);self.assertIn(MASK,v[0][0]['content']);self.assertTrue(all(set(m)<=({'role','content','tool_calls'} if m['role']!='tool' else {'role','content','tool_call_id'}) for t in v for m in t))

def check_projection_protocol_integrity():
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProtocolChecks))
    if not r.wasSuccessful():raise AssertionError('projection protocol failed')
if __name__=='__main__':check_projection_protocol_integrity()
