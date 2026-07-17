"""Contract and state-transition tests for the local sandbox tools."""

from decimal import Decimal

import pytest

from agentic.tools.dummy import (
    DUMMY_TOOLS,
    add_beneficiary,
    buy_investment,
    get_balance,
    get_portfolio,
    pay_bill,
    reset_dummy_state,
    search_transactions,
    sell_investment,
    transfer_funds,
    withdraw_funds,
)
from agentic.tools.metadata import ToolResult
from agentic.tools.provider import load_tool_bundle


EXPECTED_TOOLS = {
    "get_balance",
    "search_transactions",
    "get_portfolio",
    "transfer_funds",
    "pay_bill",
    "add_beneficiary",
    "buy_investment",
    "sell_investment",
    "withdraw_funds",
}


@pytest.fixture(autouse=True)
async def clean_ledger(monkeypatch):
    monkeypatch.setenv("DUMMY_TOOL_USER_ID", "evaluation-user")
    monkeypatch.setenv("DUMMY_TOOL_TENANT_ID", "evaluation-tenant")
    await reset_dummy_state()


def test_dummy_tools_are_discovered_with_security_metadata(app_config):
    # The default package now exposes the bank tools; the dummy sandbox stays
    # available through the explicit provider override.
    bundle = load_tool_bundle(
        "agentic.tools.dummy:DUMMY_TOOLS", app_config.tools.tools, require_tools=True
    )

    assert {tool.name for tool in DUMMY_TOOLS} == EXPECTED_TOOLS
    assert {tool.name for tool in bundle.tools} == EXPECTED_TOOLS
    assert {item.name for item in bundle.metadata} == EXPECTED_TOOLS
    transfer = next(item for item in bundle.metadata if item.name == "transfer_funds")
    assert transfer.requires_confirmation
    assert transfer.requires_receipt
    assert transfer.required_scopes == frozenset({"financial:write"})


@pytest.mark.asyncio
async def test_transfer_changes_balance_and_is_searchable():
    before = ToolResult.model_validate(await get_balance())
    transfer = ToolResult.model_validate(
        await transfer_funds("Test beneficiary", Decimal("250.00"))
    )
    after = ToolResult.model_validate(await get_balance())
    history = ToolResult.model_validate(await search_transactions("beneficiary"))

    assert before.data["available_balance"] == "100000.00"
    assert transfer.status == "completed"
    assert transfer.receipt_id
    assert transfer.user_id == "evaluation-user"
    assert transfer.tenant_id == "evaluation-tenant"
    assert after.data["available_balance"] == "99750.00"
    assert len(history.data["transactions"]) == 1


@pytest.mark.asyncio
async def test_investment_purchase_sale_and_insufficient_position():
    purchase = ToolResult.model_validate(await buy_investment("SABIC", Decimal("2")))
    sale = ToolResult.model_validate(await sell_investment("SABIC", Decimal("1")))
    rejected = ToolResult.model_validate(await sell_investment("SABIC", Decimal("2")))
    portfolio = ToolResult.model_validate(await get_portfolio())

    assert purchase.status == sale.status == "completed"
    assert purchase.receipt_id and sale.receipt_id
    assert rejected.status == "failed"
    assert rejected.error_code == "insufficient_position"
    sabic = next(item for item in portfolio.data["positions"] if item["symbol"] == "SABIC")
    assert sabic["quantity"] == "1"


@pytest.mark.asyncio
async def test_remaining_dummy_actions_follow_result_contract():
    results = [
        await pay_bill("Electricity", Decimal("100.00")),
        await add_beneficiary("Savings", "SA-DUMMY-001"),
        await withdraw_funds(Decimal("50.00")),
    ]

    validated = [ToolResult.model_validate(result) for result in results]
    assert all(result.status == "completed" for result in validated)
    assert validated[0].receipt_id
    assert validated[1].operation_id and validated[1].receipt_id is None
    assert validated[1].data["status"] == "active"
    assert validated[1].data["automatically_activated"] is True
    assert validated[2].receipt_id


@pytest.mark.asyncio
async def test_dummy_tools_fail_safely_for_unsupported_or_unaffordable_actions():
    unsupported = ToolResult.model_validate(
        await transfer_funds("Destination", Decimal("1.00"), "USD")
    )
    unaffordable = ToolResult.model_validate(
        await buy_investment("ACWA", Decimal("1000"))
    )

    assert unsupported.status == unaffordable.status == "failed"
    assert unsupported.error_code == "unsupported_currency"
    assert unaffordable.error_code == "insufficient_funds"
