"""Dynamic least-privilege filtering of model-visible financial tools."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, ToolMessage


def _completed_tool_names(messages: list[Any]) -> set[str]:
    """Recover completed tool names even when providers omit ToolMessage.name."""

    call_names: dict[str, str] = {}
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            call_id = call.get("id")
            name = call.get("name")
            if call_id and name:
                call_names[str(call_id)] = str(name)

    completed: set[str] = set()
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        name = message.name or call_names.get(str(message.tool_call_id))
        if name:
            completed.add(name)
    return completed


class IntentToolScopeMiddleware(AgentMiddleware):
    """Hide external tools not authorized for the classified intent.

    Internal clarification and response-format tools are not managed names and
    remain visible. The model therefore cannot access unrelated financial data
    merely because the caller has broad scopes.
    """

    def __init__(
        self,
        managed_tool_names: set[str],
        required_tool_sequences: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__()
        self.managed_tool_names = frozenset(managed_tool_names)
        self.required_tool_sequences = required_tool_sequences or {}

    async def awrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        state = request.state or {}
        allowed = frozenset(state.get("available_tools", ()))
        intent = (state.get("intent") or {}).get("intent")
        sequence = self.required_tool_sequences.get(str(intent), ())
        registered_tools = {
            str(name)
            for tool in request.tools
            if (name := getattr(tool, "name", None)) is not None
        }
        # Sequence policies are reusable across agent compositions. If a graph
        # does not register the whole workflow, fall back to ordinary intent
        # scoping instead of trapping the model with an impossible next step.
        if not set(sequence).issubset(registered_tools):
            sequence = ()
        completed_tools = _completed_tool_names(request.messages)
        required_next = next((name for name in sequence if name not in completed_tools), None)
        if required_next is not None:
            # A required action sequence prevents the model from replacing live
            # financial evidence with a fabricated refusal or clarification.
            # Structured output is a separate model exit path, so it must also
            # be unavailable until all authoritative steps have completed.
            return await handler(
                request.override(
                    tools=[
                        tool
                        for tool in request.tools
                        if getattr(tool, "name", None) == required_next
                    ],
                    response_format=None,
                    tool_choice=required_next,
                )
            )
        if sequence:
            return await handler(
                request.override(
                    tools=[
                        tool
                        for tool in request.tools
                        if getattr(tool, "name", None) not in self.managed_tool_names
                        and getattr(tool, "name", None) != "request_user_input"
                    ]
                )
            )
        scoped_tools = [
            tool
            for tool in request.tools
            if getattr(tool, "name", None) not in self.managed_tool_names
            or getattr(tool, "name", None) in allowed
        ]
        return await handler(request.override(tools=scoped_tools))
