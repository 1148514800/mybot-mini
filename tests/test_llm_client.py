from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from openai import AsyncOpenAI

from mybot.core.config import GatewayConfig, build_client


class LLMClientTests(unittest.TestCase):
    def test_build_client_returns_async_client_with_configured_timeout(self) -> None:
        config = SimpleNamespace(
            api_key="test-key",
            provider="test",
            base_url=None,
            request_timeout_seconds=17,
        )

        client = build_client(config)
        try:
            self.assertIsInstance(client, AsyncOpenAI)
            self.assertEqual(client.timeout, 17)
        finally:
            asyncio.run(client.close())

    def test_gateway_config_rejects_non_positive_timeout(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be greater than 0"):
            GatewayConfig(request_timeout_seconds=0)

    def test_gateway_config_rejects_non_positive_approval_ttl(self) -> None:
        with self.assertRaisesRegex(ValueError, "approval_ttl_seconds"):
            GatewayConfig(approval_ttl_seconds=0)


if __name__ == "__main__":
    unittest.main()
