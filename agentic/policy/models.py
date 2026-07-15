"""Structured intent and risk models shared by classification and policy."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Intent(StrEnum):
    ACCOUNT_INFORMATION = "account_information"
    TRANSACTION_SEARCH = "transaction_search"
    FINANCIAL_CALCULATION = "financial_calculation"
    MONEY_TRANSFER = "money_transfer"
    BILL_PAYMENT = "bill_payment"
    BENEFICIARY_MANAGEMENT = "beneficiary_management"
    INVESTMENT_RESEARCH = "investment_research"
    INVESTMENT_BUY = "investment_buy"
    INVESTMENT_SELL = "investment_sell"
    PORTFOLIO_MODIFICATION = "portfolio_modification"
    PREFERENCE_MODIFICATION = "preference_modification"
    CLARIFICATION = "clarification"
    ACCESS_OTHER_USER = "access_other_user"
    CREDENTIAL_THEFT = "credential_theft"
    FRAUD = "fraud"
    MONEY_LAUNDERING = "money_laundering"
    MARKET_MANIPULATION = "market_manipulation"
    COMPLIANCE_BYPASS = "compliance_bypass"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    related_intents: tuple[Intent, ...] = Field(default=(), max_length=4)
    confidence: float = Field(ge=0, le=1)
    rationale_code: str = Field(max_length=100)
    required_information: tuple[str, ...] = ()

    @model_validator(mode="after")
    def related_intents_are_distinct(self) -> "IntentClassification":
        if self.intent in self.related_intents:
            raise ValueError("related_intents must not repeat the primary intent")
        if len(set(self.related_intents)) != len(self.related_intents):
            raise ValueError("related_intents must be unique")
        if Intent.UNKNOWN in self.related_intents:
            raise ValueError("UNKNOWN can only be the primary intent")
        return self

    @property
    def all_intents(self) -> tuple[Intent, ...]:
        """Return the primary and explicitly requested compound intents."""

        return (self.intent, *self.related_intents)


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: RiskLevel
    reason_codes: tuple[str, ...] = ()
    requires_confirmation: bool = False
    contains_sensitive_data: bool = False
