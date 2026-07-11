from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_service.config import AgenticSettings
from agentic_service.service import AgenticService


class AgenticServiceMvpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgenticService(
            settings=AgenticSettings(database_path=":memory:", task_runner_enabled=False)
        )
        self.counter = 0

    def submit(self, user_id: str, text: str, *, language: str = "en") -> dict:
        self.counter += 1
        acknowledgement = self.service.submit(
            {
                "request_id": f"request-{self.counter}",
                "session_id": f"session-{user_id}",
                "user_id": user_id,
                "channel": "chat",
                "language": language,
                "natural_language_request": text,
                "original_user_message": text,
                "confirmation": {"required": True, "received": True},
                "metadata": {"created_at": "2026-07-10T00:00:00+00:00", "source_provider": "test"},
            }
        )
        task = self.service.get_task(acknowledgement["task_id"], user_id)
        self.assertIsNotNone(task)
        return task

    def test_transfers_beneficiaries_gifts_and_savings(self) -> None:
        own = self.submit("user-1", "Transfer 250 SAR from my Al Rajhi account to my SNB account")
        self.assertEqual(own["state"], "completed")
        self.assertEqual(own["plan"]["action_type"], "own_account_transfer")

        same_bank = self.submit(
            "user-1",
            "Transfer 25 SAR from my Al Rajhi Main account to my Al Rajhi Wallet account",
        )
        self.assertEqual(same_bank["state"], "completed")
        self.assertEqual(same_bank["safe_result"]["transfer"]["source"]["bank"], "Al Rajhi")
        self.assertEqual(same_bank["safe_result"]["transfer"]["destination"]["bank"], "Al Rajhi")

        peer = self.submit("user-1", "Send 125 SAR to @sara")
        self.assertEqual(peer["state"], "completed")

        added = self.submit("user-1", "Add beneficiary SA03 8000 0000 6080 1016 7519")
        beneficiary = added["safe_result"]["beneficiary"]
        self.assertTrue(beneficiary["iban_masked"].startswith("SA03"))

        deleted = self.submit("user-1", f"Delete beneficiary {beneficiary['beneficiary_id']}")
        self.assertEqual(deleted["state"], "completed")

        gift = self.submit("user-1", "Send a gift of 50 SAR to @noura")
        self.assertTrue(gift["safe_result"]["is_gift"])
        self.assertTrue(gift["safe_result"]["gift_id"])

        savings = self.submit("user-1", "Open a savings account and transfer 500 SAR from my Al Rajhi account")
        self.assertIn(savings["state"], {"completed", "partially_completed"})
        self.assertTrue(savings["safe_result"]["account_created"])

    def test_investing_qatta_reporting_analysis_and_store(self) -> None:
        investment = self.submit("user-1", "Buy 10 shares of 2222")
        self.assertEqual(investment["state"], "completed")
        self.assertEqual(investment["safe_result"]["order"]["symbol"], "2222")

        qatta = self.submit("user-1", "Split 300 SAR between @ali and @sara")
        qatta_id = qatta["safe_result"]["qatta"]["qatta_id"]
        share = self.submit("user-2", f"Pay my Qatta {qatta_id} share")
        self.assertEqual(share["state"], "completed")

        report = self.submit("user-1", "Prepare my monthly financial report for June 2026")
        self.assertIn("report", report["safe_result"])
        self.assertEqual(report["safe_result"]["report"]["month"], "2026-06")

        analysis = self.submit("user-1", "Analyze my finances")
        self.assertTrue(analysis["safe_result"]["read_only"])

        catalog = self.submit("user-1", "Show the store catalog")
        self.assertGreaterEqual(len(catalog["safe_result"]["items"]), 1)

        purchase = self.submit("user-1", "Buy SKU-COFFEE-01 from the store")
        self.assertEqual(purchase["safe_result"]["order"]["state"], "paid")

        arabic_purchase = self.submit(
            "user-1", "اشتري مجموعة القهوة السعودية من المتجر", language="ar"
        )
        self.assertEqual(arabic_purchase["safe_result"]["order"]["sku"], "COFFEE-01")

    def test_monthly_report_allows_negative_net_cashflow(self) -> None:
        transactions = [{
            "amount": "-100.00",
            "category": "shopping",
            "occurred_at": "2026-07-10T00:00:00+00:00",
        }]
        with (
            patch.object(type(self.service.backend), "transactions_for_month", return_value=transactions),
            patch.object(type(self.service.backend), "list_accounts", return_value=[]),
        ):
            report = self.submit("user-1", "Prepare my monthly financial report for July 2026")

        self.assertEqual(report["state"], "completed")
        self.assertEqual(report["safe_result"]["report"]["net_cashflow"]["amount"], "-100.00")

    def test_mutation_waits_for_explicit_confirmation(self) -> None:
        acknowledgement = self.service.submit({
            "request_id": "unconfirmed-request",
            "session_id": "session-user-1",
            "user_id": "user-1",
            "channel": "chat",
            "language": "en",
            "natural_language_request": "Add beneficiary SA03 8000 0000 6080 1016 7519",
            "original_user_message": "Add beneficiary SA03 8000 0000 6080 1016 7519",
            "confirmation": {"required": True, "received": False},
            "metadata": {"created_at": "2026-07-10T00:00:00+00:00", "source_provider": "test"},
        })
        task = self.service.get_task(acknowledgement["task_id"], "user-1")
        self.assertEqual(task["state"], "awaiting_approval")
        self.assertTrue(task["safe_result"]["confirmation_required"])

    def test_request_idempotency_replays_original_task(self) -> None:
        payload = {
            "request_id": "same-request", "session_id": "session-user-1", "user_id": "user-1",
            "channel": "chat", "language": "en", "natural_language_request": "Show the store catalog",
            "original_user_message": "Show the store catalog", "confirmation": {"required": False, "received": True},
            "metadata": {"created_at": "2026-07-10T00:00:00+00:00", "source_provider": "test"},
        }
        first = self.service.submit(payload)
        second = self.service.submit(payload)
        self.assertEqual(first["task_id"], second["task_id"])

    def test_validated_model_plan_executes_through_agentic_service(self) -> None:
        planned = json.dumps({
            "intent": "transfer_between_accounts",
            "language": "en",
            "amount": 250,
            "recipient": None,
            "source_account": "Al Rajhi",
            "destination_account": "SNB",
            "iban": None,
            "symbol": None,
            "quantity": None,
            "participants": [],
            "sku": None,
            "note": None,
            "period": None,
            "clarification_question": None,
        })
        task = self.submit("user-1", planned)
        self.assertEqual(task["state"], "completed")
        self.assertEqual(task["plan"]["action_type"], "own_account_transfer")
        self.assertIn("transfer", task["safe_result"])


if __name__ == "__main__":
    unittest.main()
