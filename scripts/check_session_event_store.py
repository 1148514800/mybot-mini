"""Atomic append, private paths, versioning, quotas, deletion and multiprocess writes."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
from mybot.storage.event_schema import Event,StoreError,identifier
from mybot.storage.event_store import SessionEventStore
from mybot.storage.history import SessionHistory


class EventStoreChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.workspace=self.root/'workspace';self.workspace.mkdir();self.path=self.root/'private/events.db'
        self.store=SessionEventStore(self.path,self.workspace);self.addCleanup(self.store.close)
        self.sid=self.store.create_session()
    def event(self,**changes):return Event.create(self.sid,'context.cleared',{}) if not changes else replace(Event.create(self.sid,'context.cleared',{}),**changes)
    def test_sequence_and_deterministic_reads(self):
        for _ in range(10):self.store.append(self.event())
        rows=self.store.events(self.sid);self.assertEqual([r['sequence'] for r in rows],list(range(1,12)))
        self.assertEqual(rows,self.store.events(self.sid));self.assertEqual(len(self.store.events(self.sid,after=5,limit=2)),2)
    def test_idempotent_same_event(self):
        event=self.event();seq=self.store.append(event);self.assertEqual(self.store.append(event),seq)
        self.assertEqual(len(self.store.events(self.sid)),2)
    def test_id_conflict_refuses_overwrite(self):
        event=self.event();self.store.append(event)
        with self.assertRaises(StoreError):self.store.append(replace(event,timestamp=event.timestamp+1))
        self.assertEqual(len(self.store.events(self.sid)),2)
    def test_batch_failure_rolls_back_all(self):
        good=self.event();bad=Event.create(self.sid,'pin.revoked',{'pin_id':identifier(),'expected_revision':1},source='user_confirmed')
        with self.assertRaises(StoreError):self.store.append_many([good,bad])
        self.assertEqual(len(self.store.events(self.sid)),1)
    def test_concurrent_processes_no_lost_sequence(self):
        code="from pathlib import Path;from mybot.storage.event_store import SessionEventStore;from mybot.storage.event_schema import Event;import sys;s=SessionEventStore(Path(sys.argv[1]),Path(sys.argv[2]));[s.append(Event.create(sys.argv[3],'context.cleared',{})) for _ in range(20)];s.close()"
        children=[subprocess.Popen([sys.executable,'-c',code,str(self.path),str(self.workspace),self.sid],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(3)]
        for child in children:
            out,err=child.communicate(timeout=20);self.assertEqual(child.returncode,0,err.decode())
        self.assertEqual([r['sequence'] for r in self.store.events(self.sid)],list(range(1,62)))
    def test_corrupt_database_preserved(self):
        self.store.close();self.path.write_bytes(b'corrupt data');before=self.path.read_bytes()
        with self.assertRaises(StoreError):SessionEventStore(self.path,self.workspace)
        self.assertEqual(self.path.read_bytes(),before)
    def test_wrong_version_preserved(self):
        with sqlite3.connect(self.path) as db:db.execute('PRAGMA user_version=9')
        before=self.path.read_bytes()
        with self.assertRaises(StoreError):SessionEventStore(self.path,self.workspace)
        self.assertEqual(self.path.read_bytes(),before)
    def test_event_logical_corruption_refused(self):
        with sqlite3.connect(self.path) as db:db.execute("UPDATE events SET payload='{}'")
        with self.assertRaises(StoreError):SessionEventStore(self.path,self.workspace)
    def test_foreign_sqlite_not_overwritten(self):
        self.store.close();self.path.unlink()
        with sqlite3.connect(self.path) as db:db.execute('CREATE TABLE private_data(value)')
        self.path.chmod(0o600);before=self.path.read_bytes()
        with self.assertRaises(StoreError):SessionEventStore(self.path,self.workspace)
        self.assertEqual(self.path.read_bytes(),before)
    def test_process_death_inside_transaction_recovers_hot_journal(self):
        h=SessionHistory(self.store,self.sid);h.start('committed before crash');h.finish('committed reply')
        self.store.close()
        code="import sqlite3,sys,os;d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA cache_size=5');d.execute('BEGIN IMMEDIATE');d.execute('UPDATE messages SET content=?',('x'*2000000,));os._exit(17)"
        child=subprocess.run([sys.executable,'-c',code,str(self.path)],capture_output=True,timeout=10)
        self.assertEqual(child.returncode,17);self.assertTrue(self.path.with_name(self.path.name+'-journal').exists())
        self.store=SessionEventStore(self.path,self.workspace);self.addCleanup(self.store.close)
        self.assertEqual([m['content'] for m in SessionHistory(self.store,self.sid).messages()],['committed before crash','committed reply'])
        self.assertEqual(len(self.store.events(self.sid)),5)
        self.assertFalse(self.path.with_name(self.path.name+'-journal').exists())
    def test_foreign_hot_journal_is_preserved_without_recovery(self):
        self.store.close();self.path.unlink()
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE messages(content)');db.execute("INSERT INTO messages VALUES('foreign original')")
        self.path.chmod(0o600)
        code="import sqlite3,sys,os;d=sqlite3.connect(sys.argv[1]);d.execute('PRAGMA cache_size=5');d.execute('BEGIN IMMEDIATE');d.execute('UPDATE messages SET content=?',('x'*2000000,));os._exit(17)"
        child=subprocess.run([sys.executable,'-c',code,str(self.path)],capture_output=True,timeout=10)
        self.assertEqual(child.returncode,17)
        journal=self.path.with_name(self.path.name+'-journal');before=self.path.read_bytes();before_journal=journal.read_bytes()
        with self.assertRaises(StoreError):SessionEventStore(self.path,self.workspace)
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(journal.read_bytes(),before_journal)
    def test_private_directory_and_file_modes(self):
        self.assertEqual(self.path.stat().st_mode&0o777,0o600);self.assertEqual(self.path.parent.stat().st_mode&0o777,0o700)
        self.path.chmod(0o644)
        with self.assertRaises(StoreError):self.store.append(self.event())
    def test_unsafe_directory_refused(self):
        self.path.parent.chmod(0o755)
        with self.assertRaises(StoreError):SessionEventStore(self.path,self.workspace)
    def test_symlink_parent_and_file_refused(self):
        alias=self.root/'alias';alias.symlink_to(self.path.parent,target_is_directory=True)
        with self.assertRaises(StoreError):SessionEventStore(alias/'events.db',self.workspace)
        link=self.path.parent/'link';link.symlink_to(self.path)
        with self.assertRaises(StoreError):SessionEventStore(link,self.workspace)
    def test_hardlink_and_workspace_refused(self):
        os.link(self.path,self.path.parent/'hard')
        with self.assertRaises(StoreError):self.store.append(self.event())
        with self.assertRaises(StoreError):SessionEventStore(self.workspace/'events.db',self.workspace)
    def test_ownership_not_assumed(self):
        real=Path.lstat
        def metadata(path,*a,**kw):
            result=real(path,*a,**kw)
            if path==self.path:
                from types import SimpleNamespace
                return SimpleNamespace(st_dev=result.st_dev,st_ino=result.st_ino,st_uid=os.geteuid()+1,st_mode=result.st_mode,st_nlink=result.st_nlink,st_size=result.st_size)
            return result
        with patch.object(Path,'lstat',metadata):
            with self.assertRaises(StoreError):self.store.append(self.event())
    def test_payload_and_event_count_limits(self):
        self.store.limits['max_events']=1
        with self.assertRaises(StoreError):self.store.append(self.event())
        self.store.limits['max_events']=10;self.store.limits['max_payload_bytes']=1024
        event=Event.create(self.sid,'user.message',{'turn_id':identifier(),'content':'x'*2000,'truncated':False},source='user',privacy_class='chat')
        with self.assertRaises(StoreError):self.store.append(event)
        self.assertEqual(len(self.store.events(self.sid)),1)
    def test_database_size_limit_rolls_back(self):
        self.store.limits['max_bytes']=1024*1024
        completed=0
        try:
            for _ in range(100):
                h=SessionHistory(self.store);h.start('x'*12000);h.finish('y'*12000);completed+=1
        except StoreError:pass
        self.assertLess(completed,100);self.assertLessEqual(self.path.stat().st_size,1024*1024)
    def test_unknown_payload_fields_and_sources_refused(self):
        for event in (replace(self.event(),schema_version=2),replace(self.event(),payload={'approval_nonce':'bad'}),replace(self.event(),source='model')):
            with self.assertRaises(StoreError):self.store.append(event)
    def test_private_text_and_receipt_refused(self):
        from mybot.storage.event_privacy import safe_text
        for text in ('api_key=private-credential-value','receipt='+'a'*64,'/Users/private/project/secret'):
            event=Event.create(self.sid,'user.message',dict(turn_id=identifier(),content=text,truncated=False),source='user',privacy_class='chat')
            with self.assertRaises(StoreError):self.store.append(event)
            self.assertNotEqual(safe_text(text)[0],text)
    def test_delete_is_actual_cascade_not_clear_event(self):
        h=SessionHistory(self.store,self.sid);h.start('UNIQUE_DELETE_SENTINEL_628463');h.finish('reply')
        self.store.delete(self.sid)
        for table in ('events','messages','turns','pins'):
            self.assertEqual(self.store.query('SELECT count(*) AS n FROM '+table)[0]['n'],0)
        self.assertNotIn(b'UNIQUE_DELETE_SENTINEL_628463',self.path.read_bytes())
        with self.assertRaises(StoreError):self.store.events(self.sid)
    def test_clear_context_keeps_facts(self):
        h=SessionHistory(self.store,self.sid);h.start('old');h.finish('ok');h.clear_context()
        self.assertEqual(len(h.messages()),2);self.assertEqual(h.model_turns(),[])


def check_session_event_store():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EventStoreChecks))
    if not result.wasSuccessful():raise AssertionError('event store checks failed')
if __name__=='__main__':check_session_event_store()
