from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy import func, select

from agentic.agent.graph import build_financial_agent, initial_state
from agentic.persistence.models import AgentTaskRow, ToolExecutionRow
from agentic.policy.models import Intent
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext
from agentic.tools.guard import AgentRuntimeContext, ToolGuardError
from agentic.tools.metadata import ToolMetadata, ToolRisk
from tests.fakes import ScriptedChatModel, StaticClassifier, report_message


class BalanceArgs(BaseModel):
    account: str


class TransferArgs(BaseModel):
    amount: int
    destination: str


async def add_task(database, *, task_id: str = "task-1") -> None:
    async with database.session() as session:
        session.add(
            AgentTaskRow(
                id=task_id,
                request_id="request-1",
                session_id="session-1",
                user_id="user-1",
                tenant_id="tenant-1",
                language="en",
                authorized_scopes=["financial:read", "financial:write"],
                assurance_level="high",
                original_request="fixture",
            )
        )


def runtime_context(database, app_config, *, scopes=None) -> AgentRuntimeContext:
    auth = AuthContext(
        "user-1",
        "tenant-1",
        "session-1",
        frozenset(scopes or {"financial:read", "financial:write"}),
    )
    return AgentRuntimeContext(
        auth=auth,
        task_id="task-1",
        session_factory=database.session_factory,
        config=app_config,
        confirmation_signer=ConfirmationSigner("c" * 32),
    )


def state(request: str = "Show my balance"):
    return initial_state(
        task_id="task-1",
        request_id="request-1",
        session_id="session-1",
        user_id="user-1",
        tenant_id="tenant-1",
        language="en",
        request=request,
    )


@pytest.mark.integration
async def test_graph_returns_concise_structured_report(database, app_config):
    await add_task(database)
    model = ScriptedChatModel(responses=[report_message(summary="Balance retrieved")])
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[],
        tool_metadata=[],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    result = await graph.ainvoke(
        state(),
        config={"configurable": {"thread_id": "task-1"}},
        context=runtime_context(database, app_config),
    )
    assert result["status"] == "completed"
    assert result["final_report"]["summary"] == "Balance retrieved"
    assert result["intent"]["intent"] == "account_information"


@pytest.mark.integration
async def test_unknown_request_returns_capability_grounded_interaction_guidance(
    database, app_config
):
    await add_task(database)

    async def read_balance(account: str) -> dict[str, Any]:
        return {"status": "completed", "summary": account, "data": {}}

    tool = StructuredTool.from_function(
        coroutine=read_balance,
        name="read_balance",
        description="Read the authenticated customer's account balance.",
        args_schema=BalanceArgs,
    )
    metadata = ToolMetadata(
        name="read_balance",
        risk=ToolRisk.SENSITIVE_READ,
        intents=frozenset({Intent.ACCOUNT_INFORMATION.value}),
        required_scopes=frozenset({"financial:read"}),
    )
    model = ScriptedChatModel(
        responses=[
            report_message(
                summary=(
                    "I can help with balances, transactions, payments, beneficiaries, "
                    "and investments. Tell me what you would like to do."
                ),
                interaction_context={
                    "response_kind": "guidance",
                    "user_goal": "Understand what Nafea can help with",
                    "key_facts": ["Account balances are supported."],
                    "suggested_next_steps": ["Ask to view an account balance."],
                },
            )
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.UNKNOWN),
        external_tools=[tool],
        tool_metadata=[metadata],
        config=app_config,
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        state("Can you help me prepare for a trip?"),
        config={"configurable": {"thread_id": "unknown-guidance"}},
        context=runtime_context(database, app_config),
    )

    assert result["status"] == "completed"
    assert result["final_report"]["interaction_context"]["response_kind"] == "guidance"
    assert result["available_tools"] == []
    seen_text = "\n".join(
        str(message.content)
        for invocation in model.seen_messages
        for message in invocation
        if isinstance(message.content, str)
    )
    assert "read_balance" in seen_text
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ToolExecutionRow)) == 0


@pytest.mark.integration
async def test_unknown_request_has_deterministic_guidance_when_support_model_fails(
    database, app_config
):
    await add_task(database)
    graph = build_financial_agent(
        primary_model=ScriptedChatModel(responses=[]),
        classifier_model=StaticClassifier(Intent.UNKNOWN),
        external_tools=[],
        tool_metadata=[],
        config=app_config,
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        state("Something unexpected"),
        config={"configurable": {"thread_id": "unknown-fallback"}},
        context=runtime_context(database, app_config),
    )

    assert result["status"] == "completed"
    assert "I can help with available" in result["final_report"]["summary"]
    context = result["final_report"]["interaction_context"]
    assert context["response_kind"] == "guidance"
    assert context["suggested_next_steps"]


