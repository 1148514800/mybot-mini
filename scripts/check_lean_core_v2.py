"""Offline product retirement and migration contracts, using synthetic inputs only."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mybot.config import GatewayConfig, ConfigError, config_from_document, load_config
from mybot.agent.token_counter import TokenCounter, TokenBudgetError
from mybot.tools import build_default_tool_registry
from scripts.migrate_config_v2 import migrate as migrate_config
from scripts.migrate_legacy_session import migrate as migrate_session, MigrationError


def document():
    return {'llm': {'provider':'offline', 'providers':{'offline':{
        'api_key':'synthetic-key', 'base_url':'https://offline.invalid/v1', 'model':'offline'}}}}


class CoreV2Checks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.workspace = self.root / 'workspace'; self.workspace.mkdir()
        self.private = self.root / 'private'; self.private.mkdir(mode=0o700)
        self.source = self.root / 'legacy.json'; self.destination = self.private / 'events.sqlite3'
        self.config_path = self.root / 'config.json'

    def source_turns(self, turns):
        self.source.write_text(json.dumps({'version':1, 'turns':turns}))

    def migration(self, **kw):
        return migrate_session(self.source, self.destination, workspace=self.workspace, **kw)

    def test_fixed_retired_denial_even_malformed_arguments(self):
        registry = build_default_tool_registry(self.workspace)
        self.assertNotIn('write_file', [d['function']['name'] for d in registry.get_definitions()])
        for arguments in ({}, {'path':'x', 'content':'secret'}):
            result = asyncio.run(registry.execute('write_file', arguments))
            self.assertEqual(result.error, 'TOOL_RETIRED_WRITE_FILE')
            self.assertIs(result.metadata['executed'], False)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_removed_constructor_fields(self):
        for kwargs in ({'session_persist':False}, {'session_path':'unused'}, {'coding_file_access':'legacy_confirm'}):
            with self.assertRaises(TypeError): GatewayConfig(**kwargs)
        with self.assertRaises(ValueError): GatewayConfig(session_backend='legacy_json')

    def test_retired_document_errors_are_sanitized(self):
        for section, value, error in (
            ('coding', {'file_access':'legacy_confirm'}, 'MIGRATION_REQUIRED_CODING_FILE_ACCESS'),
            ('session', {'path':'synthetic-secret-key'}, 'MIGRATION_REQUIRED_SESSION_JSON'),
            ('context', {'token_budget':{'mode':'legacy_chars'}}, 'MIGRATION_REQUIRED_TOKEN_BUDGET')):
            config = document(); config[section] = value
            with self.assertRaises(ConfigError) as caught: config_from_document(config)
            self.assertEqual(str(caught.exception), error)

    def test_estimate_is_default_even_when_context_disabled(self):
        config = GatewayConfig(context_enabled=False, context_token_budget={'input_limit':256})
        self.assertEqual(config.context_token_budget['mode'], 'estimate')
        with self.assertRaises(TokenBudgetError): TokenCounter.enforce(config, TokenCounter.request(config, [{'role':'user','content':'a'*256}], []))
        for mode in ('legacy_chars',):
            with self.assertRaises(ValueError): GatewayConfig(context_token_budget={'mode':mode})
        with self.assertRaisesRegex(TokenBudgetError, 'unverified'):
            TokenCounter.enforce(GatewayConfig(context_token_budget={'mode':'strict'}), {'max_tokens':1})

    def test_config_preview_apply_backup_and_budget(self):
        config = document(); config.update(coding={'file_access':'legacy_confirm'}, session={'persist':False,'path':'unused'}, context={'token_budget':{'mode':'legacy_chars','input_limit':3210}})
        self.config_path.write_text(json.dumps(config)); original = self.config_path.read_bytes()
        with self.assertRaisesRegex(ConfigError, 'CONFIRMATION_REQUIRED'): migrate_config(self.config_path)
        preview = migrate_config(self.config_path, confirm_token_estimate=True)
        self.assertFalse(preview['applied']); self.assertEqual(self.config_path.read_bytes(), original)
        migrate_config(self.config_path, apply=True, confirm_token_estimate=True)
        new = load_config(self.config_path)
        self.assertFalse(new.coding_enabled); self.assertEqual(new.coding_patch_mode, 'off')
        self.assertEqual(new.storage_backend, 'memory'); self.assertEqual(new.context_token_budget['input_limit'], 3210)
        backup = self.config_path.with_name('config.json.v1-backup')
        self.assertEqual(backup.read_bytes(), original); self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_active_session_config_cannot_silently_change_backend(self):
        config = document(); config['session'] = {'persist':True, 'path':'old.json'}
        self.config_path.write_text(json.dumps(config)); original = self.config_path.read_bytes()
        with self.assertRaisesRegex(ConfigError, 'DATA_MIGRATION_REQUIRED'): migrate_config(self.config_path, apply=True)
        self.assertEqual(self.config_path.read_bytes(), original); self.assertFalse(self.config_path.with_name('config.json.v1-backup').exists())

    def test_lossless_session_preview_apply_and_existing_destination(self):
        turns = [[{'role':'user','content':'问题😀'}, {'role':'assistant','content':'回答'}], [{'role':'user','content':''},{'role':'assistant','content':'two'}]]
        self.source_turns(turns); original = self.source.read_bytes()
        result = self.migration(); self.assertTrue(result['lossless']); self.assertFalse(self.destination.exists())
        result = self.migration(apply=True); self.assertEqual(result['destination_messages'], 4)
        before = self.destination.read_bytes()
        with self.assertRaisesRegex(MigrationError, 'DESTINATION_EXISTS'): self.migration(apply=True)
        self.assertEqual(self.destination.read_bytes(), before); self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.destination.stat().st_mode & 0o777, 0o600)

    def test_tool_history_requires_lossy_confirmation_and_backup(self):
        self.source_turns([[{'role':'user','content':'question'}, {'role':'assistant','content':'thinking', 'tool_calls':[{'id':'1','type':'function','function':{'name':'read_file','arguments':'{}'}}]}, {'role':'tool','tool_call_id':'1','content':'old output'}, {'role':'assistant','content':'answer'}]])
        original = self.source.read_bytes()
        with self.assertRaisesRegex(MigrationError, 'UNSUPPORTED_TOOL_HISTORY'): self.migration()
        with self.assertRaisesRegex(MigrationError, 'LOSSY_CONFIRMATION_REQUIRED'): self.migration(flatten_tool_history=True)
        result = self.migration(apply=True, flatten_tool_history=True, confirm_lossy=True)
        self.assertFalse(result['lossless']); self.assertEqual(result['omitted_tool_interactions'], 1)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.source.with_name('legacy.json.migration-backup').read_bytes(), original)

    def test_incomplete_and_unrepresentable_history_preserved(self):
        for turns, error in (([[{'role':'user','content':'unfinished'}]], 'INVALID_LEGACY_SESSION'),
                             ([[{'role':'user','content':'password=secret'}, {'role':'assistant','content':'ok'}]], 'TEXT_NOT_LOSSLESSLY_REPRESENTABLE')):
            self.source_turns(turns); original = self.source.read_bytes()
            with self.assertRaisesRegex(MigrationError, error): self.migration(apply=True)
            self.assertEqual(self.source.read_bytes(), original); self.assertFalse(self.destination.exists())

    def test_disabled_extensions_do_not_import_runtime_components(self):
        code = """
