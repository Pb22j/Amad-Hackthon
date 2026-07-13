from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "partially_completed", "rejected", "failed"]
    summary: str = Field(min_length=1, max_length=2000)
    actions: list[str] = Field(default_factory=list, max_length=10)
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list, max_length=5)
    receipt_ids: list[str] = Field(default_factory=list, max_length=20)
    needs_follow_up: bool = False

    @model_validator(mode="after")
    def completed_financial_actions_have_receipts(self) -> "AgentReport":
        if self.status == "completed" and self.result.get("receipt_required"):
            if not self.receipt_ids:
                raise ValueError("completed financial action requires an authoritative receipt")
        self.result.pop("receipt_required", None)
        return self


class ActionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    status: Literal["completed", "failed", "pending", "unknown"]
    summary: str
    receipt_id: str | None = None
    operation_id: str | None = None
