from __future__ import annotations

import unittest

import httpx

from agentic_service.config import AgenticSettings
from agentic_service.live_adapters import LiveProviderConfigurationError
from agentic_service.providers import BankingProviderRuntime
from agentic_service.service import AgenticService


class BankingProviderRuntimeTests(unittest.TestCase):
    def test_mock_is_the_zero_key_default_and_never_builds_a_live_client(self) -> None:
        runtime = BankingProviderRuntime.from_settings(
            AgenticSettings(),
            environment={
                "SAUDI_OPEN_BANKING_BASE_URL": "not-a-url",
                "SAUDI_OPEN_BANKING_AUTH_MODE": "not-an-auth-mode",
            },
        )

        self.assertEqual(runtime.mode, "mock")
        self.assertEqual(runtime.provider_name, "mock")
        self.assertIsNone(runtime.live_adapter)
        self.assertEqual(runtime.readiness()["status"], "ready")

    def test_live_provider_is_selected_entirely_from_settings_and_environment(self) -> None:
        settings = AgenticSettings(
            database_path=":memory:",
            provider_mode="live",
            banking_provider="saudi_open_banking",
            approval_mode="explicit",
            request_webhook_secret="request-secret",
            task_runner_enabled=False,
        )
        environment = {
            "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/open-banking/v1",
            "SAUDI_OPEN_BANKING_API_KEY": "sandbox-key",
            "SAUDI_OPEN_BANKING_PIS_ENABLED": "true",
        }
        runtime = BankingProviderRuntime.from_settings(
            settings,
            environment=environment,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        )

        self.assertEqual(runtime.mode, "live")
        self.assertIsNotNone(runtime.live_adapter)
        self.assertEqual(runtime.readiness()["status"], "ready")
        self.assertTrue(runtime.capabilities()["payment_initiation"])

        service = AgenticService(settings=settings, banking_runtime=runtime)
        capabilities = service.capabilities()
        self.assertEqual(capabilities["provider"], "saudi_open_banking")
        self.assertTrue(capabilities["provider_transport_ready"])
        self.assertTrue(capabilities["capabilities"]["live_saudi_open_banking"])
        self.assertFalse(capabilities["ready_for_live_money"])

    def test_live_startup_fails_closed_and_lists_missing_environment_names(self) -> None:
        settings = AgenticSettings(
            provider_mode="live", banking_provider="saudi_open_banking", approval_mode="explicit"
        )

        with self.assertRaises(LiveProviderConfigurationError) as raised:
            BankingProviderRuntime.from_settings(settings, environment={})

        self.assertIn("SAUDI_OPEN_BANKING_BASE_URL", str(raised.exception))
        self.assertIn("SAUDI_OPEN_BANKING_API_KEY", str(raised.exception))

    def test_live_service_requires_authenticated_interaction_requests(self) -> None:
        settings = AgenticSettings(
            database_path=":memory:", provider_mode="live",
            banking_provider="saudi_open_banking", approval_mode="explicit",
        )
        runtime = BankingProviderRuntime.from_settings(
            settings,
            environment={
                "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/v1",
                "SAUDI_OPEN_BANKING_API_KEY": "key",
            },
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        )

        with self.assertRaisesRegex(ValueError, "AGENTIC_REQUEST_WEBHOOK_SECRET"):
            AgenticService(settings=settings, banking_runtime=runtime)


if __name__ == "__main__":
    unittest.main()
