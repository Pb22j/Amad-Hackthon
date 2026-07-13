from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolRisk(StrEnum):
    READ = "read"
    SENSITIVE_READ = "sensitive_read"
    WRITE = "write"
    FINANCIAL_ACTION = "financial_action"


class ToolMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    risk: ToolRisk
    required_scopes: frozenset[str] = frozenset()
    requires_confirmation: bool = False
    requires_receipt: bool = False
    requires_owner_metadata: bool = True
    idempotent: bool = False
    max_calls_per_task: int = Field(default=5, ge=1, le=100)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed", "pending", "unknown"]
    summary: str = Field(min_length=1, max_length=1000)
    data: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = None
    tenant_id: str | None = None
    receipt_id: str | None = None
    operation_id: str | None = None
    error_code: str | None = None

