from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from agentic.agent.report import ActionReceipt


class FinancialAgentState(TypedDict, total=False):
    task_id: str
    request_id: str
    session_id: str
    user_id: str
    tenant_id: str
    language: str
    # Wrapped in an object so the PostgreSQL checkpointer sends it through the encrypted
    # serializer instead of inlining a primitive string in the checkpoints JSON column.
    original_request: dict[str, str]
    relevant_context: list[dict[str, Any]]
    messages: Annotated[list[Any], add_messages]
    intent: dict[str, Any] | None
    risk: dict[str, Any] | None
    available_tools: list[str]
    model_calls: int
    tool_calls: int
    clarification_rounds: int
    pending_clarification: dict[str, Any] | None
    pending_confirmation: dict[str, Any] | None
    actions: list[ActionReceipt]
    status: str
    final_report: dict[str, Any] | None
    structured_response: dict[str, Any] | None
