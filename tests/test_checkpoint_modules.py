from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest

from mybot.storage.checkpoints.sanitizer import sanitize_messages
from mybot.storage.checkpoints.serialization import (
    recent_task_from_checkpoint,
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
                    [sys.executable, '-c', f'''import importlib
importlib.import_module({first!r})
from mybot.storage.checkpoint import ActiveTaskCheckpointStore as legacy
from mybot.storage.checkpoints import ActiveTaskCheckpointStore as public
from mybot.storage.checkpoints.models import RecoveredActiveCheckpoint
from mybot.storage.checkpoints.serialization import recent_task_from_checkpoint
from mybot.agent.checkpoint_recovery import (
    recent_task_from_checkpoint as old,
)
assert legacy is public
assert old is recent_task_from_checkpoint
assert RecoveredActiveCheckpoint.__module__ == 'mybot.storage.checkpoints.models'\n''' ],
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

    def test_recent_task_adapter_binds_identity_and_disables_live_state(self):
        payload = {
            'session_key': 'cli:a',
            'task_id': 'task-1',
            'origin_run_id': 'run-1',
            'browser_mode': 'managed',
            'messages': [{'role': 'user', 'content': 'inspect'}],
            'loaded_skills': ['skills/demo/skill.md'],
            'browser_state': {
                'latest_snapshot': 'live',
                'browser_initialized': True,
            },
            'expires_at': '2026-09-06T00:00:00+00:00',
        }
        recovered = recent_task_from_checkpoint(payload)
        self.assertEqual(recovered.session_key, 'cli:a')
        self.assertEqual(recovered.task_id, 'task-1')
        self.assertEqual(recovered.loaded_skills, ['skills/demo/skill.md'])
        self.assertFalse(recovered.browser_initialized)
        self.assertEqual(recovered.browser_snapshot, '')
        self.assertTrue(recovered.recovered_from_checkpoint)


if __name__ == '__main__':
    unittest.main()
