from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time
import unittest

import httpx

from agentic_service.live_adapters import (
    LiveProviderConfigurationError,
    LiveProviderRequestError,
    SaudiOpenBankingAdapter,
    SaudiOpenBankingProfile,
)


class LiveProfileTests(unittest.TestCase):
    def test_api_key_profile_has_conditional_requirements_and_hides_secrets(self) -> None:
        profile = SaudiOpenBankingProfile.from_env(
            {
                "SAUDI_OPEN_BANKING_BASE_URL": "https://bank.example/open-banking/v1",
                "SAUDI_OPEN_BANKING_API_KEY": "never-print-this",
                "SAUDI_OPEN_BANKING_CUSTOMER_CONTEXT_ID": "never-print-context",
            }
        )

        self.assertEqual(profile.missing_requirements(), [])
        profile.ensure_usable()
        self.assertNotIn("never-print-this", repr(profile))
        self.assertNotIn("never-print-context", repr(profile))
        self.assertEqual(profile.auth_mode, "api_key")

    def test_oauth_profile_requires_only_its_selected_auth_inputs(self) -> None:
        profile = SaudiOpenBankingProfile(
            base_url="https://bank.example",
            auth_mode="oauth_client_credentials",
        )

        missing = profile.missing_requirements()
        self.assertIn("SAUDI_OPEN_BANKING_TOKEN_URL", missing)
        self.assertIn("SAUDI_OPEN_BANKING_CLIENT_ID", missing)
        self.assertIn("SAUDI_OPEN_BANKING_CLIENT_SECRET", missing)
        self.assertNotIn("SAUDI_OPEN_BANKING_API_KEY", missing)

    def test_profile_rejects_insecure_or_malformed_provider_configuration(self) -> None:
        insecure = SaudiOpenBankingProfile(base_url="http://bank.example", api_key="key")
        with self.assertRaisesRegex(LiveProviderConfigurationError, "must use HTTPS"):
            insecure.ensure_usable()

        bad_path = SaudiOpenBankingProfile(
            base_url="https://bank.example",
            api_key="key",
            accounts_path="https://attacker.example/accounts",
        )
        with self.assertRaisesRegex(LiveProviderConfigurationError, "accounts path"):
            bad_path.ensure_usable()

    def test_mtls_files_are_required_only_when_profile_enables_mtls(self) -> None:
        profile = SaudiOpenBankingProfile(
            base_url="https://bank.example", api_key="key", mtls_required=True,
            mtls_cert_path="/missing/cert.pem", mtls_key_path="/missing/key.pem",
        )
        missing = profile.missing_requirements()
        self.assertTrue(any("file not found" in item for item in missing))


class LiveAdapterContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_key_requests_preserve_base_path_and_correlation_headers(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(201, json={"paymentId": "payment-1", "status": "Pending"})

        profile = SaudiOpenBankingProfile(
            base_url="https://bank.example/open-banking/v1",
            api_key="sandbox-key",
            api_version="2026-01",
        )
        adapter = SaudiOpenBankingAdapter(profile, transport=httpx.MockTransport(handler))

        result = await adapter.initiate_payment(
            {"amount": {"amount": "25.00", "currency": "SAR"}},
            idempotency_key="task-1:step-1",
            interaction_id="interaction-1",
        )

        self.assertEqual(result["paymentId"], "payment-1")
        request = requests[0]
        self.assertEqual(str(request.url), "https://bank.example/open-banking/v1/payments")
        self.assertEqual(request.headers["X-API-Key"], "sandbox-key")
        self.assertEqual(request.headers["X-Idempotency-Key"], "task-1:step-1")
        self.assertEqual(request.headers["X-FAPI-Interaction-ID"], "interaction-1")
        self.assertEqual(request.headers["X-API-Version"], "2026-01")
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(json.loads(request.content)["amount"]["currency"], "SAR")

    async def test_customer_bound_token_overrides_configured_application_auth(self) -> None:
        seen_authorization = ""

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_authorization
            seen_authorization = request.headers.get("Authorization", "")
            return httpx.Response(200, json={"accounts": []})

        profile = SaudiOpenBankingProfile(
            base_url="https://bank.example", auth_mode="bearer_token", access_token="application-token"
        )
        adapter = SaudiOpenBankingAdapter(profile, transport=httpx.MockTransport(handler))

        await adapter.list_accounts(access_token="customer-consent-token")

        self.assertEqual(seen_authorization, "Bearer customer-consent-token")

    async def test_provider_resource_identifiers_are_url_encoded(self) -> None:
        seen_raw_path = b""

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_raw_path
            seen_raw_path = request.url.raw_path
            return httpx.Response(200, json={"transactions": []})

        adapter = SaudiOpenBankingAdapter(
            SaudiOpenBankingProfile(base_url="https://bank.example/v1", api_key="key"),
            transport=httpx.MockTransport(handler),
        )

        await adapter.list_transactions("account/id with spaces")

        self.assertEqual(seen_raw_path, b"/v1/accounts/account%2Fid%20with%20spaces/transactions")

    async def test_oauth_client_credentials_token_is_acquired_and_cached(self) -> None:
        token_requests = 0
        account_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_requests, account_requests
            if request.url.host == "identity.example":
                token_requests += 1
                self.assertTrue(request.headers["Authorization"].startswith("Basic "))
                return httpx.Response(200, json={"access_token": "issued-token", "expires_in": 300})
            account_requests += 1
            self.assertEqual(request.headers["Authorization"], "Bearer issued-token")
            return httpx.Response(200, json={"accounts": []})

        profile = SaudiOpenBankingProfile(
            base_url="https://bank.example/v1",
            auth_mode="oauth_client_credentials",
            token_url="https://identity.example/oauth/token",
            client_id="client-id",
            client_secret="client-secret",
            token_scope="accounts payments",
        )
        adapter = SaudiOpenBankingAdapter(profile, transport=httpx.MockTransport(handler))

        await adapter.list_accounts()
        await adapter.list_accounts()

        self.assertEqual(token_requests, 1)
        self.assertEqual(account_requests, 2)

    async def test_provider_error_is_safe_and_classified_without_response_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"access_token": "must-not-leak", "error": "private provider detail"})

        adapter = SaudiOpenBankingAdapter(
            SaudiOpenBankingProfile(base_url="https://bank.example", api_key="secret-key"),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(LiveProviderRequestError) as raised:
            await adapter.list_accounts()

        error = raised.exception
        self.assertEqual(error.status_code, 429)
        self.assertTrue(error.retryable)
        self.assertNotIn("must-not-leak", str(error))
        self.assertNotIn("secret-key", str(error))

    async def test_mutations_require_stable_idempotency_and_interaction_ids(self) -> None:
        adapter = SaudiOpenBankingAdapter(
            SaudiOpenBankingProfile(base_url="https://bank.example", api_key="key"),
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        )

        with self.assertRaises(LiveProviderConfigurationError):
            await adapter.initiate_payment({}, idempotency_key="", interaction_id="")

    async def test_beneficiary_write_is_capability_gated(self) -> None:
        adapter = SaudiOpenBankingAdapter(
            SaudiOpenBankingProfile(base_url="https://bank.example", api_key="key"),
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        )

        with self.assertRaisesRegex(LiveProviderConfigurationError, "does not enable beneficiary writes"):
            await adapter.add_beneficiary({}, idempotency_key="one", interaction_id="two")


class LiveAdapterThreadingTests(unittest.TestCase):
    def test_oauth_token_refresh_is_safe_across_worker_event_loops(self) -> None:
        token_requests = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_requests
            if request.url.path.endswith("/token"):
                token_requests += 1
                time.sleep(0.02)
                return httpx.Response(200, json={"access_token": "shared-token", "expires_in": 300})
            return httpx.Response(200, json={"accounts": []})

        adapter = SaudiOpenBankingAdapter(
            SaudiOpenBankingProfile(
                base_url="https://bank.example/v1",
                auth_mode="oauth_client_credentials",
                token_url="https://identity.example/token",
                client_id="client-id",
                client_secret="client-secret",
            ),
            transport=httpx.MockTransport(handler),
        )
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: asyncio.run(adapter.list_accounts()), range(4)))

        self.assertEqual(token_requests, 1)
        self.assertEqual(results, [{"accounts": []}] * 4)


if __name__ == "__main__":
    unittest.main()
