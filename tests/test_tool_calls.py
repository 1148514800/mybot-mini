import unittest
from types import SimpleNamespace

from mybot.agent.tool_calls import tool_call_signature


class ToolCallSignatureTests(unittest.TestCase):
    def test_signature_normalizes_json_arguments(self):
        first = SimpleNamespace(
            function=SimpleNamespace(name="read_file", arguments='{"path":"x","n":1}')
        )
        second = SimpleNamespace(
            function=SimpleNamespace(name="read_file", arguments='{"n":1,"path":"x"}')
        )

        self.assertEqual(tool_call_signature(first), tool_call_signature(second))
