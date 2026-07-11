"""Application service that executes the complete mock-backed financial MVP."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping
from uuid import uuid4

from .config import AgenticSettings
from .domain import ActionPlan, ActionType, AuditEvent, Money, StepState, TaskRecord, TaskState
from .mock_backend import MockFinancialBackend
from .planner import plan_request
from .providers import BankingProviderRuntime
from .security import mask_iban, normalize_saudi_iban, sanitize_user_text
from .storage import IdempotencyConflict, SQLiteRepository


class AgenticService:
    """Persist, plan, execute, audit, and notify one natural-language task.

    It is deliberately a deterministic executor.  The planner can only choose
    from ``ActionType``; this class resolves every account/payee and uses
    server-side balances, prices, and inventory before applying a mutation.
    """

    def __init__(
        self,
        *,
        settings: AgenticSettings | None = None,
        repository: SQLiteRepository | None = None,
        backend: MockFinancialBackend | None = None,
        banking_runtime: BankingProviderRuntime | None = None,
    ) -> None:
        self.settings = settings or AgenticSettings.from_env()
        if self.settings.provider_mode == "live" and not self.settings.request_webhook_secret:
            raise ValueError("Live mode requires AGENTIC_REQUEST_WEBHOOK_SECRET (or AGENTIC_WEBHOOK_SECRET)")
        self.settings.ensure_data_directory()
        self.repository = repository or SQLiteRepository(self.settings.database_path)
        self.backend = backend or MockFinancialBackend()
        # In mock mode this never reads live credentials or constructs an HTTP
        # client. Live mode validates and selects its adapter at startup.
        self.banking_runtime = banking_runtime or BankingProviderRuntime.from_settings(self.settings)
        self._threads: set[threading.Thread] = set()
        self._thread_lock = threading.Lock()
        self._seed_store()

    def _seed_store(self) -> None:
        self.repository.upsert_store_item(
            "COFFEE-01", "Saudi Coffee Set", Money.positive("65.00"), 12,
            description="A curated Saudi coffee gift set.", ui_metadata={"image_key": "coffee-set", "category": "gifts"},
        )
        self.repository.upsert_store_item(
            "MUG-01", "Nafi Mug", Money.positive("35.00"), 8,
            description="Ceramic Nafi mug.", ui_metadata={"image_key": "mug", "category": "lifestyle"},
        )
        self.repository.upsert_store_item(
            "CARD-01", "Digital Gift Card", Money.positive("100.00"), 100,
            description="Digital store gift card.", ui_metadata={"image_key": "gift-card", "category": "gifts"},
        )

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a request and return a fast idempotent acknowledgement."""
        confirmation = payload.get("confirmation") or {}
        task = TaskRecord.new(
            request_id=str(payload["request_id"]), session_id=str(payload["session_id"]),
            user_id=str(payload["user_id"]), language=str(payload["language"]),
            natural_language_request=str(payload["natural_language_request"]),
            application_approval_received=bool(
                confirmation.get("required") and confirmation.get("received")
            ),
        )
        try:
            outcome = self.repository.create_or_get_task(task, payload)
        except IdempotencyConflict as exc:
            raise ValueError(str(exc)) from exc
        existing = outcome.task
        acknowledgement = {
            "request_id": existing.request_id,
            "task_id": existing.task_id,
            "status": "accepted",
            "user_safe_message": "",
        }
        if not outcome.created:
            return acknowledgement
        self.repository.record_audit(AuditEvent(
            task_id=existing.task_id, actor_id=existing.user_id, action="request_accepted", result="accepted",
            details={"request_id": existing.request_id, "language": existing.language},
        ))
        # The interaction layer already renders the synchronous acknowledgement
        # from this method.  Posting an ``accepted`` callback here can deadlock
        # a synchronous interaction->agentic request with its own callback.
        # Background execution emits only meaningful progress/input/result events.
        if self.settings.task_runner_enabled:
            self._start_background(existing.task_id)
        else:
            self.process_task(existing.task_id)
        return acknowledgement

    def _start_background(self, task_id: str) -> None:
        thread = threading.Thread(target=self._run_thread, args=(task_id,), daemon=True, name=f"agentic-{task_id[:8]}")
        with self._thread_lock:
            self._threads.add(thread)
        thread.start()

    def _run_thread(self, task_id: str) -> None:
        try:
            self.process_task(task_id)
        finally:
            with self._thread_lock:
                current = threading.current_thread()
                self._threads.discard(current)

    def process_task(self, task_id: str) -> dict[str, Any] | None:
        """Run a task synchronously; useful for tests and local task runners."""
        task = self.repository.get_task(task_id)
        if task is None or task.state.terminal:
            return task.to_dict() if task else None
        try:
            task = self.repository.transition_task(task_id, TaskState.PLANNING)
            self._emit(task, "progress", self._message(task.language, "planning"), {})
            plan = plan_request(task.natural_language_request, task.language)
            if plan.action_type == ActionType.NEED_INPUT:
                result = {"missing_fields": list(plan.missing_fields), "question": plan.user_message or self._message(task.language, "input_needed")}
                task = self.repository.transition_task(task.task_id, TaskState.INPUT_NEEDED, plan=plan, safe_result=result)
                self.repository.record_audit(AuditEvent(task_id=task.task_id, actor_id=task.user_id, action="plan", result="input_needed", details=result))
                self._emit(task, "input_needed", result["question"], result)
                return task.to_dict()

            if plan.action_type.is_mutation and not task.application_approval_received:
                result = {
                    "confirmation_required": True,
                    "question": self._message(task.language, "approval_required"),
                    "user_safe_summary": self._message(task.language, "approval_required"),
                }
                task = self.repository.transition_task(
                    task.task_id, TaskState.AWAITING_APPROVAL, plan=plan, safe_result=result
                )
                self.repository.record_audit(AuditEvent(
                    task_id=task.task_id,
                    actor_id=task.user_id,
                    action=plan.action_type.value,
                    result="awaiting_approval",
                    details={"confirmation_required": True},
                ))
                self._emit(task, "input_needed", result["question"], result)
                return task.to_dict()

            task = self.repository.transition_task(task.task_id, TaskState.RUNNING, plan=plan)
            self.repository.record_step(task.task_id, 0, plan.action_type.value, f"{task.request_id}:1:0", StepState.RUNNING)
            result, partial = self._execute(task, plan)
            state = TaskState.PARTIALLY_COMPLETED if partial else TaskState.COMPLETED
            task = self.repository.transition_task(task.task_id, state, plan=plan, safe_result=result)
            provider_reference = str(result.get("provider_reference") or "")
            self.repository.record_step(
                task.task_id, 0, plan.action_type.value, f"{task.request_id}:1:0",
                StepState.COMPLETED, provider_reference=provider_reference, details=result,
            )
            self.repository.record_audit(AuditEvent(
                task_id=task.task_id, actor_id=task.user_id, action=plan.action_type.value,
                result=state.value, details=result, provider_reference=provider_reference,
            ))
            self._emit(task, "completed", str(result.get("user_safe_summary", self._message(task.language, "completed"))), result)
            return task.to_dict()
        except ValueError as exc:
            return self._fail(task_id, str(exc), user_error=True)
        except Exception:
            return self._fail(task_id, "The request could not be completed right now.", user_error=False)

    def _fail(self, task_id: str, message: str, *, user_error: bool) -> dict[str, Any] | None:
        task = self.repository.get_task(task_id)
        if task is None:
            return None
        safe = {"error": message if user_error else self._message(task.language, "failed"), "user_safe_summary": message if user_error else self._message(task.language, "failed")}
        if not task.state.terminal:
            task = self.repository.transition_task(task_id, TaskState.FAILED, safe_result=safe)
            self.repository.record_audit(AuditEvent(task_id=task.task_id, actor_id=task.user_id, action="task", result="failed", details={"reason": safe["error"]}))
            self._emit(task, "failed", safe["user_safe_summary"], safe)
        return task.to_dict()

    def _execute(self, task: TaskRecord, plan: ActionPlan) -> tuple[dict[str, Any], bool]:
        if self.banking_runtime.mode != "mock":
            return self._execute_live(task, plan)
        action = plan.action_type
        params = dict(plan.fields)
        # Planner compatibility values are deliberately normalized here.
        if action in {ActionType.INVESTMENT_ORDER, ActionType.INVEST}:
            return self._invest(task, params), False
        if action in {ActionType.OPEN_SAVINGS_AND_FUND, ActionType.OPEN_SAVINGS}:
            return self._open_savings(task, params)
        if action == ActionType.OWN_ACCOUNT_TRANSFER:
            return self._own_transfer(task, params), False
        if action == ActionType.USER_TRANSFER:
            return self._user_transfer(task, params), False
        if action == ActionType.ADD_BENEFICIARY:
            return self._add_beneficiary(task, params), False
        if action == ActionType.DELETE_BENEFICIARY:
            return self._delete_beneficiary(task, params), False
        if action == ActionType.CREATE_QATTA:
            return self._create_qatta(task, params), False
        if action == ActionType.PAY_QATTA_SHARE:
            return self._pay_qatta_share(task, params), False
        if action == ActionType.MONTHLY_REPORT:
            return self._monthly_report(task, params), False
        if action == ActionType.GIFT_TRANSFER:
            return self._gift_transfer(task, params), False
        if action == ActionType.FINANCIAL_ANALYSIS:
            return self._financial_analysis(task, params), False
        if action == ActionType.LIST_STORE_ITEMS:
            return self._list_store_items(task), False
        if action == ActionType.STORE_PURCHASE:
            return self._store_purchase(task, params), False
        raise ValueError("This request is not supported by the current MVP")

    @staticmethod
    def _money(params: Mapping[str, Any], *, key: str = "amount") -> Money:
        value = params.get(key)
        if value in (None, ""):
            raise ValueError("A positive amount is required")
        return Money.positive(value, str(params.get("currency", "SAR")))

    def _execute_live(self, task: TaskRecord, plan: ActionPlan) -> tuple[dict[str, Any], bool]:
        """Execute only operations covered by the configured banking boundary.

        Brokerage and bank-product actions do not silently fall back to mock
        providers. In-app catalog/Qatta creation remains local by design.
        """
        action = plan.action_type
        params = dict(plan.fields)
        if action == ActionType.OWN_ACCOUNT_TRANSFER:
            return self._live_own_transfer(task, params)
        if action == ActionType.ADD_BENEFICIARY:
            return self._live_add_beneficiary(task, params), False
        if action == ActionType.DELETE_BENEFICIARY:
            return self._live_delete_beneficiary(task, params), False
        if action == ActionType.MONTHLY_REPORT:
            return self._live_monthly_report(task, params), False
        if action == ActionType.FINANCIAL_ANALYSIS:
            return self._live_financial_analysis(task, params), False
        if action == ActionType.LIST_STORE_ITEMS:
            return self._list_store_items(task), False
        if action == ActionType.CREATE_QATTA:
            self._require_live_application_approval(task)
            return self._create_qatta(task, params), False
        unsupported = {
            ActionType.INVESTMENT_ORDER: "Saudi market orders require the separately configured broker provider",
            ActionType.INVEST: "Saudi market orders require the separately configured broker provider",
            ActionType.OPEN_SAVINGS_AND_FUND: "Savings onboarding requires the separately configured bank-product provider",
            ActionType.OPEN_SAVINGS: "Savings onboarding requires the separately configured bank-product provider",
            ActionType.USER_TRANSFER: "This app-user payee is not linked to a verified live bank destination",
            ActionType.GIFT_TRANSFER: "This gift recipient is not linked to a verified live bank destination",
            ActionType.PAY_QATTA_SHARE: "This Qatta payee is not linked to a verified live bank destination",
            ActionType.STORE_PURCHASE: "The live merchant payee is not configured",
        }
        raise ValueError(unsupported.get(action, "This action is not enabled by the selected live provider"))

    def _live_adapter(self):
        adapter = self.banking_runtime.live_adapter
        if adapter is None:
            raise ValueError("The selected live banking provider is not configured")
        return adapter

    @staticmethod
    def _run_live_call(awaitable):
        """Resolve an async provider call from either a worker or ASGI thread."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)
        result: list[Any] = []
        failure: list[BaseException] = []

        def runner() -> None:
            try:
                result.append(asyncio.run(awaitable))
            except BaseException as exc:  # propagate the original provider error
                failure.append(exc)

        thread = threading.Thread(target=runner, daemon=True, name="nafi-live-provider-call")
        thread.start()
        thread.join()
        if failure:
            raise failure[0]
        return result[0]

    @staticmethod
    def _normalize_lookup(value: Any) -> str:
        return re.sub(r"[^\w\u0600-\u06ff]+", "", str(value).casefold())

    @classmethod
    def _provider_value(cls, value: Any, names: set[str]) -> Any:
        normalized_names = {cls._normalize_lookup(name) for name in names}
        if isinstance(value, Mapping):
            for key, item in value.items():
                if cls._normalize_lookup(key) in normalized_names and item not in (None, ""):
                    return item
            for item in value.values():
                found = cls._provider_value(item, names)
                if found not in (None, ""):
                    return found
        elif isinstance(value, list):
            for item in value:
                found = cls._provider_value(item, names)
                if found not in (None, ""):
                    return found
        return None

    @classmethod
    def _provider_records(cls, payload: Mapping[str, Any], names: set[str]) -> list[Mapping[str, Any]]:
        normalized_names = {cls._normalize_lookup(name) for name in names}

        def find(value: Any) -> list[Mapping[str, Any]] | None:
            if not isinstance(value, Mapping):
                return None
            for key, item in value.items():
                if cls._normalize_lookup(key) in normalized_names and isinstance(item, list):
                    return [record for record in item if isinstance(record, Mapping)]
            for item in value.values():
                found = find(item)
                if found is not None:
                    return found
            return None

        return find(payload) or []

    @classmethod
    def _provider_reference(cls, response: Mapping[str, Any], *, required: bool = True) -> str:
        value = cls._provider_value(
            response,
            {"payment_id", "paymentId", "beneficiary_id", "beneficiaryId", "provider_reference", "id"},
        )
        if value in (None, "") and required:
            raise ValueError("The provider response did not include a reconciliation reference")
        return str(value or "")

    @classmethod
    def _provider_status(cls, response: Mapping[str, Any], default: str = "submitted") -> str:
        value = cls._provider_value(response, {"status", "payment_status", "paymentStatus", "state"})
        return str(value or default).strip().lower().replace(" ", "_")

    @staticmethod
    def _mask_provider_reference(value: str) -> str:
        compact = str(value).replace(" ", "")
        if compact.upper().startswith("SA") and len(compact) == 24:
            return mask_iban(compact.upper())
        return f"****{compact[-4:]}" if len(compact) > 4 else "****"

    def _require_live_application_approval(self, task: TaskRecord) -> None:
        if self.settings.approval_mode != "explicit" or not task.application_approval_received:
            raise ValueError("Confirm the exact live action before Nafi sends it to the provider")

    def _require_live_customer_authorization(self) -> None:
        if not self._live_adapter().profile.has_customer_authorization:
            raise ValueError(
                "A customer-bound access token or provider-managed consent context is required"
            )

    def _live_accounts(self) -> list[Mapping[str, Any]]:
        self._require_live_customer_authorization()
        response = self._run_live_call(self._live_adapter().list_accounts())
        accounts = self._provider_records(response, {"account", "accounts"})
        if not accounts:
            raise ValueError("The provider returned no authorized accounts")
        return accounts

    def _resolve_live_account(
        self, accounts: list[Mapping[str, Any]], alias: Any
    ) -> tuple[str, str]:
        query = self._normalize_lookup(alias)
        if not query:
            raise ValueError("A source and destination account are required")
        candidates: list[tuple[str, str, list[str]]] = []
        for account in accounts:
            reference = self._provider_value(
                account, {"account_id", "accountId", "AccountId", "identification", "id"}
            )
            if reference in (None, ""):
                continue
            labels = [
                str(value) for value in (
                    reference,
                    self._provider_value(account, {"name", "nickname", "account_name", "display_name"}),
                    self._provider_value(account, {"iban", "IBAN"}),
                    self._provider_value(account, {"bank", "bank_name", "institution"}),
                ) if value not in (None, "")
            ]
            candidates.append((str(reference), labels[1] if len(labels) > 1 else str(reference), labels))
        exact = [item for item in candidates if query in {self._normalize_lookup(label) for label in item[2]}]
        matches = exact or [
            item for item in candidates
            if any(query in self._normalize_lookup(label) for label in item[2])
        ]
        if len(matches) != 1:
            raise ValueError("The live account reference is missing or ambiguous")
        reference, display, _ = matches[0]
        return reference, display

    def _live_own_transfer(
        self, task: TaskRecord, params: Mapping[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        self._require_live_application_approval(task)
        self._require_live_customer_authorization()
        amount = self._money(params)
        accounts = self._live_accounts()
        source, source_name = self._resolve_live_account(accounts, params.get("source_account"))
        destination, destination_name = self._resolve_live_account(accounts, params.get("destination_account"))
        if source == destination:
            raise ValueError("Source and destination accounts must be different")
        instruction = {
            "debtorAccount": {"schemeName": "AccountId", "identification": source},
            "creditorAccount": {"schemeName": "AccountId", "identification": destination},
            "instructedAmount": amount.to_dict(),
            "remittanceInformation": {
                "reference": task.request_id,
                "description": "Nafi transfer between own accounts",
            },
        }
        response = self._run_live_call(self._live_adapter().initiate_payment(
            instruction,
            idempotency_key=f"{task.request_id}:1:0",
            interaction_id=task.task_id,
        ))
        reference = self._provider_reference(response)
        provider_status = self._provider_status(response)
        settled = provider_status in {"settled", "completed", "executed", "acceptedsettlementcompleted"}
        summary = (
            f"Transferred {amount.amount} {amount.currency} between your accounts."
            if settled else
            f"Submitted {amount.amount} {amount.currency}; provider status is {provider_status}."
        )
        result = {
            "user_safe_summary": summary,
            "provider_reference": reference,
            "transfer": {
                "payment_reference": reference,
                "status": provider_status,
                "source": {"name": source_name, "reference_masked": self._mask_provider_reference(source)},
                "destination": {"name": destination_name, "reference_masked": self._mask_provider_reference(destination)},
                "amount": amount.to_dict(),
            },
            "is_gift": False,
        }
        return result, not settled

    def _live_add_beneficiary(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_live_application_approval(task)
        iban = normalize_saudi_iban(str(params.get("iban", "")))
        name = sanitize_user_text(str(params.get("display_name") or "Beneficiary"), max_length=80)
        provider_reference = ""
        sync_status = "not_supported"
        if self._live_adapter().profile.beneficiary_write_enabled:
            self._require_live_customer_authorization()
            response = self._run_live_call(self._live_adapter().add_beneficiary(
                {"name": name, "iban": iban},
                idempotency_key=f"{task.request_id}:1:0",
                interaction_id=task.task_id,
            ))
            provider_reference = self._provider_reference(response)
            sync_status = self._provider_status(response, "submitted")
        beneficiary, created = self.repository.add_beneficiary(
            task.user_id,
            iban,
            name,
            verification_state="provider_synced" if provider_reference else "local",
            provider_reference=provider_reference,
        )
        return {
            "user_safe_summary": f"{'Added' if created else 'Found'} beneficiary {name}.",
            "provider_reference": provider_reference,
            "beneficiary": {
                "beneficiary_id": beneficiary["beneficiary_id"],
                "display_name": beneficiary["display_name"],
                "iban_masked": mask_iban(iban),
                "created": created,
                "provider_sync_status": sync_status,
            },
        }

    def _live_delete_beneficiary(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        self._require_live_application_approval(task)
        raw = str(params.get("beneficiary") or params.get("iban") or "")
        is_iban = raw.upper().replace(" ", "").startswith("SA")
        normalized_iban = normalize_saudi_iban(raw) if is_iban else None
        beneficiary = self.repository.get_beneficiary(
            task.user_id,
            iban=normalized_iban if is_iban else None,
            beneficiary_id=None if is_iban else raw,
        )
        if not beneficiary:
            return {"user_safe_summary": "No active beneficiary matched that reference.", "deleted": False}
        provider_reference = str(beneficiary.get("provider_reference") or beneficiary.get("iban") or "")
        sync_status = "not_supported"
        if self._live_adapter().profile.beneficiary_write_enabled:
            self._require_live_customer_authorization()
            response = self._run_live_call(self._live_adapter().delete_beneficiary(
                provider_reference,
                idempotency_key=f"{task.request_id}:1:0",
                interaction_id=task.task_id,
            ))
            sync_status = self._provider_status(response, "deleted")
        removed = self.repository.delete_beneficiary(
            task.user_id,
            iban=normalized_iban if is_iban else None,
            beneficiary_id=None if is_iban else raw,
        )
        return {
            "user_safe_summary": "Beneficiary deleted." if removed else "No active beneficiary matched that reference.",
            "provider_reference": provider_reference if sync_status != "not_supported" else "",
            "provider_sync_status": sync_status,
            "deleted": removed,
        }

    @classmethod
    def _provider_decimal(cls, value: Any) -> Decimal | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (str, int, float, Decimal)):
            try:
                return Decimal(str(value).replace(",", ""))
            except Exception:
                return None
        if isinstance(value, Mapping):
            preferred = cls._provider_value(value, {"amount", "value", "balance"})
            if preferred is not None and preferred is not value:
                parsed = cls._provider_decimal(preferred)
                if parsed is not None:
                    return parsed
            for item in value.values():
                parsed = cls._provider_decimal(item)
                if parsed is not None:
                    return parsed
        if isinstance(value, list):
            for item in value:
                parsed = cls._provider_decimal(item)
                if parsed is not None:
                    return parsed
        return None

    @staticmethod
    def _report_month(value: Any) -> str:
        requested = str(value or "current_month")
        now = datetime.now(UTC)
        if requested == "current_month":
            return now.strftime("%Y-%m")
        if requested == "previous_month":
            first = now.replace(day=1)
            return (first - timedelta(days=1)).strftime("%Y-%m")
        if re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", requested):
            return requested
        raise ValueError("Report month must use YYYY-MM")

    def _live_financial_snapshot(self, month: str) -> dict[str, Any]:
        self._require_live_customer_authorization()
        adapter = self._live_adapter()

        async def load() -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], Decimal]:
            account_payload = await adapter.list_accounts()
            accounts = self._provider_records(account_payload, {"account", "accounts"})
            if not accounts:
                raise ValueError("The provider returned no authorized accounts")
            transactions: list[Mapping[str, Any]] = []
            closing_balance = Decimal("0")
            for account in accounts:
                account_id = self._provider_value(
                    account, {"account_id", "accountId", "AccountId", "identification", "id"}
                )
                if account_id in (None, ""):
                    raise ValueError("The provider account response is missing an account reference")
                embedded_balance = self._provider_value(
                    account, {"available_balance", "current_balance", "balance"}
                )
                balance = self._provider_decimal(embedded_balance)
                if balance is None:
                    balance_payload = await adapter.get_balances(str(account_id))
                    balance_records = self._provider_records(balance_payload, {"balance", "balances"})
                    balance_source: Any = balance_records[0] if balance_records else balance_payload
                    balance = self._provider_decimal(balance_source)
                if balance is None:
                    raise ValueError("The provider balance response could not be normalized")
                closing_balance += balance
                transaction_payload = await adapter.list_transactions(str(account_id))
                transactions.extend(
                    self._provider_records(transaction_payload, {"transaction", "transactions"})
                )
            return accounts, transactions, closing_balance

        accounts, raw_transactions, closing_balance = self._run_live_call(load())
        normalized: list[dict[str, Any]] = []
        for transaction in raw_transactions:
            occurred_at = str(self._provider_value(
                transaction,
                {"booking_date_time", "bookingDateTime", "booking_date", "value_date", "date", "occurred_at"},
            ) or "")
            if not occurred_at:
                raise ValueError("A provider transaction date could not be normalized")
            if occurred_at and not occurred_at.startswith(month):
                continue
            amount_source = self._provider_value(
                transaction, {"transaction_amount", "transactionAmount", "amount"}
            )
            amount = self._provider_decimal(amount_source)
            if amount is None:
                raise ValueError("A provider transaction amount could not be normalized")
            direction = str(self._provider_value(
                transaction, {"credit_debit_indicator", "creditDebitIndicator", "direction", "type"}
            ) or "").casefold()
            if "debit" in direction or direction in {"dbit", "out", "outgoing"}:
                amount = -abs(amount)
            elif "credit" in direction or direction in {"crit", "in", "incoming"}:
                amount = abs(amount)
            currency = str(self._provider_value(transaction, {"currency"}) or "SAR").upper()
            if currency != "SAR":
                raise ValueError("The live report currently requires all provider transactions in SAR")
            category = sanitize_user_text(str(self._provider_value(
                transaction, {"category", "merchant_category", "transaction_category", "type"}
            ) or "other"), max_length=60).lower()
            normalized.append({"amount": amount, "category": category})
        income = sum((item["amount"] for item in normalized if item["amount"] > 0), Decimal("0"))
        expenses = -sum((item["amount"] for item in normalized if item["amount"] < 0), Decimal("0"))
        categories: dict[str, Decimal] = {}
        for item in normalized:
            if item["amount"] < 0:
                categories[item["category"]] = categories.get(item["category"], Decimal("0")) + -item["amount"]
        net = income - expenses
        return {
            "month": month,
            "income": Money(income).to_dict(),
            "expenses": Money(expenses).to_dict(),
            "net_cashflow": {"amount": format(net, ".2f"), "currency": "SAR"},
            "savings_rate": format((net / income * Decimal("100")) if income else Decimal("0"), ".2f"),
            "category_totals": {
                category: Money(value).to_dict() for category, value in sorted(categories.items())
            },
            "closing_balance": {"amount": format(closing_balance, ".2f"), "currency": "SAR"},
            "transaction_count": len(normalized),
            "account_count": len(accounts),
            "source": "live_saudi_open_banking",
        }

    def _live_monthly_report(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        month = self._report_month(params.get("month"))
        report = self._live_financial_snapshot(month)
        return {
            "user_safe_summary": f"Prepared your live monthly financial report for {month}.",
            "report": report,
        }

    def _live_financial_analysis(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        month = self._report_month(params.get("month"))
        report = self._live_financial_snapshot(month)
        cash = Decimal(report["closing_balance"]["amount"])
        expenses = Decimal(report["expenses"]["amount"])
        analysis = {
            "cash_balance": report["closing_balance"],
            "monthly_expenses": report["expenses"],
            "monthly_income": report["income"],
            "savings_rate_percent": report["savings_rate"],
            "estimated_months_of_runway": "not_available" if expenses <= 0 else format(cash / expenses, ".1f"),
            "largest_spend_categories": report["category_totals"],
            "portfolio": [],
            "data_source": "live_saudi_open_banking",
            "disclaimer": "Informational analysis only; it is not investment, credit, or legal advice.",
        }
        return {
            "user_safe_summary": "Prepared your read-only analysis from live authorized account data.",
            "analysis": analysis,
            "read_only": True,
        }

    def _own_transfer(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        amount = self._money(params)
        result = self.backend.transfer(task.user_id, str(params.get("source_account", "")), str(params.get("destination_account", "")), amount, description="Transfer between your accounts")
        return {"user_safe_summary": f"Transferred {amount.amount} {amount.currency} between your accounts.", "transfer": result, "is_gift": False}

    def _user_transfer(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        amount = self._money(params)
        recipient_alias = str(params.get("recipient", ""))
        recipient_user_id = self.backend.resolve_user(recipient_alias)
        if recipient_user_id == task.user_id:
            raise ValueError("Use an account transfer to move money between your own accounts")
        result = self.backend.transfer(task.user_id, params.get("source_account"), "", amount, description="Transfer to an app user", recipient_user_id=recipient_user_id)
        return {"user_safe_summary": f"Transferred {amount.amount} {amount.currency} to {recipient_alias}.", "transfer": result, "recipient": recipient_alias, "is_gift": False}

    def _add_beneficiary(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        iban = normalize_saudi_iban(str(params.get("iban", "")))
        name = sanitize_user_text(str(params.get("display_name") or "Beneficiary"), max_length=80)
        beneficiary, created = self.repository.add_beneficiary(task.user_id, iban, name)
        return {"user_safe_summary": f"{'Added' if created else 'Found'} beneficiary {name}.", "beneficiary": {"beneficiary_id": beneficiary["beneficiary_id"], "display_name": beneficiary["display_name"], "iban_masked": mask_iban(iban), "created": created}}

    def _delete_beneficiary(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        raw = str(params.get("beneficiary") or params.get("iban") or "")
        if raw.upper().replace(" ", "").startswith("SA"):
            removed = self.repository.delete_beneficiary(task.user_id, iban=normalize_saudi_iban(raw))
        else:
            removed = self.repository.delete_beneficiary(task.user_id, beneficiary_id=raw)
        return {"user_safe_summary": "Beneficiary deleted." if removed else "No active beneficiary matched that reference.", "deleted": removed}

    def _invest(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        symbol = str(params.get("symbol", ""))
        quantity = int(params["quantity"]) if params.get("quantity") else None
        amount = self._money(params) if params.get("amount") else None
        side = str(params.get("side", "buy"))
        order = self.backend.place_order(task.user_id, params.get("source_account"), symbol, amount=amount, quantity=quantity, side=side)
        return {"user_safe_summary": f"{side.title()} order for {order['quantity']} {order['symbol']} shares filled.", "order": order, "portfolio": self.backend.portfolio(task.user_id), "informational_only": True}

    def _create_qatta(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        total = self._money(params)
        aliases = list(params.get("participants") or [])
        if not aliases:
            raise ValueError("At least two Qatta participants are required")
        participants: list[str] = []
        for alias in aliases:
            user_id = self.backend.resolve_user(str(alias))
            if user_id == task.user_id:
                continue
            if user_id not in participants:
                participants.append(user_id)
        if not participants:
            raise ValueError("Qatta needs at least one other participant")
        minor_total = total.minor_units
        base, remainder = divmod(minor_total, len(participants))
        shares = {participant: base + (1 if index < remainder else 0) for index, participant in enumerate(sorted(participants))}
        qatta_id = self.repository.create_qatta(task.user_id, total, sanitize_user_text(str(params.get("purpose", "Shared payment")), max_length=120), shares)
        qatta = self.repository.get_qatta(qatta_id)
        return {"user_safe_summary": f"Created Qatta for {total.amount} {total.currency} across {len(participants)} participants.", "qatta": qatta}

    def _pay_qatta_share(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        qatta = self.repository.get_qatta(str(params.get("qatta_id", "")))
        if not qatta:
            raise ValueError("Qatta was not found")
        share = next((item for item in qatta["shares"] if item["participant_id"] == task.user_id), None)
        if not share:
            raise ValueError("You are not a participant in this Qatta")
        if share["state"] == "paid":
            return {"user_safe_summary": "Your Qatta share is already paid.", "qatta": qatta}
        amount = Money.from_minor_units(int(share["amount_minor"]), str(qatta["currency"]))
        transfer = self.backend.transfer(task.user_id, params.get("source_account"), "", amount, description=f"Qatta: {qatta['purpose']}", recipient_user_id=str(qatta["owner_id"]))
        self.repository.settle_qatta_share(str(qatta["qatta_id"]), task.user_id, str(transfer["payment_reference"]))
        return {"user_safe_summary": f"Paid your Qatta share of {amount.amount} {amount.currency}.", "qatta": self.repository.get_qatta(str(qatta["qatta_id"])), "transfer": transfer}

    def _monthly_report(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        month = str(params.get("month") or "current_month")
        transactions = self.backend.transactions_for_month(task.user_id, month)
        if month.startswith("--"):
            transactions = [item for item in transactions if item["occurred_at"][5:7] == month[-2:]]
        income = sum((Decimal(item["amount"]) for item in transactions if Decimal(item["amount"]) > 0), Decimal("0"))
        expenses = -sum((Decimal(item["amount"]) for item in transactions if Decimal(item["amount"]) < 0), Decimal("0"))
        categories: dict[str, Decimal] = {}
        for item in transactions:
            amount = Decimal(item["amount"])
            if amount < 0:
                categories[item["category"]] = categories.get(item["category"], Decimal("0")) + -amount
        accounts = self.backend.list_accounts(task.user_id)
        closing = sum((Decimal(account["balance"]["amount"]) for account in accounts), Decimal("0"))
        # Net cashflow is intentionally signed. ``Money`` models amounts that can
        # be moved and therefore rejects negatives, so using it here made a
        # perfectly valid loss-making month fail the entire report.
        net_cashflow = {"amount": format(income - expenses, ".2f"), "currency": "SAR"}
        report = {"month": month, "income": Money(income).to_dict(), "expenses": Money(expenses).to_dict(), "net_cashflow": net_cashflow, "savings_rate": format(((income - expenses) / income * Decimal("100")) if income else Decimal("0"), ".2f"), "category_totals": {category: Money(value).to_dict() for category, value in sorted(categories.items())}, "closing_balance": Money(closing).to_dict(), "transaction_count": len(transactions)}
        return {"user_safe_summary": f"Prepared your monthly financial report for {month}.", "report": report}

    def _open_savings(self, task: TaskRecord, params: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        account = self.backend.create_savings_account(task.user_id)
        result: dict[str, Any] = {"savings_account": account.public(), "account_created": True}
        try:
            amount = self._money(params)
            transfer = self.backend.transfer(task.user_id, params.get("source_account"), account.account_id, amount, description="Initial savings funding")
            result.update({"funded": True, "transfer": transfer, "user_safe_summary": f"Created and funded your savings account with {amount.amount} {amount.currency}."})
            return result, False
        except ValueError as exc:
            result.update({"funded": False, "funding_error": str(exc), "user_safe_summary": "Savings account created, but the initial funding could not be completed."})
            return result, True

    def _gift_transfer(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        transfer_result = self._user_transfer(task, params)
        recipient = str(params.get("recipient"))
        message = sanitize_user_text(str(params.get("gift_message", "")), max_length=self.settings.max_gift_message_length)
        gift_id = self.repository.create_gift(task.task_id, task.user_id, self.backend.resolve_user(recipient), str(transfer_result["transfer"]["payment_reference"]), message=message, occasion=sanitize_user_text(str(params.get("occasion", "")), max_length=80), theme=sanitize_user_text(str(params.get("theme", "")), max_length=40))
        transfer_result.update({"is_gift": True, "gift_id": gift_id, "gift_message": message, "user_safe_summary": f"Gift transfer of {self._money(params).amount} SAR sent to {recipient}."})
        return transfer_result

    def _financial_analysis(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        report = self._monthly_report(task, {"month": params.get("month", "current_month")})["report"]
        accounts = self.backend.list_accounts(task.user_id)
        portfolio = self.backend.portfolio(task.user_id)
        cash = sum((Decimal(account["balance"]["amount"]) for account in accounts), Decimal("0"))
        expenses = Decimal(report["expenses"]["amount"])
        runway = "not_available" if expenses <= 0 else format(cash / expenses, ".1f")
        analysis = {"cash_balance": Money(cash).to_dict(), "monthly_expenses": report["expenses"], "monthly_income": report["income"], "savings_rate_percent": report["savings_rate"], "estimated_months_of_runway": runway, "largest_spend_categories": report["category_totals"], "portfolio": portfolio, "disclaimer": "Informational analysis only; it is not investment, credit, or legal advice."}
        return {"user_safe_summary": "Prepared your read-only financial analysis.", "analysis": analysis, "read_only": True}

    def _list_store_items(self, task: TaskRecord) -> dict[str, Any]:
        items = self.repository.list_store_items()
        return {"user_safe_summary": f"Found {len(items)} items in the store.", "items": items}

    def _store_purchase(self, task: TaskRecord, params: Mapping[str, Any]) -> dict[str, Any]:
        items = self.repository.list_store_items()
        sku = str(params.get("sku", "")).upper()
        if not sku and params.get("item"):
            item_name = str(params["item"]).lower()
            arabic_items = {
                "مجموعة القهوة السعودية": "COFFEE-01",
                "طقم القهوة السعودية": "COFFEE-01",
                "كوب نافع": "MUG-01",
                "بطاقة هدية رقمية": "CARD-01",
                "بطاقة هدية": "CARD-01",
            }
            translated_sku = next(
                (item_sku for alias, item_sku in arabic_items.items() if alias in item_name),
                "",
            )
            candidate = next(
                (item for item in items if item["sku"] == translated_sku or item_name in item["name"].lower()),
                None,
            )
            sku = str(candidate["sku"]) if candidate else ""
        item = next((candidate for candidate in items if candidate["sku"] == sku), None)
        if not item:
            raise ValueError("Store item was not found or is unavailable")
        quantity = int(params.get("quantity", 1))
        if quantity <= 0:
            raise ValueError("Store quantity must be positive")
        order_id = str(uuid4())
        expires_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        if not self.repository.reserve_inventory(order_id, sku, quantity, expires_at):
            raise ValueError("This item is no longer available in the requested quantity")
        order = self.repository.create_order(order_id, task.user_id, sku, quantity)
        amount = Money.from_minor_units(int(order["total_minor"]), str(order["currency"]))
        try:
            source_alias = params.get("source_account")
            if str(source_alias or "").strip().lower() in {"store", "the store", "المتجر"}:
                source_alias = None
            payment = self.backend.transfer(task.user_id, source_alias, "store-merchant", amount, description=f"Store purchase: {item['name']}")
            self.repository.finalize_order(order_id, str(payment["payment_reference"]), paid=True)
            return {"user_safe_summary": f"Purchased {quantity} × {item['name']} for {amount.amount} {amount.currency}.", "order": {**order, "state": "paid", "payment_reference": payment["payment_reference"], "total": amount.to_dict()}, "payment": payment}
        except ValueError:
            self.repository.finalize_order(order_id, "", paid=False)
            raise

    def get_task(self, task_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        task = self.repository.get_task_for_user(task_id, user_id) if user_id else self.repository.get_task(task_id)
        if task is None:
            return None
        result = task.to_dict()
        result["audit"] = self.repository.list_audit(task_id)
        return result

    def capabilities(self) -> dict[str, Any]:
        mock = self.banking_runtime.mode == "mock"
        provider_capabilities = self.banking_runtime.capabilities()
        profile = self.banking_runtime.live_adapter.profile if self.banking_runtime.live_adapter else None
        customer_authorized = bool(profile and profile.has_customer_authorization)
        live_reads = bool(not mock and customer_authorized and provider_capabilities["account_information"])
        live_payments = bool(
            not mock and customer_authorized and provider_capabilities["payment_initiation"]
            and self.settings.approval_mode == "explicit"
        )
        return {"mode": self.banking_runtime.mode, "provider": self.banking_runtime.provider_name,
                "provider_transport_ready": self.banking_runtime.configured,
                "customer_authorization_configured": customer_authorized,
                "ready_for_live_money": live_payments,
                "provider_capabilities": provider_capabilities, "capabilities": {
            "own_account_transfer": mock or live_payments, "user_transfer": mock,
            "beneficiary_management": True,
            "live_beneficiary_sync": bool(not mock and provider_capabilities["beneficiary_write"]),
            "saudi_market_investing": mock, "qatta": True, "monthly_report": mock or live_reads,
            "savings_account": mock, "gift_transfer": mock, "financial_analysis": mock or live_reads,
            "store": True, "live_saudi_open_banking": not mock,
        }, "notes": ["Mock mode uses seeded no-key data." if mock else
                       "Live mutations require a persisted exact application approval; customer consent/SCA remains provider-managed."]}

    def readiness(self) -> dict[str, Any]:
        """Configuration readiness only; it deliberately performs no bank call."""
        return self.banking_runtime.readiness()

    def _emit(self, task: TaskRecord, event_type: str, summary: str, details: Mapping[str, Any]) -> None:
        payload = {"task_id": task.task_id, "request_id": task.request_id, "session_id": task.session_id, "event_type": event_type, "user_safe_summary": summary, "details": dict(details), "created_at": datetime.now(UTC).isoformat(), "language": task.language}
        destination = self.settings.interaction_callback_url
        self.repository.enqueue_event(task.task_id, payload, destination, f"{task.task_id}:{event_type}:{task.version}")
        if not destination:
            return
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.settings.interaction_webhook_secret:
            headers["X-Agentic-Webhook-Secret"] = self.settings.interaction_webhook_secret
        request = urllib.request.Request(destination, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=3):
                pass
        except (urllib.error.URLError, TimeoutError):
            # The event remains persisted in the outbox; a future retry worker
            # can deliver it without changing task execution semantics.
            return

    @staticmethod
    def _message(language: str, key: str) -> str:
        ar = language == "ar"
        messages = {
            "accepted": ("I'll check that now.", "تمام، سأتحقق من ذلك الآن."),
            "planning": ("I’m preparing your request.", "أقوم بتجهيز طلبك الآن."),
            "input_needed": ("I need one more detail to continue.", "أحتاج إلى معلومة إضافية للمتابعة."),
            "approval_required": (
                "Please confirm this exact demo financial action before I continue.",
                "يرجى تأكيد هذه العملية المالية التجريبية بشكل صريح قبل المتابعة.",
            ),
            "completed": ("Done.", "تم."),
            "failed": ("I could not complete that request right now.", "لم أتمكن من إكمال الطلب الآن."),
        }
        return messages[key][1 if ar else 0]