@pytest.mark.integration
async def test_graph_recovers_when_model_finishes_with_plain_text(database, app_config):
    await add_task(database)
    model = ScriptedChatModel(
        responses=[
            AIMessage(content="Your balance was retrieved."),
            report_message(summary="Balance retrieved through recovery"),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[],
        tool_metadata=[],
        config=app_config,
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        state(),
        config={"configurable": {"thread_id": "task-1"}},
        context=runtime_context(database, app_config),
    )

    assert result["status"] == "completed"
    assert result["final_report"]["summary"] == "Balance retrieved through recovery"


@pytest.mark.integration
async def test_graph_executes_guarded_read_tool(database, app_config):
    await add_task(database)
    calls = 0

    async def get_balance(account: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "status": "completed",
            "summary": "Balance retrieved",
            "data": {"account": account, "balance": "100.00", "currency": "SAR"},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
        }

    tool = StructuredTool.from_function(
        coroutine=get_balance,
        name="get_balance",
        description="Retrieve an authenticated user's account balance.",
        args_schema=BalanceArgs,
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_balance",
                        "args": {"account": "checking"},
                        "id": "balance-call",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Balance retrieved", result={"balance": "100.00"}),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[tool],
        tool_metadata=[
            ToolMetadata(
                name="get_balance",
                risk=ToolRisk.SENSITIVE_READ,
                required_scopes=frozenset({"financial:read"}),
            )
        ],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    result = await graph.ainvoke(
        state(),
        config={"configurable": {"thread_id": "task-1"}},
        context=runtime_context(database, app_config),
    )
    assert calls == 1
    assert result["final_report"]["result"]["balance"] == "100.00"
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ToolExecutionRow)) == 1


@pytest.mark.integration
@pytest.mark.security
async def test_tool_result_for_another_user_is_never_returned(database, app_config):
    await add_task(database)

    async def compromised_tool(account: str) -> dict[str, Any]:
        return {
            "status": "completed",
            "summary": "stolen data",
            "data": {"balance": "999999"},
            "user_id": "victim-user",
            "tenant_id": "tenant-1",
        }

    tool = StructuredTool.from_function(
        coroutine=compromised_tool,
        name="get_balance",
        description="Retrieve balance.",
        args_schema=BalanceArgs,
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_balance",
                        "args": {"account": "checking"},
                        "id": "bad-call",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[tool],
        tool_metadata=[ToolMetadata(name="get_balance", risk=ToolRisk.SENSITIVE_READ)],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    with pytest.raises(PermissionError, match="different user"):
        await graph.ainvoke(
            state(),
            config={"configurable": {"thread_id": "task-1"}},
            context=runtime_context(database, app_config),
        )


@pytest.mark.integration
@pytest.mark.security
async def test_missing_scope_prevents_tool_execution(database, app_config):
    await add_task(database)
    executed = False

    async def get_balance(account: str) -> dict[str, Any]:
        nonlocal executed
        executed = True
        return {"status": "completed", "summary": "x", "data": {}}

    tool = StructuredTool.from_function(
        coroutine=get_balance,
        name="get_balance",
        description="Retrieve balance.",
        args_schema=BalanceArgs,
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_balance",
                        "args": {"account": "checking"},
                        "id": "scope-call",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[tool],
        tool_metadata=[
            ToolMetadata(
                name="get_balance",
                risk=ToolRisk.SENSITIVE_READ,
                required_scopes=frozenset({"financial:read"}),
            )
        ],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    with pytest.raises(PermissionError, match="missing required scopes"):
        await graph.ainvoke(
            state(),
            config={"configurable": {"thread_id": "task-1"}},
            context=runtime_context(database, app_config, scopes={"financial:write"}),
        )
    assert not executed


@pytest.mark.integration
async def test_clarification_interrupt_and_resume(database, app_config):
    await add_task(database)
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "request_user_input",
                        "args": {
                            "question": "Which account should be used?",
                            "reason_code": "missing_account",
                            "expected_answer": {"type": "string"},
                            "expires_in_seconds": 900,
                        },
                        "id": "clarification-call",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Account selected"),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.MONEY_TRANSFER),
        external_tools=[],
        tool_metadata=[],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "task-1"}}
    context = runtime_context(database, app_config)
    interrupted = await graph.ainvoke(state("Transfer money"), config=config, context=context)
    payload = interrupted["__interrupt__"][0].value
    assert payload["kind"] == "clarification"
    assert payload["question"] == "Which account should be used?"
    result = await graph.ainvoke(Command(resume="checking"), config=config, context=context)
    assert result["final_report"]["summary"] == "Account selected"


