from __future__ import annotations

import json
import unittest

import httpx
from fastapi.testclient import TestClient

from agentic_service.api import create_app
from agentic_service.config import AgenticSettings
from agentic_service.providers import BankingProviderRuntime
from agentic_service.service import AgenticService


class LiveServiceExecutionTests(unittest.TestCase):
    def _service(self, environment: dict[str, str], handler) -> AgenticService:
        settings = AgenticSettings(
            database_path=":memory:",
            provider_mode="live",
            banking_provider="saudi_open_banking",
            approval_mode="explicit",
            request_webhook_secret="request-secret",
            task_runner_enabled=False,
        )
        runtime = BankingProviderRuntime.from_settings(
            settings,
            environment=environment,
            transport=httpx.MockTransport(handler),
        )
        return AgenticService(settings=settings, banking_runtime=runtime)

    @staticmethod
    def _payload(request_id: str, text: str, *, approved: bool) -> dict:
        return {
            "request_id": request_id,
            "session_id": "live-session",
            "user_id": "user-1",
            "channel": "chat",
            "language": "en",
            "natural_language_request": text,
            "original_user_message": text,
            "confirmation": {"required": approved, "received": approved},
            "metadata": {"created_at": "2026-07-11T00:00:00+00:00", "source_provider": "test"},
        }

    def test_live_own_account_transfer_executes_after_exact_approval_and_customer_auth(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json={"data": {"accounts": [
                    {"accountId": "account-rajhi-001", "name": "Al Rajhi Main"},
                    {"accountId": "account-snb-002", "name": "SNB Secondary"},
                ]}})
            instruction = json.loads(request.content)
            self.assertEqual(instruction["debtorAccount"]["identification"], "account-rajhi-001")
            self.assertEqual(instruction["creditorAccount"]["identification"], "account-snb-002")
            self.assertEqual(request.headers["X-Idempotency-Key"], "live-transfer:1:0")
            self.assertTrue(request.headers["X-FAPI-Interaction-ID"])
            return httpx.Response(201, json={"paymentId": "provider-payment-1", "status": "Settled"})

        service = self._service(
            {
                "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/v1",
                "SAUDI_OPEN_BANKING_AUTH_MODE": "api_key_bearer_token",
                "SAUDI_OPEN_BANKING_API_KEY": "api-key",
                "SAUDI_OPEN_BANKING_ACCESS_TOKEN": "customer-token",
            },
            handler,
        )
        self.assertTrue(service.capabilities()["ready_for_live_money"])

        acknowledgement = service.submit(self._payload(
            "live-transfer",
            "Transfer 250 SAR from my Al Rajhi account to my SNB account",
            approved=True,
        ))
        task = service.get_task(acknowledgement["task_id"], "user-1")

        self.assertEqual(task["state"], "completed")
        self.assertTrue(task["application_approval_received"])
        self.assertEqual(task["safe_result"]["provider_reference"], "provider-payment-1")
        self.assertEqual(task["safe_result"]["transfer"]["status"], "settled")
        self.assertNotIn("customer-token", json.dumps(task))
        self.assertEqual([request.method for request in requests], ["GET", "POST"])

    def test_live_readiness_is_configuration_only_and_secret_free(self) -> None:
        service = self._service(
            {
                "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/v1",
                "SAUDI_OPEN_BANKING_AUTH_MODE": "api_key_bearer_token",
                "SAUDI_OPEN_BANKING_API_KEY": "never-leak-api-key",
                "SAUDI_OPEN_BANKING_ACCESS_TOKEN": "never-leak-customer-token",
            },
            lambda request: self.fail("readiness must not call the provider"),
        )

        response = TestClient(create_app(service)).get("/health/ready")
        serialized = json.dumps(response.json())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "live")
        self.assertTrue(response.json()["provider_profile"]["customer_authorization_configured"])
        self.assertNotIn("never-leak", serialized)

    def test_live_mutation_without_exact_approval_fails_before_provider_call(self) -> None:
        provider_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal provider_calls
            provider_calls += 1
            return httpx.Response(500, json={})

        service = self._service(
            {
                "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/v1",
                "SAUDI_OPEN_BANKING_AUTH_MODE": "bearer_token",
                "SAUDI_OPEN_BANKING_ACCESS_TOKEN": "customer-token",
            },
            handler,
        )

        acknowledgement = service.submit(self._payload(
            "unapproved-transfer",
            "Transfer 25 SAR from my Al Rajhi account to my SNB account",
            approved=False,
        ))
        task = service.get_task(acknowledgement["task_id"], "user-1")

        self.assertEqual(task["state"], "awaiting_approval")
        self.assertTrue(task["safe_result"]["confirmation_required"])
        self.assertEqual(provider_calls, 0)

    def test_live_monthly_report_uses_ais_data_with_provider_managed_consent_context(self) -> None:
        seen_context_headers: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_context_headers.append(request.headers.get("X-Customer-Context-ID", ""))
            if request.url.path.endswith("/accounts"):
                return httpx.Response(200, json={"accounts": [
                    {"accountId": "account-1", "name": "Main", "balance": {"amount": "1000.00", "currency": "SAR"}}
                ]})
            return httpx.Response(200, json={"transactions": [
                {"amount": {"amount": "1000.00", "currency": "SAR"}, "creditDebitIndicator": "Credit", "date": "2026-07-01", "category": "salary"},
                {"amount": {"amount": "100.00", "currency": "SAR"}, "creditDebitIndicator": "Debit", "date": "2026-07-03", "category": "food"},
            ]})

        service = self._service(
            {
                "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/v1",
                "SAUDI_OPEN_BANKING_API_KEY": "api-key",
                "SAUDI_OPEN_BANKING_CUSTOMER_CONTEXT_ID": "consent-user-1",
            },
            handler,
        )

        acknowledgement = service.submit(self._payload(
            "live-report", "Prepare my monthly financial report for July 2026", approved=False
        ))
        task = service.get_task(acknowledgement["task_id"], "user-1")
        report = task["safe_result"]["report"]

        self.assertEqual(task["state"], "completed")
        self.assertEqual(report["month"], "2026-07")
        self.assertEqual(report["income"]["amount"], "1000.00")
        self.assertEqual(report["expenses"]["amount"], "100.00")
        self.assertEqual(report["source"], "live_saudi_open_banking")
        self.assertEqual(seen_context_headers, ["consent-user-1", "consent-user-1"])

    def test_live_beneficiary_sync_is_capability_gated_and_persists_provider_reference(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            self.assertTrue(request.url.path.endswith("/beneficiaries"))
            return httpx.Response(201, json={"beneficiaryId": "provider-beneficiary-1", "status": "Active"})

        service = self._service(
            {
                "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/v1",
                "SAUDI_OPEN_BANKING_AUTH_MODE": "bearer_token",
                "SAUDI_OPEN_BANKING_ACCESS_TOKEN": "customer-token",
                "SAUDI_OPEN_BANKING_BENEFICIARY_WRITE_ENABLED": "true",
            },
            handler,
        )

        acknowledgement = service.submit(self._payload(
            "live-beneficiary",
            "Add beneficiary SA03 8000 0000 6080 1016 7519",
            approved=True,
        ))
        task = service.get_task(acknowledgement["task_id"], "user-1")
        stored = service.repository.list_beneficiaries("user-1")[0]

        self.assertEqual(task["state"], "completed")
        self.assertEqual(task["safe_result"]["beneficiary"]["provider_sync_status"], "active")
        self.assertEqual(stored["provider_reference"], "provider-beneficiary-1")
        self.assertNotIn("SA0380000000608010167519", json.dumps(task["safe_result"]))

    def test_separate_live_broker_action_stays_fail_closed_without_http_fallback(self) -> None:
        provider_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal provider_calls
            provider_calls += 1
            return httpx.Response(200, json={})

        service = self._service(
            {
                "SAUDI_OPEN_BANKING_BASE_URL": "https://sandbox.example/v1",
                "SAUDI_OPEN_BANKING_AUTH_MODE": "bearer_token",
                "SAUDI_OPEN_BANKING_ACCESS_TOKEN": "customer-token",
            },
            handler,
        )

        acknowledgement = service.submit(self._payload(
            "live-investment", "Buy 10 shares of 2222", approved=True
        ))
        task = service.get_task(acknowledgement["task_id"], "user-1")

        self.assertEqual(task["state"], "failed")
        self.assertIn("broker provider", task["safe_result"]["error"])
        self.assertEqual(provider_calls, 0)


if __name__ == "__main__":
    unittest.main()
