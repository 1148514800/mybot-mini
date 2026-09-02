from __future__ import annotations

import os
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from mybot.mcp import (
    MCPConfig,
    MCPConfigError,
    MissingEnvironmentVariable,
)


class MCPConfigTests(unittest.TestCase):
    def test_defaults_disable_mcp(self):
        config = MCPConfig.from_dict({})
        self.assertFalse(config.enabled)
        self.assertEqual(config.servers, ())

    def test_project_example_config_is_valid_and_disabled(self):
        path = Path(__file__).resolve().parents[1] / "config" / "config.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        config = MCPConfig.from_dict(data["mcp"])
        self.assertFalse(config.enabled)
        self.assertEqual(len(config.servers), 2)

    def test_parses_stdio_and_http_servers(self):
        config = MCPConfig.from_dict(
            {
                "enabled": True,
                "servers": {
                    "local": {
                        "transport": "stdio",
                        "command": "python",
                        "args": ["-m", "demo"],
                        "required": True,
                    },
                    "remote": {
                        "transport": "streamable_http",
                        "url": "http://127.0.0.1:8000/mcp",
                        "headers": {"Authorization": "Bearer ${TEST_TOKEN}"},
                    },
                },
            }
        )
        self.assertTrue(config.enabled)
        self.assertEqual(len(config.servers), 2)
        self.assertEqual(config.servers[0].args, ("-m", "demo"))
        self.assertTrue(config.servers[0].required)
        self.assertEqual(config.servers[1].transport, "streamable_http")

    def test_expands_environment_only_when_server_connects(self):
        config = MCPConfig.from_dict(
            {
                "enabled": True,
                "servers": {
                    "remote": {
                        "transport": "streamable_http",
                        "url": "http://localhost/mcp",
                        "headers": {
                            "Authorization": "Bearer ${MCP_TEST_TOKEN}"
                        },
                    }
                },
            }
        ).servers[0]
        with patch.dict(os.environ, {"MCP_TEST_TOKEN": "secret-value"}):
            self.assertEqual(
                config.resolved_headers()["Authorization"],
                "Bearer secret-value",
            )
            self.assertNotIn(
                "secret-value",
                config.redact_secrets("request used secret-value"),
            )

    def test_missing_environment_variable_is_explicit(self):
        config = MCPConfig.from_dict(
            {
                "enabled": True,
                "servers": {
                    "local": {
                        "transport": "stdio",
                        "command": "python",
                        "env": {"TOKEN": "${MCP_DEFINITELY_MISSING}"},
                    }
                },
            }
        ).servers[0]
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingEnvironmentVariable):
                config.resolved_env()

    def test_literal_sensitive_header_is_redacted_from_errors(self):
        config = MCPConfig.from_dict(
            {
                "servers": {
                    "remote": {
                        "transport": "streamable_http",
                        "url": "http://localhost/mcp",
                        "headers": {"Authorization": "Bearer literal-secret"},
                    }
                }
            }
        ).servers[0]
        redacted = config.redact_secrets(
            "request Authorization=Bearer literal-secret failed"
        )
        self.assertNotIn("literal-secret", redacted)

    def test_rejects_invalid_transport_and_policy(self):
        with self.assertRaises(MCPConfigError):
            MCPConfig.from_dict(
                {
                    "servers": {
                        "bad": {"transport": "sse", "url": "http://x"}
                    }
                }
            )
        with self.assertRaises(MCPConfigError):
            MCPConfig.from_dict(
                {
                    "servers": {
                        "bad": {
                            "transport": "stdio",
                            "command": "python",
                            "tool_policy": {"x": "execute_python"},
                        }
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