import importlib.abc, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
class Boundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('mybot.mcp_client.manager', 'mybot.mcp_client.transport', 'mybot.skills.registry'):
            raise AssertionError('disabled component initialized: ' + fullname)
sys.meta_path.insert(0, Boundary())
from mybot.config import GatewayConfig
from mybot.agent import AgentLoop, ContextBuilder
from mybot.tools import build_default_tool_registry
with tempfile.TemporaryDirectory() as folder:
    config = GatewayConfig(workspace=Path(folder))
    agent = AgentLoop(SimpleNamespace(), config, build_default_tool_registry(config.workspace), ContextBuilder(config.workspace))
    assert agent.skills is None and agent.discovery is None
    agent.close_history()
"""
        subprocess.run([sys.executable, '-c', code], check=True)

    def test_check_uses_the_supplied_document_and_no_client(self):
        from unittest.mock import patch
        from mybot.web.launch import prepare_launch
        subprocess.run(['git', 'init', '-q', str(self.workspace)], check=True)
        doc = document(); doc['workspace'] = {'path':str(self.workspace)}
        doc['session'] = {'max_turns':9}; doc['context'] = {'token_budget':{'input_limit':12345}}
        self.config_path.write_text(json.dumps(doc))
        with patch('mybot.config.build_client', side_effect=AssertionError('client constructed')):
            config, _, report = prepare_launch(config_path=self.config_path)
        direct = load_config(self.config_path)
        self.assertEqual(config, direct); self.assertEqual(config.session_max_turns, 9)
        self.assertEqual(config.context_token_budget['input_limit'], 12345)
        self.assertIs(report['provider_connection_tested'], False)
        doc['session']['persist'] = False; self.config_path.write_text(json.dumps(doc))
        for load in (lambda: prepare_launch(config_path=self.config_path), lambda: load_config(self.config_path)):
            with self.assertRaisesRegex(ConfigError, 'MIGRATION_REQUIRED_SESSION_JSON'): load()

    def test_failed_publish_and_invalid_config_do_not_replace_data(self):
        from unittest.mock import patch
        self.source_turns([[{'role':'user','content':'hi'}, {'role':'assistant','content':'hello'}]])
        original = self.source.read_bytes()
        with patch('scripts.migrate_legacy_session.os.link', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError): self.migration(apply=True)
        self.assertFalse(self.destination.exists()); self.assertEqual(self.source.read_bytes(), original)
        doc = document(); doc['coding'] = {'file_access':'read_only', 'command':{'mode':'unsafe'}}
        self.config_path.write_text(json.dumps(doc)); before = self.config_path.read_bytes()
        with self.assertRaises(ConfigError): migrate_config(self.config_path, apply=True)
        self.assertEqual(self.config_path.read_bytes(), before)
        self.assertFalse(self.config_path.with_name('config.json.v1-backup').exists())

    def test_import_does_not_read_configuration(self):
        code = "from pathlib import Path\nfrom unittest.mock import patch\nwith patch.object(Path, 'read_text', side_effect=AssertionError('implicit read')):\n import mybot.config\n"
        subprocess.run([sys.executable, '-c', code], check=True)


if __name__ == '__main__': unittest.main()