@pytest.mark.integration
@pytest.mark.security
async def test_guard_clarifies_model_invented_explicit_argument(database, app_config):
    await add_task(database)
    observed = []

    async def transfer(amount: int, destination: str) -> dict[str, Any]:
        observed.append({"amount": amount, "destination": destination})
        return {
            "status": "completed",
            "summary": "Transfer simulated",
            "data": {},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
        }

    tool = StructuredTool.from_function(
        coroutine=transfer,
        name="transfer_funds",
        description="Transfer funds.",
        args_schema=TransferArgs,
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "transfer_funds",
                        "args": {"amount": 25, "destination": "default"},
                        "id": "invented-destination",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Transfer simulated"),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.MONEY_TRANSFER),
        external_tools=[tool],
        tool_metadata=[
            ToolMetadata(
                name="transfer_funds",
                risk=ToolRisk.WRITE,
                required_scopes=frozenset({"financial:write"}),
                explicit_user_fields=frozenset({"destination"}),
            )
        ],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    graph_config = {"configurable": {"thread_id": "task-1"}}
    context = runtime_context(database, app_config)
    context.original_request = "Transfer 25"

    interrupted = await graph.ainvoke(state("Transfer 25"), config=graph_config, context=context)

    assert not observed
    assert interrupted["__interrupt__"][0].value["kind"] == "clarification"
    result = await graph.ainvoke(
        Command(resume="Real Beneficiary"), config=graph_config, context=context
    )
    assert observed == [{"amount": 25, "destination": "Real Beneficiary"}]
    assert result["status"] == "completed"


@pytest.mark.integration
@pytest.mark.security
async def test_financial_action_interrupts_for_exact_confirmation(database, app_config):
    await add_task(database)
    calls = 0

    async def transfer(amount: int, destination: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "status": "completed",
            "summary": "Transfer completed",
            "data": {},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "receipt_id": "receipt-1",
        }

    tool = StructuredTool.from_function(
        coroutine=transfer,
        name="transfer_funds",
        description="Transfer funds.",
        args_schema=TransferArgs,
    )
    arguments = {"amount": 500, "destination": "beneficiary-1"}
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "transfer_funds",
                        "args": arguments,
                        "id": "transfer-call",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Transfer completed", receipt_ids=["receipt-1"]),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.MONEY_TRANSFER),
        external_tools=[tool],
        tool_metadata=[
            ToolMetadata(
                name="transfer_funds",
                risk=ToolRisk.FINANCIAL_ACTION,
                required_scopes=frozenset({"financial:write"}),
                requires_confirmation=True,
                requires_receipt=True,
                idempotent=True,
            )
        ],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "task-1"}}
    context = runtime_context(database, app_config)
    interrupted = await graph.ainvoke(state("Transfer 500 SAR"), config=config, context=context)
    assert calls == 0
    assert interrupted["__interrupt__"][0].value["arguments"] == arguments
    token = context.confirmation_signer.issue(
        auth=context.auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments=arguments,
    )
    context.otp_verified = True
    result = await graph.ainvoke(Command(resume=token), config=config, context=context)
    assert calls == 1
    assert result["final_report"]["receipt_ids"] == ["receipt-1"]


@pytest.mark.integration
@pytest.mark.security
async def test_financial_action_separates_clarification_from_confirmation(
    database, app_config
):
    await add_task(database)
    observed = []

    async def transfer(amount: int, destination: str) -> dict[str, Any]:
        observed.append({"amount": amount, "destination": destination})
        return {
            "status": "completed",
            "summary": "Transfer completed",
            "data": {},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "receipt_id": "receipt-1",
        }

    tool = StructuredTool.from_function(
        coroutine=transfer,
        name="transfer_funds",
        description="Transfer funds.",
        args_schema=TransferArgs,
    )
    initial_arguments = {"amount": 2000, "destination": "default"}
    clarified_arguments = {"amount": 2000, "destination": "Yousef"}
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "transfer_funds",
                        "args": initial_arguments,
                        "id": "transfer-before-clarification",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "transfer_funds",
                        "args": clarified_arguments,
                        "id": "transfer-after-clarification",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Transfer completed", receipt_ids=["receipt-1"]),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.MONEY_TRANSFER),
        external_tools=[tool],
        tool_metadata=[
            ToolMetadata(
                name="transfer_funds",
                risk=ToolRisk.FINANCIAL_ACTION,
                required_scopes=frozenset({"financial:write"}),
                explicit_user_fields=frozenset({"amount", "destination"}),
                requires_confirmation=True,
                requires_receipt=True,
                idempotent=True,
            )
        ],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    graph_config = {"configurable": {"thread_id": "task-1"}}
    context = runtime_context(database, app_config)
    context.original_request = "Transfer two thousands riyals"

    clarification = await graph.ainvoke(
        state(context.original_request), config=graph_config, context=context
    )
    clarification_payload = clarification["__interrupt__"][0].value
    assert clarification_payload["kind"] == "clarification"
    assert clarification_payload["expected_answer"]["field"] == "destination"

    context.explicit_user_values = ("Yousef",)
    context.resuming_from_clarification = True
    confirmation = await graph.ainvoke(
        Command(resume="Yousef"), config=graph_config, context=context
    )
    confirmation_payload = confirmation["__interrupt__"][0].value
    assert confirmation_payload["kind"] == "confirmation"
    assert confirmation_payload["arguments"] == clarified_arguments
    assert observed == []

    token = context.confirmation_signer.issue(
        auth=context.auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments=clarified_arguments,
    )
    context.otp_verified = True
    result = await graph.ainvoke(
        Command(resume=token), config=graph_config, context=context
    )

    assert observed == [clarified_arguments]
    assert result["final_report"]["receipt_ids"] == ["receipt-1"]


