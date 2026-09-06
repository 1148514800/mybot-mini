from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest

from mybot.guardrails import PendingApproval, RiskLevel
from mybot.storage.checkpoints.sanitizer import sanitize_messages
from mybot.storage.checkpoints.serialization import (
    approval_from_checkpoint,
    serialize_approval,
)
from mybot.tracing import REDACTED


class CheckpointModuleTests(unittest.TestCase):
    def test_cold_imports_and_compatibility(self):
        # A fresh interpreter catches cycles hidden by the test runner's imports.
        for first in (
            'mybot.storage.checkpoint',
            'mybot.storage.checkpoints.serialization',
            'mybot.agent.checkpoint_recovery',
        ):
            with self.subTest(first=first):
                result = subprocess.run(
                    [sys.executable, '-c', f'''
import importlib
importlib.import_module({first!r})
from mybot.storage.checkpoint import ActiveTaskCheckpointStore as legacy
from mybot.storage.checkpoints import ActiveTaskCheckpointStore as public
from mybot.storage.checkpoints.models import RecoveredActiveCheckpoint
from mybot.storage.checkpoints.serialization import approval_from_checkpoint
from mybot.agent.checkpoint_recovery import approval_from_checkpoint as old
assert legacy is public
assert old is approval_from_checkpoint
assert RecoveredActiveCheckpoint.__module__ == 'mybot.storage.checkpoints.models'
'''],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_message_sanitization_preserves_live_input(self):
        secret = 'unique-private-input'
        messages = [
            {'role': 'user', 'content': secret},
            {'role': 'assistant', 'tool_calls': [{
                'id': 'call-1', 'type': 'function',
                'function': {'name': 'browser_type', 'arguments': json.dumps({
                    'target': 'e1', 'text': secret,
                })},
            }]},
            {'role': 'tool', 'tool_call_id': 'call-1', 'content': secret},
        ]
        original = copy.deepcopy(messages)
        safe = sanitize_messages(messages)
        self.assertEqual(messages, original)
        self.assertNotIn(secret, json.dumps(safe))
        self.assertEqual(safe[0]['content'], REDACTED)
        self.assertIn('read fresh browser state', safe[2]['content'])

    def test_approval_adapter_preserves_binding_and_disables_sensitive_resume(self):
        pending = PendingApproval(
            approval_id='approval-1', session_key='cli:a', task_id='task-1',
            requester_sender_id='sender-1', tool_name='browser_type',
            arguments={'target': 'e1', 'text': 'unique-private-input'},
            risk_level=RiskLevel.SENSITIVE, reason='confirmation required',
            created_at='2026-09-05T00:00:00+00:00',
            expires_at='2026-09-06T00:00:00+00:00',
            browser_initialized=True,
            browser_state={'latest_snapshot': 'live', 'browser_initialized': True},
        )
        original = copy.deepcopy(pending)
        payload = serialize_approval(pending)
        recovered = approval_from_checkpoint(payload)
        self.assertEqual(pending, original)
        self.assertNotIn('unique-private-input', json.dumps(payload))
        self.assertFalse(recovered.resumable)
        self.assertFalse(recovered.browser_initialized)
        self.assertFalse(recovered.browser_state['browser_initialized'])
        self.assertEqual(recovered.requester_sender_id, pending.requester_sender_id)
        self.assertEqual(recovered.task_id, pending.task_id)
        self.assertEqual(recovered.expires_at, pending.expires_at)
        self.assertTrue(recovered.recovered_from_checkpoint)
