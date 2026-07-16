"""Strict schemas describing tool risk and the trusted result envelope."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolRisk(StrEnum):
    """Risk class used to select authorization, retry, and audit behavior."""

    READ = "read"
    SENSITIVE_READ = "sensitive_read"
    WRITE = "write"
    FINANCIAL_ACTION = "financial_action"


class ToolMetadata(BaseModel):
    """Agent-owned security policy attached to one stable external tool name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    risk: ToolRisk
    intents: frozenset[str] = frozenset()
    explicit_user_fields: frozenset[str] = frozenset()
    required_scopes: frozenset[str] = frozenset()
    requires_confirmation: bool = False
    requires_receipt: bool = False
    requires_owner_metadata: bool = True
    idempotent: bool = False
    max_calls_per_task: int = Field(default=5, ge=1, le=100)

    @model_validator(mode="after")
    def financial_actions_are_always_gated(self) -> "ToolMetadata":
        if self.risk == ToolRisk.FINANCIAL_ACTION and not self.requires_confirmation:
            raise ValueError("financial_action tools must require confirmation and OTP")
        if self.risk == ToolRisk.FINANCIAL_ACTION and not self.requires_receipt:
            raise ValueError("financial_action tools must require an authoritative receipt")
        return self


class ToolResult(BaseModel):
    """Normalized result every teammate-owned tool must return."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed", "pending", "unknown"]
    summary: str = Field(min_length=1, max_length=1000)
    data: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None
    tenant_id: str | None = None
    receipt_id: str | None = None
    operation_id: str | None = None
    error_code: str | None = None