@pytest.mark.integration
@pytest.mark.security
async def test_completed_financial_action_without_receipt_fails(database, app_config):
    await add_task(database)

    async def transfer(amount: int, destination: str) -> dict[str, Any]:
        return {
            "status": "completed",
            "summary": "Transfer completed",
            "data": {},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
        }

    tool = StructuredTool.from_function(
        coroutine=transfer,
        name="transfer_funds",
        description="Transfer funds.",
        args_schema=TransferArgs,
    )
    arguments = {"amount": 500, "destination": "beneficiary-1"}
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "transfer_funds",
                        "args": arguments,
                        "id": "transfer-call",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.MONEY_TRANSFER),
        external_tools=[tool],
        tool_metadata=[
            ToolMetadata(
                name="transfer_funds",
                risk=ToolRisk.FINANCIAL_ACTION,
                required_scopes=frozenset({"financial:write"}),
                requires_confirmation=True,
                requires_receipt=True,
            )
        ],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    context = runtime_context(database, app_config)
    config = {"configurable": {"thread_id": "task-1"}}
    await graph.ainvoke(state("Transfer 500 SAR"), config=config, context=context)
    token = context.confirmation_signer.issue(
        auth=context.auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments=arguments,
    )
    context.otp_verified = True
    with pytest.raises(ToolGuardError, match="receipt"):
        await graph.ainvoke(Command(resume=token), config=config, context=context)


@pytest.mark.integration
async def test_read_tool_retries_transient_failures(database, app_config):
    await add_task(database)
    calls = 0

    async def flaky(account: str):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("temporary")
        return {
            "status": "completed",
            "summary": "Recovered",
            "data": {},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
        }

    tool = StructuredTool.from_function(
        coroutine=flaky, name="get_balance", description="read", args_schema=BalanceArgs
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_balance",
                        "args": {"account": "checking"},
                        "id": "retry",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Recovered"),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[tool],
        tool_metadata=[ToolMetadata(name="get_balance", risk=ToolRisk.READ)],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    await graph.ainvoke(
        state(),
        config={"configurable": {"thread_id": "retry"}},
        context=runtime_context(database, app_config),
    )
    assert calls == 3


@pytest.mark.integration
@pytest.mark.security
async def test_tool_without_required_owner_metadata_fails(database, app_config):
    await add_task(database)

    async def unsafe(account: str):
        return {"status": "completed", "summary": "missing owner", "data": {}}

    tool = StructuredTool.from_function(
        coroutine=unsafe, name="get_balance", description="read", args_schema=BalanceArgs
    )
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_balance",
                        "args": {"account": "checking"},
                        "id": "owner",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[tool],
        tool_metadata=[ToolMetadata(name="get_balance", risk=ToolRisk.READ)],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    with pytest.raises(ToolGuardError, match="ownership metadata"):
        await graph.ainvoke(
            state(),
            config={"configurable": {"thread_id": "owner"}},
            context=runtime_context(database, app_config),
        )


@pytest.mark.integration
async def test_completed_execution_is_reused_idempotently(database, app_config):
    await add_task(database)
    calls = 0

    async def get_balance(account: str):
        nonlocal calls
        calls += 1
        return {
            "status": "completed",
            "summary": "Balance",
            "data": {"balance": 10},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
        }

    tool = StructuredTool.from_function(
        coroutine=get_balance,
        name="get_balance",
        description="read",
        args_schema=BalanceArgs,
    )
    tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_balance",
                "args": {"account": "checking"},
                "id": "same",
                "type": "tool_call",
            }
        ],
    )
    model = ScriptedChatModel(responses=[tool_call, report_message(), tool_call, report_message()])
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(Intent.ACCOUNT_INFORMATION),
        external_tools=[tool],
        tool_metadata=[ToolMetadata(name="get_balance", risk=ToolRisk.READ)],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    context = runtime_context(database, app_config)
    await graph.ainvoke(state(), config={"configurable": {"thread_id": "first"}}, context=context)
    await graph.ainvoke(state(), config={"configurable": {"thread_id": "second"}}, context=context)
    assert calls == 1
