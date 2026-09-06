import unittest
from types import SimpleNamespace

from mybot.agent.tool_calls import (
    deserialize_tool_call,
    serialize_tool_call,
    tool_call_signature,
)


class ToolCallCodecTests(unittest.TestCase):
    def test_signature_normalizes_json_arguments(self):
        first = SimpleNamespace(
            function=SimpleNamespace(name="read_file", arguments='{"path":"x","n":1}')
        )
        second = SimpleNamespace(
            function=SimpleNamespace(name="read_file", arguments='{"n":1,"path":"x"}')
        )

        self.assertEqual(tool_call_signature(first), tool_call_signature(second))

    def test_serialize_and_deserialize_round_trip(self):
        original = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(name="read_file", arguments='{"path":"x"}'),
        )

        serialized = serialize_tool_call(original)
        restored = deserialize_tool_call(serialized)

        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.function.name, original.function.name)
        self.assertEqual(restored.function.arguments, original.function.arguments)
