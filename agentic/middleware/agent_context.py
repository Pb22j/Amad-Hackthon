"""Inject trusted orchestration guidance into each inner-agent model call."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage


class AgentContextMiddleware(AgentMiddleware):
    """Add state-derived capability and reasoning context to the system prompt.

    The outer graph creates this context only after policy screening and intent
    classification. Keeping it in the system message avoids mixing trusted
    orchestration metadata with untrusted conversation messages.
    """

    async def awrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        agent_context = str((request.state or {}).get("agent_context", "")).strip()
        if not agent_context:
            return await handler(request)

        existing = request.system_message
        if existing is None:
            system_message = SystemMessage(content=agent_context)
        elif isinstance(existing.content, str):
            system_message = SystemMessage(
                content=f"{existing.content.rstrip()}\n\n{agent_context}",
                additional_kwargs=existing.additional_kwargs,
                response_metadata=existing.response_metadata,
                name=existing.name,
                id=existing.id,
            )
        else:
            system_message = SystemMessage(
                content=[*existing.content, {"type": "text", "text": agent_context}],
                additional_kwargs=existing.additional_kwargs,
                response_metadata=existing.response_metadata,
                name=existing.name,
                id=existing.id,
            )
        return await handler(request.override(system_message=system_message))
