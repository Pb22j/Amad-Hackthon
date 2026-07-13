from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from agentic.agent.graph import build_financial_agent, initial_state
from agentic.persistence.models import AgentTaskRow
from agentic.policy.models import Intent
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext
from agentic.tools.guard import AgentRuntimeContext
from agentic.tools.metadata import ToolMetadata, ToolRisk
from tests.fakes import ScriptedChatModel, StaticClassifier, report_message


class FinancialActionArgs(BaseModel):
    reference: str
    amount: int


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.parametrize(
    ("tool_name", "intent", "scope"),
    [
        ("transfer_funds", Intent.MONEY_TRANSFER, "financial:write"),
        ("pay_bill", Intent.BILL_PAYMENT, "financial:write"),
        ("add_beneficiary", Intent.BENEFICIARY_MANAGEMENT, "financial:write"),
        ("buy_investment", Intent.INVESTMENT_BUY, "investment:trade"),
        ("sell_investment", Intent.INVESTMENT_SELL, "investment:trade"),
        ("withdraw_funds", Intent.MONEY_TRANSFER, "financial:write"),
    ],
)
async def test_supported_financial_actions_require_confirmation_and_receipt(
    database, app_config, tool_name, intent, scope
):
    task_id = f"task-{tool_name}"
    async with database.session() as session:
        session.add(
            AgentTaskRow(
                id=task_id,
                request_id=f"request-{tool_name}",
                session_id=f"session-{tool_name}",
                user_id="user-1",
                tenant_id="tenant-1",
                language="en",
                authorized_scopes=[scope],
                assurance_level="high",
                original_request=tool_name,
            )
        )
    calls = 0

    async def financial_action(reference: str, amount: int) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "status": "completed",
            "summary": f"{tool_name} completed",
            "data": {"reference": reference, "amount": amount},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "receipt_id": f"receipt-{tool_name}",
        }

    tool = StructuredTool.from_function(
        coroutine=financial_action,
        name=tool_name,
        description=f"Execute {tool_name}",
        args_schema=FinancialActionArgs,
    )
    arguments = {"reference": "authorized-resource", "amount": 25}
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": tool_name,
                        "args": arguments,
                        "id": f"call-{tool_name}",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(
                summary=f"{tool_name} completed",
                receipt_ids=[f"receipt-{tool_name}"],
            ),
        ]
    )
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(intent),
        external_tools=[tool],
        tool_metadata=[
            ToolMetadata(
                name=tool_name,
                risk=ToolRisk.FINANCIAL_ACTION,
                required_scopes=frozenset({scope}),
                requires_confirmation=True,
                requires_receipt=True,
            )
        ],
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    auth = AuthContext(
        "user-1", "tenant-1", f"session-{tool_name}", frozenset({scope})
    )
    signer = ConfirmationSigner("c" * 32)
    context = AgentRuntimeContext(
        auth,
        task_id,
        database.session_factory,
        app_config,
        signer,
    )
    graph_config = {"configurable": {"thread_id": task_id}}
    interrupted = await graph.ainvoke(
        initial_state(
            task_id=task_id,
            request_id=f"request-{tool_name}",
            session_id=f"session-{tool_name}",
            user_id="user-1",
            tenant_id="tenant-1",
            language="en",
            request=f"Please {tool_name}",
        ),
        config=graph_config,
        context=context,
    )
    assert calls == 0
    assert interrupted["__interrupt__"][0].value["kind"] == "confirmation"
    token = signer.issue(
        auth=auth,
        task_id=task_id,
        tool_name=tool_name,
        arguments=arguments,
    )
    result = await graph.ainvoke(Command(resume=token), config=graph_config, context=context)
    assert calls == 1
    assert result["final_report"]["receipt_ids"] == [f"receipt-{tool_name}"]

