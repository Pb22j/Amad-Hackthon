"""Closed, serialisable domain contracts for the financial agent.

The planner may only return :class:`ActionPlan`; executors resolve every alias
and revalidate values against server-authoritative state before a side effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class ActionType(str, Enum):
    OWN_ACCOUNT_TRANSFER = "own_account_transfer"
    USER_TRANSFER = "user_transfer"
    ADD_BENEFICIARY = "add_beneficiary"
    DELETE_BENEFICIARY = "delete_beneficiary"
    INVESTMENT_ORDER = "investment_order"
    # Kept for wire/planner compatibility with the initial MVP vocabulary.
    # Executors should normalize both investment spellings to the same tool.
    INVEST = "invest"
    CREATE_QATTA = "create_qatta"
    PAY_QATTA_SHARE = "pay_qatta_share"
    MONTHLY_REPORT = "monthly_report"
    OPEN_SAVINGS_AND_FUND = "open_savings_and_fund"
    OPEN_SAVINGS = "open_savings"
    GIFT_TRANSFER = "gift_transfer"
    FINANCIAL_ANALYSIS = "financial_analysis"
    LIST_STORE_ITEMS = "list_store_items"
    STORE_PURCHASE = "store_purchase"
    NEED_INPUT = "need_input"

    @property
    def is_mutation(self) -> bool:
        return self not in {
            ActionType.MONTHLY_REPORT,
            ActionType.FINANCIAL_ANALYSIS,
            ActionType.LIST_STORE_ITEMS,
            ActionType.NEED_INPUT,
        }


class TaskState(str, Enum):
    ACCEPTED = "accepted"
    PLANNING = "planning"
    INPUT_NEEDED = "input_needed"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_BANK_AUTHORIZATION = "awaiting_bank_authorization"
    RUNNING = "running"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.COMPLETED, self.PARTIALLY_COMPLETED, self.FAILED, self.CANCELLED}


class StepState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class SplitMode(str, Enum):
    EQUAL = "equal"
    EXACT = "exact"
    PERCENTAGE = "percentage"


_CURRENCY_MINOR_DIGITS = {"SAR": 2, "USD": 2, "EUR": 2, "KWD": 3, "JPY": 0}


@dataclass(frozen=True, slots=True)
class Money:
    """A non-negative monetary amount represented exactly with ``Decimal``."""

    amount: Decimal
    currency: str = "SAR"

    def __post_init__(self) -> None:
        try:
            amount = self.amount if isinstance(self.amount, Decimal) else Decimal(str(self.amount))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("money amount must be a decimal number") from exc
        currency = self.currency.upper().strip()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter ISO code")
        if not amount.is_finite() or amount < 0:
            raise ValueError("money amount must be a finite non-negative value")
        places = _CURRENCY_MINOR_DIGITS.get(currency, 2)
        quantized = amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        if quantized != amount:
            raise ValueError(f"{currency} supports at most {places} decimal places")
        object.__setattr__(self, "amount", quantized)
        object.__setattr__(self, "currency", currency)

    @classmethod
    def positive(cls, amount: Decimal | str | int, currency: str = "SAR") -> "Money":
        money = cls(Decimal(str(amount)), currency)
        if money.amount <= 0:
            raise ValueError("money amount must be positive")
        return money

    @property
    def minor_units(self) -> int:
        digits = _CURRENCY_MINOR_DIGITS.get(self.currency, 2)
        return int(self.amount.scaleb(digits))

    @classmethod
    def from_minor_units(cls, minor_units: int, currency: str = "SAR") -> "Money":
        if minor_units < 0:
            raise ValueError("minor units must be non-negative")
        digits = _CURRENCY_MINOR_DIGITS.get(currency.upper(), 2)
        return cls(Decimal(minor_units).scaleb(-digits), currency)

    def to_dict(self) -> dict[str, str]:
        return {"amount": format(self.amount, "f"), "currency": self.currency}


def _json_value(value: Any) -> Any:
    if isinstance(value, Money):
        return value.to_dict()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True, init=False)
class ActionPlan:
    """A strictly bounded, untrusted action proposal from a planner."""

    action_type: ActionType
    fields: Mapping[str, Any]
    confidence: float
    missing_fields: tuple[str, ...]
    evidence: tuple[str, ...]
    schema_version: str
    user_message: str

    def __init__(
        self,
        action_type: ActionType | str | None = None,
        fields: Mapping[str, Any] | None = None,
        confidence: float = 1.0,
        missing_fields: tuple[str, ...] | list[str] = (),
        evidence: tuple[str, ...] | list[str] = (),
        schema_version: str = "1",
        user_message: str = "",
        *,
        # ``action``/``parameters`` preserve compatibility with the initial
        # planner contract while action_type/fields remains the canonical API.
        action: ActionType | str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        selected_action = action_type if action_type is not None else action
        if selected_action is None:
            raise TypeError("ActionPlan requires action_type (or action)")
        if action_type is not None and action is not None and action_type != action:
            raise ValueError("action and action_type must match when both are supplied")
        selected_fields = fields if fields is not None else parameters
        if fields is not None and parameters is not None and dict(fields) != dict(parameters):
            raise ValueError("fields and parameters must match when both are supplied")
        normalized_action = selected_action if isinstance(selected_action, ActionType) else ActionType(str(selected_action))
        normalized_fields = dict(selected_fields or {})
        normalized_missing = tuple(str(item) for item in missing_fields)
        if not 0 <= confidence <= 1:
            raise ValueError("plan confidence must be between 0 and 1")
        if normalized_action == ActionType.NEED_INPUT and not normalized_missing:
            raise ValueError("need_input plans require at least one missing field")
        if normalized_action != ActionType.NEED_INPUT and normalized_missing:
            # A partial mutation must explicitly be a need-input plan, avoiding
            # executors accidentally treating partially filled data as valid.
            raise ValueError("only need_input plans may contain missing fields")
        object.__setattr__(self, "action_type", normalized_action)
        object.__setattr__(self, "fields", normalized_fields)
        object.__setattr__(self, "confidence", float(confidence))
        object.__setattr__(self, "missing_fields", normalized_missing)
        object.__setattr__(self, "evidence", tuple(str(item) for item in evidence))
        object.__setattr__(self, "schema_version", str(schema_version))
        object.__setattr__(self, "user_message", str(user_message))

    @property
    def action(self) -> ActionType:
        """Compatibility alias for early workflow/planner implementations."""
        return self.action_type

    @property
    def parameters(self) -> Mapping[str, Any]:
        """Compatibility alias for early workflow/planner implementations."""
        return self.fields

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "schema_version": self.schema_version,
            "fields": _json_value(self.fields),
            "confidence": self.confidence,
            "missing_fields": list(self.missing_fields),
            "evidence": list(self.evidence),
            "user_message": self.user_message,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ActionPlan":
        return cls(
            action_type=ActionType(str(value["action_type"])),
            schema_version=str(value.get("schema_version", "1")),
            fields=dict(value.get("fields", {})),
            confidence=float(value.get("confidence", 1.0)),
            missing_fields=tuple(str(item) for item in value.get("missing_fields", ())),
            evidence=tuple(str(item) for item in value.get("evidence", ())),
            user_message=str(value.get("user_message", "")),
        )


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    request_id: str
    session_id: str
    user_id: str
    language: str
    natural_language_request: str
    application_approval_received: bool = False
    state: TaskState = TaskState.ACCEPTED
    action_type: ActionType | None = None
    plan: ActionPlan | None = None
    safe_result: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    version: int = 0

    @classmethod
    def new(
        cls, *, request_id: str, session_id: str, user_id: str, language: str,
        natural_language_request: str, application_approval_received: bool = False,
    ) -> "TaskRecord":
        return cls(
            task_id=str(uuid4()), request_id=request_id, session_id=session_id,
            user_id=user_id, language=language, natural_language_request=natural_language_request,
            application_approval_received=application_approval_received,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "language": self.language,
            "natural_language_request": self.natural_language_request,
            "application_approval_received": self.application_approval_received,
            "state": self.state.value,
            "action_type": self.action_type.value if self.action_type else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "safe_result": _json_value(self.safe_result),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class AuditEvent:
    task_id: str
    action: str
    result: str
    actor_id: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)
    provider_reference: str = ""
    created_at: str = field(default_factory=utc_now_iso)
