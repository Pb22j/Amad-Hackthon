from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from unittest import TestCase, mock

from agentic_service.config import AgenticSettings
from agentic_service.domain import ActionPlan, ActionType, AuditEvent, Money, TaskRecord, TaskState
from agentic_service.security import InvalidIban, mask_iban, normalize_saudi_iban, sign_payload, verify_payload_signature
from agentic_service.storage import IdempotencyConflict, SQLiteRepository


def _task(request_id: str = "request-1") -> TaskRecord:
    return TaskRecord.new(
        request_id=request_id,
        session_id="session-1",
        user_id="user-1",
        language="en",
        natural_language_request="Transfer 25 SAR",
    )


class FoundationTests(TestCase):
    def test_money_is_exact_and_uses_minor_units(self) -> None:
        money = Money.positive("19.50", "sar")
        self.assertEqual(money.currency, "SAR")
        self.assertEqual(money.minor_units, 1950)
        self.assertEqual(Money.from_minor_units(1950, "SAR"), money)
        with self.assertRaises(ValueError):
            Money.positive("1.001", "SAR")

    def test_action_plan_accepts_compatibility_names(self) -> None:
        plan = ActionPlan(action=ActionType.LIST_STORE_ITEMS, parameters={"category": "gifts"}, user_message="Here are items")
        self.assertIs(plan.action_type, ActionType.LIST_STORE_ITEMS)
        self.assertEqual(plan.parameters["category"], "gifts")
        self.assertEqual(ActionPlan.from_dict(plan.to_dict()).user_message, "Here are items")
        with self.assertRaises(ValueError):
            ActionPlan(ActionType.USER_TRANSFER, missing_fields=("amount",))

    def test_saudi_iban_validation_masking_and_hmac(self) -> None:
        iban = normalize_saudi_iban("SA03 8000 0000 6080 1016 7519")
        self.assertEqual(iban, "SA0380000000608010167519")
        self.assertEqual(mask_iban(iban), "SA03****************7519")
        with self.assertRaises(InvalidIban):
            normalize_saudi_iban("SA0380000000608010167518")
        body = b'{"event":"completed"}'
        signature = sign_payload("test-secret", body)
        self.assertTrue(verify_payload_signature("test-secret", body, signature))
        self.assertFalse(verify_payload_signature("test-secret", body, "bad"))

    def test_request_idempotency_and_task_audit(self) -> None:
        repo = SQLiteRepository()
        task = _task()
        created = repo.create_or_get_task(task, {"request_id": task.request_id, "message": "Transfer 25 SAR"})
        repeated = repo.create_or_get_task(_task(), {"request_id": task.request_id, "message": "Transfer 25 SAR"})
        self.assertTrue(created.created)
        self.assertFalse(repeated.created)
        self.assertEqual(repeated.task.task_id, task.task_id)
        with self.assertRaises(IdempotencyConflict):
            repo.create_or_get_task(_task(), {"request_id": task.request_id, "message": "Transfer 26 SAR"})

        plan = ActionPlan(ActionType.LIST_STORE_ITEMS)
        completed = repo.transition_task(task.task_id, TaskState.COMPLETED, plan=plan, safe_result={"token": "never-log"})
        self.assertEqual(completed.version, 1)
        repo.record_audit(AuditEvent(task_id=task.task_id, action="complete", result="ok", details={"access_token": "secret"}))
        self.assertEqual(repo.list_audit(task.task_id)[0]["details"]["access_token"], "[REDACTED]")

    def test_beneficiary_qatta_and_atomic_inventory(self) -> None:
        repo = SQLiteRepository()
        iban = "SA0380000000608010167519"
        beneficiary, created = repo.add_beneficiary("user-1", iban, "Friend")
        self.assertTrue(created)
        self.assertEqual(beneficiary["iban"], iban)
        self.assertFalse(repo.add_beneficiary("user-1", iban, "Changed")[1])
        self.assertTrue(repo.delete_beneficiary("user-1", beneficiary_id=beneficiary["beneficiary_id"]))
        self.assertEqual(repo.list_beneficiaries("user-1"), [])

        qatta_id = repo.create_qatta("owner", Money.positive("10"), "Lunch", {"a": 500, "b": 500})
        self.assertTrue(repo.settle_qatta_share(qatta_id, "a", "payment-a"))
        self.assertTrue(repo.settle_qatta_share(qatta_id, "b", "payment-b"))
        self.assertEqual(repo.get_qatta(qatta_id)["state"], "completed")

        repo.upsert_store_item("MUG", "Mug", Money.positive("10"), stock=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda item: repo.reserve_inventory(f"order-{item}", "MUG", 1, "2099-01-01T00:00:00+00:00"), (1, 2)))
        self.assertEqual(outcomes.count(True), 1)

    def test_live_mode_refuses_auto_mock_approval(self) -> None:
        environment = dict(os.environ, AGENTIC_PROVIDER_MODE="live", AGENTIC_APPROVAL_MODE="auto_mock")
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(ValueError):
                AgenticSettings.from_env()

    def test_banking_provider_selection_defaults_to_no_key_mock(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = AgenticSettings.from_env()
        self.assertEqual(settings.provider_mode, "mock")
        self.assertEqual(settings.banking_provider, "mock")

    def test_single_backend_selector_enables_saudi_profile_but_still_requires_explicit_approval(self) -> None:
        environment = {
            "AGENTIC_BANKING_BACKEND": "saudi_open_banking",
            "AGENTIC_APPROVAL_MODE": "explicit",
        }
        with mock.patch.dict(os.environ, environment, clear=True):
            settings = AgenticSettings.from_env()
        self.assertEqual(settings.provider_mode, "live")
        self.assertEqual(settings.banking_provider, "saudi_open_banking")
