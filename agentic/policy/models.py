from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


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
    confidence: float = Field(ge=0, le=1)
    rationale_code: str = Field(max_length=100)
    required_information: tuple[str, ...] = ()


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: RiskLevel
    reason_codes: tuple[str, ...] = ()
    requires_confirmation: bool = False
    contains_sensitive_data: bool = False

