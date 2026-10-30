"""v2 replacement contracts for the retired Phase 05 JSON runtime backend.

JSON is read only by the explicit migration command. Runtime persistence is SQLite.
"""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mybot.config import GatewayConfig, ConfigError, config_from_document
from mybot.storage.history import open_store, SessionHistory
from mybot.storage.session_store import validate_turns
from scripts.check_lean_core_v2 import CoreV2Checks, document
from scripts.migrate_legacy_session import MigrationError


class PersistenceChecks(unittest.TestCase):
    # Share synthetic setup, while running new migration tests once in their own suite.
    setUp = CoreV2Checks.setUp
    source_turns = CoreV2Checks.source_turns
    migration = CoreV2Checks.migration
    def seed(self):
        turns = [[{'role':'user','content':'question'}, {'role':'assistant','content':'answer'}]]
        self.source_turns(turns)
        return turns

    def open_history(self):
        cfg = GatewayConfig(workspace=self.workspace, session_backend='event_sqlite', session_event_path=self.destination)
        store = open_store(cfg, 'cli'); self.addCleanup(store.close)
        return SessionHistory(store, store.sessions(1)[0]['id'])

    def test_save_and_restart(self):
        turns = self.seed(); self.migration(apply=True)
        self.assertEqual([dict(r) for r in self.open_history().store.query('SELECT role,content FROM messages ORDER BY sequence')], turns[0])
        self.assertIn('不恢复授权', self.open_history().model_turns()[0][-1]['content'])

    def test_multiple_tool_results_restore(self):
        CoreV2Checks.test_tool_history_requires_lossy_confirmation_and_backup(self)
        self.assertEqual(self.open_history().store.query('SELECT * FROM tools'), [])

    def test_restore_and_save_use_current_window(self):
        self.source_turns([[{'role':'user','content':str(n)}, {'role':'assistant','content':str(n)}] for n in range(8)])
        self.migration(apply=True); history = self.open_history()
        self.assertEqual(len(history.model_turns(3)), 3)
        self.assertEqual(len(history.store.query('SELECT * FROM messages')), 16)

    def test_clear_disk_memory_and_plan(self):
        self.seed(); self.migration(apply=True); history = self.open_history(); history.clear_context()
        self.assertEqual(history.model_turns(), [])
        self.assertEqual(len(history.store.query('SELECT * FROM messages')), 2)

    def test_timeout_and_exception_do_not_write(self):
        self.seed(); original = self.source.read_bytes()
        with patch('scripts.migrate_legacy_session.open_store', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError): self.migration(apply=True)
        self.assertEqual(self.source.read_bytes(), original); self.assertFalse(self.destination.exists())

    def test_react_limit_persists_complete_pairs(self):
        self.seed(); self.migration(apply=True); validate_turns(self.open_history().model_turns())
        self.assertEqual(self.open_history().status()['status'], 'completed')

    def test_atomic_replace_failure_preserves_file_and_memory(self):
        self.seed(); original = self.source.read_bytes()
        with patch('scripts.migrate_legacy_session.os.link', side_effect=OSError):
            with self.assertRaises(OSError): self.migration(apply=True)
        self.assertEqual(self.source.read_bytes(), original); self.assertFalse(self.destination.exists())

    def test_fsync_failure_preserves_file(self):
        self.seed(); original = self.source.read_bytes()
        with patch('scripts.migrate_legacy_session.os.fsync', side_effect=OSError):
            with self.assertRaises(Exception): self.migration(apply=True)
        self.assertEqual(self.source.read_bytes(), original); self.assertFalse(self.destination.exists())

    def test_clear_failure_keeps_disk_and_memory(self):
        self.seed(); self.migration(apply=True); history = self.open_history(); before = history.model_turns()
        with patch.object(history.store, 'append', side_effect=OSError):
            with self.assertRaises(OSError): history.clear_context()
        self.assertEqual(history.model_turns(), before)

    def test_corrupt_and_unsupported_documents_preserved(self):
        for text in ('{', '{"version":2,"turns":[]}', '{"version":1,"turns":[],"extra":true}', '{"version":1,"version":1,"turns":[]}'):
            self.source.write_text(text)
            with self.assertRaises(MigrationError): self.migration(apply=True)
            self.assertEqual(self.source.read_text(), text); self.assertFalse(self.destination.exists())

    def test_bad_message_pairs_and_roles_rejected(self):
        for turns in ([[{'role':'user','content':'x'}]], [[{'role':'system','content':'x'},{'role':'assistant','content':'x'}]], [[{'role':'user','content':'x'},{'role':'tool','tool_call_id':'orphan','content':'x'},{'role':'assistant','content':'x'}]]):
            with self.assertRaises(ValueError): validate_turns(turns)
            self.source_turns(turns)
            with self.assertRaises(MigrationError): self.migration(apply=True)
            self.assertFalse(self.destination.exists())

    def test_disabled_persistence_ignores_existing_corrupt_file(self):
        self.source.write_text('{')
        cfg = GatewayConfig(workspace=self.workspace)
        store = open_store(cfg, 'cli'); self.addCleanup(store.close)
        self.assertEqual(store.sessions(), []); self.assertEqual(self.source.read_text(), '{')

    def test_planning_history_does_not_resume_execution(self):
        self.seed(); self.migration(apply=True); history = self.open_history()
        self.assertEqual(history.store.query('SELECT * FROM tools'), [])
        self.assertEqual(history.store.query('SELECT * FROM pins'), [])
        self.assertNotIn('verified', json.dumps(history.status()))

    def test_storage_cannot_be_accessed_through_workspace_tools(self):
        self.seed(); self.destination = self.workspace / 'history.sqlite3'
        with self.assertRaisesRegex(MigrationError, 'STORAGE_INSIDE_WORKSPACE'): self.migration(apply=True)
        self.assertFalse(self.destination.exists())

    def test_config_types_and_project_relative_path(self):
        for session in ({'persist':False}, {'path':'old.json'}, {'backend':'legacy_json'}):
            cfg = document(); cfg['session'] = session
            with self.assertRaisesRegex(ConfigError, 'MIGRATION_REQUIRED_SESSION_JSON'): config_from_document(cfg)
        for value in (None, 'legacy_json', True):
            with self.assertRaises(ValueError): GatewayConfig(session_backend=value)

    def test_deepcopy_roundtrip_and_permissions(self):
        turns = self.seed(); self.migration(apply=True); history = self.open_history()
        view = history.model_turns(); view[0][0]['content'] = 'mutated'
        self.assertEqual([dict(r) for r in history.store.query('SELECT role,content FROM messages ORDER BY sequence')], turns[0])
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o600)


def check_persistence():
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PersistenceChecks))
    if not result.wasSuccessful(): raise AssertionError('v2 persistence checks failed')


if __name__ == '__main__': check_persistence()
