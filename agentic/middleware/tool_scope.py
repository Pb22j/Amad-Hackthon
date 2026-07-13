"""Dynamic least-privilege filtering of model-visible financial tools."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse


class IntentToolScopeMiddleware(AgentMiddleware):
    """Hide external tools not authorized for the classified intent.

    Internal clarification and response-format tools are not managed names and
    remain visible. The model therefore cannot access unrelated financial data
    merely because the caller has broad scopes.
    """

    def __init__(self, managed_tool_names: set[str]) -> None:
        super().__init__()
        self.managed_tool_names = frozenset(managed_tool_names)

    async def awrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        state = request.state or {}
        allowed = frozenset(state.get("available_tools", ()))
        scoped_tools = [
            tool
            for tool in request.tools
            if getattr(tool, "name", None) not in self.managed_tool_names
            or getattr(tool, "name", None) in allowed
        ]
        return await handler(request.override(tools=scoped_tools))
