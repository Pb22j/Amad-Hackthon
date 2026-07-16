"""Tests for deterministic intent-based model tool visibility."""

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, ToolMessage
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


@tool
def list_beneficiaries() -> str:
    """Resolve live beneficiaries."""

    return "beneficiaries"


@tool
def transfer_between_accounts() -> str:
    """Execute a resolved transfer."""

    return "transferred"


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


async def test_first_step_must_select_tool_before_clarification_or_report():
    middleware = IntentToolScopeMiddleware(
        {"allowed_tool", "unrelated_tool"},
        require_tool_selection_first=True,
    )
    request = ModelRequest(
        model=ScriptedChatModel(responses=[]),
        messages=[],
        tools=[allowed_tool, unrelated_tool, internal_response_tool],
        response_format="agent-report",
        state={"messages": [], "available_tools": ["allowed_tool"]},
    )
    observed = []
    options = {}

    async def handler(scoped_request):
        observed.extend(tool.name for tool in scoped_request.tools)
        options.update(
            response_format=scoped_request.response_format,
            tool_choice=scoped_request.tool_choice,
        )
        return ModelResponse(result=[])

    await middleware.awrap_model_call(request, handler)

    assert observed == ["allowed_tool"]
    assert options == {"response_format": None, "tool_choice": "required"}


async def test_internal_exits_return_after_model_selects_a_financial_tool():
    middleware = IntentToolScopeMiddleware(
        {"allowed_tool", "unrelated_tool"},
        require_tool_selection_first=True,
    )
    selected = AIMessage(
        content="",
        tool_calls=[{"id": "allowed-1", "name": "allowed_tool", "args": {}}],
    )
    completed = ToolMessage(content="allowed", tool_call_id="allowed-1", name="allowed_tool")
    request = ModelRequest(
        model=ScriptedChatModel(responses=[]),
        messages=[selected, completed],
        tools=[allowed_tool, unrelated_tool, internal_response_tool],
        response_format="agent-report",
        state={"messages": [], "available_tools": ["allowed_tool"]},
    )
    observed = []

    async def handler(scoped_request):
        observed.extend(tool.name for tool in scoped_request.tools)
        assert scoped_request.response_format == "agent-report"
        assert scoped_request.tool_choice is None
        return ModelResponse(result=[])

    await middleware.awrap_model_call(request, handler)

    assert observed == ["allowed_tool", "internal_response_tool"]


async def test_required_sequence_forces_authoritative_transfer_directly():
    middleware = IntentToolScopeMiddleware(
        {"list_beneficiaries", "transfer_between_accounts"},
        required_tool_sequences={
            "saved_beneficiary_transfer": (
                "transfer_between_accounts",
            )
        },
    )
    base_state = {
        "messages": [],
        "available_tools": ["list_beneficiaries", "transfer_between_accounts"],
        "intent": {"intent": "saved_beneficiary_transfer"},
    }

    async def visible(messages):
        observed = []
        request_options = {}
        request = ModelRequest(
            model=ScriptedChatModel(responses=[]),
            messages=messages,
            tools=[list_beneficiaries, transfer_between_accounts, internal_response_tool],
            response_format="agent-report",
            state=base_state,
        )

        async def handler(scoped_request):
            observed.extend(tool.name for tool in scoped_request.tools)
            request_options.update(
                response_format=scoped_request.response_format,
                tool_choice=scoped_request.tool_choice,
            )
            return ModelResponse(result=[])

        await middleware.awrap_model_call(request, handler)
        return observed, request_options

    observed, options = await visible([])
    assert observed == ["transfer_between_accounts"]
    assert options == {"response_format": None, "tool_choice": "transfer_between_accounts"}
    transferred = ToolMessage(
        content="transferred",
        tool_call_id="transfer-1",
        name="transfer_between_accounts",
    )
    observed, options = await visible([transferred])
    assert observed == ["internal_response_tool"]
    assert options == {"response_format": "agent-report", "tool_choice": None}


async def test_required_sequence_recovers_tool_name_from_call_id():
    middleware = IntentToolScopeMiddleware(
        {"list_beneficiaries", "transfer_between_accounts"},
        required_tool_sequences={
            "saved_beneficiary_transfer": (
                "transfer_between_accounts",
            )
        },
    )
    call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "transfer-1",
                "name": "transfer_between_accounts",
                "args": {"destination_account": "Ahmed", "amount": 700},
            }
        ],
    )
    result_without_name = ToolMessage(content="transferred", tool_call_id="transfer-1")
    observed = []
    request = ModelRequest(
        model=ScriptedChatModel(responses=[]),
        messages=[call, result_without_name],
        tools=[list_beneficiaries, transfer_between_accounts, internal_response_tool],
        state={
            "messages": [],
            "available_tools": ["list_beneficiaries", "transfer_between_accounts"],
            "intent": {"intent": "saved_beneficiary_transfer"},
        },
    )

    async def handler(scoped_request):
        observed.extend(tool.name for tool in scoped_request.tools)
        return ModelResponse(result=[])

    await middleware.awrap_model_call(request, handler)

    assert observed == ["internal_response_tool"]


async def test_required_sequence_is_ignored_when_workflow_is_not_registered():
    middleware = IntentToolScopeMiddleware(
        {"allowed_tool"},
        required_tool_sequences={
            "money_transfer": ("transfer_between_accounts",)
        },
    )
    observed = []
    request = ModelRequest(
        model=ScriptedChatModel(responses=[]),
        messages=[],
        tools=[allowed_tool, internal_response_tool],
        response_format="agent-report",
        state={
            "messages": [],
            "available_tools": ["allowed_tool"],
            "intent": {"intent": "money_transfer"},
        },
    )

    async def handler(scoped_request):
        observed.extend(tool.name for tool in scoped_request.tools)
        assert scoped_request.response_format == "agent-report"
        assert scoped_request.tool_choice is None
        return ModelResponse(result=[])

    await middleware.awrap_model_call(request, handler)

    assert observed == ["allowed_tool", "internal_response_tool"]
