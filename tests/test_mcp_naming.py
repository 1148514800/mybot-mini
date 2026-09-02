from __future__ import annotations

import re
import unittest

from mybot.mcp import (
    MAX_TOOL_NAME_LENGTH,
    build_mcp_tool_name,
    resolve_name_collision,
    sanitize_name_component,
)


class MCPNamingTests(unittest.TestCase):
    def test_normal_name_is_readable(self):
        self.assertEqual(
            build_mcp_tool_name("github", "search_code"),
            "mcp__github__search_code",
        )

    def test_spaces_slashes_dots_and_unicode_are_sanitized(self):
        for value in ("my server", "repo/search", "tools.v2", "搜索工具"):
            with self.subTest(value=value):
                name = build_mcp_tool_name(value, value)
                self.assertRegex(name, r"^[A-Za-z0-9_-]+$")
                self.assertLessEqual(len(name), MAX_TOOL_NAME_LENGTH)

    def test_same_input_has_stable_hash(self):
        first = build_mcp_tool_name("my server", "search/tool")
        second = build_mcp_tool_name("my server", "search/tool")
        self.assertEqual(first, second)
        self.assertRegex(first, r"_[0-9a-f]{8}$")

    def test_very_long_name_is_bounded_with_hash(self):
        name = build_mcp_tool_name("server" * 30, "tool" * 40)
        self.assertEqual(len(name), MAX_TOOL_NAME_LENGTH)
        self.assertRegex(name, r"_[0-9a-f]{8}$")

    def test_same_sanitized_text_gets_different_stable_names(self):
        dotted = build_mcp_tool_name("demo", "search.tool")
        slashed = build_mcp_tool_name("demo", "search/tool")
        self.assertNotEqual(dotted, slashed)
        self.assertEqual(dotted, build_mcp_tool_name("demo", "search.tool"))

    def test_collision_resolution_does_not_overwrite(self):
        candidate = build_mcp_tool_name("demo", "search")
        resolved = resolve_name_collision(
            candidate,
            "demo",
            "search",
            {candidate},
        )
        self.assertNotEqual(resolved, candidate)
        self.assertLessEqual(len(resolved), MAX_TOOL_NAME_LENGTH)
        self.assertRegex(resolved, r"^[A-Za-z0-9_-]+$")

    def test_empty_component_has_safe_fallback(self):
        self.assertEqual(sanitize_name_component("中文"), "unnamed")


if __name__ == "__main__":
    unittest.main()

