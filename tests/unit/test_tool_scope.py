"""Tests for deterministic intent-based model tool visibility."""

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.tools import tool

from agentic.middleware.tool_scope import IntentToolScopeMiddleware
from tests.fakes import ScriptedChatModel


@tool
def allowed_tool() -> str:
    """Allowed test capability."""

    return "allowed"


@tool
def unrelated_tool() -> str:
    """Unrelated test capability."""

    return "unrelated"


@tool
def internal_response_tool() -> str:
    """Internal tool not managed by financial intent metadata."""

    return "response"


async def test_tool_scope_removes_unrelated_external_tools():
    middleware = IntentToolScopeMiddleware({"allowed_tool", "unrelated_tool"})
    request = ModelRequest(
        model=ScriptedChatModel(responses=[]),
        messages=[],
        tools=[allowed_tool, unrelated_tool, internal_response_tool],
        state={"messages": [], "available_tools": ["allowed_tool"]},
    )
    observed = []

    async def handler(scoped_request):
        observed.extend(tool.name for tool in scoped_request.tools)
        return ModelResponse(result=[])

    await middleware.awrap_model_call(request, handler)

    assert observed == ["allowed_tool", "internal_response_tool"]
