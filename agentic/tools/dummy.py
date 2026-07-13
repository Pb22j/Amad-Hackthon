"""In-memory sandbox financial tools for local agent evaluation.

These tools never contact a bank, broker, payment network, or any other
external system. They implement the same strict input and result contracts
expected from production tools, making them useful for evaluating tool choice,
clarification, confirmation, receipts, reporting, and guardrails.

The ownership fields default to ``evaluation-user`` and ``evaluation-tenant``.
Set ``DUMMY_TOOL_USER_ID`` and ``DUMMY_TOOL_TENANT_ID`` when evaluating with a
different signed request identity. The values come from the process environment
rather than model-controlled arguments.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field


class DummyArgs(BaseModel):
    """Base schema that rejects model-invented or misspelled arguments."""

    model_config = ConfigDict(extra="forbid")


class AccountArgs(DummyArgs):
    account: str = Field(default="checking", min_length=1, max_length=100)


class TransactionSearchArgs(DummyArgs):
    query: str = Field(default="", max_length=200)
    limit: int = Field(default=10, ge=1, le=50)


class TransferArgs(DummyArgs):
    destination: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="SAR", pattern=r"^[A-Z]{3}$")


class BillPaymentArgs(DummyArgs):
    biller: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="SAR", pattern=r"^[A-Z]{3}$")


class BeneficiaryArgs(DummyArgs):
    name: str = Field(min_length=1, max_length=200)
    account_reference: str = Field(min_length=3, max_length=200)


class InvestmentArgs(DummyArgs):
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.-]+$")
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=4)


class WithdrawalArgs(DummyArgs):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    account: str = Field(default="checking", min_length=1, max_length=100)
    currency: str = Field(default="SAR", pattern=r"^[A-Z]{3}$")


class NoArgs(DummyArgs):
    pass


@dataclass(slots=True)
class DummyLedger:
    """Process-local ledger reset whenever the service process restarts."""

    cash: Decimal = Decimal("100000.00")
    positions: dict[str, Decimal] = field(
        default_factory=lambda: {"ARAMCO": Decimal("10")}
    )
    beneficiaries: dict[str, str] = field(default_factory=dict)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    sequence: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_reference(self, prefix: str) -> str:
        self.sequence += 1
        return f"dummy-{prefix}-{self.sequence:06d}"


_STATE = DummyLedger()
_PRICES = {
    "ARAMCO": Decimal("30.00"),
    "SABIC": Decimal("75.00"),
    "ACWA": Decimal("250.00"),
}


def _owner() -> tuple[str, str]:
    """Read trusted dummy ownership without exposing it as a tool argument."""

    return (
        os.getenv("DUMMY_TOOL_USER_ID", "evaluation-user"),
        os.getenv("DUMMY_TOOL_TENANT_ID", "evaluation-tenant"),
    )


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _result(
    *,
    status: str,
    summary: str,
    data: dict[str, Any],
    receipt_id: str | None = None,
    operation_id: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    user_id, tenant_id = _owner()
    return {
        "status": status,
        "summary": summary,
        "data": data,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "receipt_id": receipt_id,
        "operation_id": operation_id,
        "error_code": error_code,
    }


async def get_balance(account: str = "checking") -> dict[str, Any]:
    """Return the simulated cash balance for a dummy account."""

    async with _STATE.lock:
        balance = _money(_STATE.cash)
    return _result(
        status="completed",
        summary=f"Retrieved the simulated {account} balance.",
        data={"account": account, "available_balance": balance, "currency": "SAR"},
    )


async def search_transactions(query: str = "", limit: int = 10) -> dict[str, Any]:
    """Search the in-memory transaction history by description."""

    normalized = query.casefold()
    async with _STATE.lock:
        matches = [
            item
            for item in reversed(_STATE.transactions)
            if not normalized or normalized in item["description"].casefold()
        ][:limit]
    return _result(
        status="completed",
        summary=f"Found {len(matches)} simulated transactions.",
        data={"transactions": matches},
    )


async def get_portfolio() -> dict[str, Any]:
    """Return simulated positions valued at fixed evaluation prices."""

    async with _STATE.lock:
        positions = [
            {
                "symbol": symbol,
                "quantity": str(quantity),
                "price": _money(_PRICES.get(symbol, Decimal("10.00"))),
            }
            for symbol, quantity in sorted(_STATE.positions.items())
        ]
    return _result(
        status="completed",
        summary="Retrieved the simulated investment portfolio.",
        data={"positions": positions, "valuation_currency": "SAR"},
    )


async def transfer_funds(
    destination: str, amount: Decimal, currency: str = "SAR"
) -> dict[str, Any]:
    """Simulate a transfer after the agent's exact-confirmation gate."""

    async with _STATE.lock:
        if currency != "SAR":
            return _result(
                status="failed",
                summary="The dummy ledger supports SAR transfers only.",
                data={"currency": currency},
                error_code="unsupported_currency",
            )
        if amount > _STATE.cash:
            return _result(
                status="failed",
                summary="The simulated account has insufficient funds.",
                data={"requested_amount": _money(amount), "currency": currency},
                error_code="insufficient_funds",
            )
        _STATE.cash -= amount
        reference = _STATE.next_reference("transfer")
        transaction = {
            "operation_id": reference,
            "type": "transfer",
            "description": f"Transfer to {destination}",
            "amount": _money(amount),
            "currency": currency,
        }
        _STATE.transactions.append(transaction)
    return _result(
        status="completed",
        summary=f"Simulated transfer to {destination} completed.",
        data=transaction,
        receipt_id=f"receipt-{reference}",
        operation_id=reference,
    )


async def pay_bill(biller: str, amount: Decimal, currency: str = "SAR") -> dict[str, Any]:
    """Simulate paying a bill from the dummy cash balance."""

    async with _STATE.lock:
        if currency != "SAR" or amount > _STATE.cash:
            return _result(
                status="failed",
                summary="The simulated bill payment could not be completed.",
                data={"biller": biller, "amount": _money(amount), "currency": currency},
                error_code=("unsupported_currency" if currency != "SAR" else "insufficient_funds"),
            )
        _STATE.cash -= amount
        reference = _STATE.next_reference("bill")
        transaction = {
            "operation_id": reference,
            "type": "bill_payment",
            "description": f"Bill payment to {biller}",
            "amount": _money(amount),
            "currency": currency,
        }
        _STATE.transactions.append(transaction)
    return _result(
        status="completed",
        summary=f"Simulated bill payment to {biller} completed.",
        data=transaction,
        receipt_id=f"receipt-{reference}",
        operation_id=reference,
    )


async def add_beneficiary(name: str, account_reference: str) -> dict[str, Any]:
    """Add a beneficiary to the process-local dummy address book."""

    async with _STATE.lock:
        _STATE.beneficiaries[name] = account_reference
        reference = _STATE.next_reference("beneficiary")
    return _result(
        status="completed",
        summary=f"Added {name} to the simulated beneficiary list.",
        data={"name": name, "account_reference": account_reference},
        operation_id=reference,
    )


async def buy_investment(symbol: str, quantity: Decimal) -> dict[str, Any]:
    """Buy a simulated position using fixed prices and the dummy cash balance."""

    normalized = symbol.upper()
    price = _PRICES.get(normalized, Decimal("10.00"))
    total = price * quantity
    async with _STATE.lock:
        if total > _STATE.cash:
            return _result(
                status="failed",
                summary="The simulated account has insufficient funds for this purchase.",
                data={"symbol": normalized, "quantity": str(quantity)},
                error_code="insufficient_funds",
            )
        _STATE.cash -= total
        _STATE.positions[normalized] = _STATE.positions.get(normalized, Decimal("0")) + quantity
        reference = _STATE.next_reference("buy")
    data = {
        "symbol": normalized,
        "quantity": str(quantity),
        "price": _money(price),
        "total": _money(total),
        "currency": "SAR",
    }
    return _result(
        status="completed",
        summary=f"Simulated purchase of {quantity} {normalized} completed.",
        data=data,
        receipt_id=f"receipt-{reference}",
        operation_id=reference,
    )


async def sell_investment(symbol: str, quantity: Decimal) -> dict[str, Any]:
    """Sell units from a simulated position at a fixed evaluation price."""

    normalized = symbol.upper()
    price = _PRICES.get(normalized, Decimal("10.00"))
    async with _STATE.lock:
        held = _STATE.positions.get(normalized, Decimal("0"))
        if quantity > held:
            return _result(
                status="failed",
                summary="The simulated portfolio does not contain enough units.",
                data={"symbol": normalized, "held": str(held)},
                error_code="insufficient_position",
            )
        total = price * quantity
        _STATE.positions[normalized] = held - quantity
        _STATE.cash += total
        reference = _STATE.next_reference("sell")
    data = {
        "symbol": normalized,
        "quantity": str(quantity),
        "price": _money(price),
        "total": _money(total),
        "currency": "SAR",
    }
    return _result(
        status="completed",
        summary=f"Simulated sale of {quantity} {normalized} completed.",
        data=data,
        receipt_id=f"receipt-{reference}",
        operation_id=reference,
    )


async def withdraw_funds(
    amount: Decimal, account: str = "checking", currency: str = "SAR"
) -> dict[str, Any]:
    """Simulate a cash withdrawal from the dummy balance."""

    async with _STATE.lock:
        if currency != "SAR" or amount > _STATE.cash:
            return _result(
                status="failed",
                summary="The simulated withdrawal could not be completed.",
                data={"account": account, "amount": _money(amount), "currency": currency},
                error_code=("unsupported_currency" if currency != "SAR" else "insufficient_funds"),
            )
        _STATE.cash -= amount
        reference = _STATE.next_reference("withdrawal")
        transaction = {
            "operation_id": reference,
            "type": "withdrawal",
            "description": f"Cash withdrawal from {account}",
            "amount": _money(amount),
            "currency": currency,
        }
        _STATE.transactions.append(transaction)
    return _result(
        status="completed",
        summary="Simulated withdrawal completed.",
        data=transaction,
        receipt_id=f"receipt-{reference}",
        operation_id=reference,
    )


async def reset_dummy_state() -> None:
    """Restore deterministic balances between evaluation scenarios."""

    async with _STATE.lock:
        _STATE.cash = Decimal("100000.00")
        _STATE.positions = {"ARAMCO": Decimal("10")}
        _STATE.beneficiaries.clear()
        _STATE.transactions.clear()
        _STATE.sequence = 0


def _tool(coroutine: Any, *, name: str, description: str, schema: type[BaseModel]) -> BaseTool:
    return StructuredTool.from_function(
        coroutine=coroutine,
        name=name,
        description=description,
        args_schema=schema,
    )


DUMMY_TOOLS: tuple[BaseTool, ...] = (
    _tool(
        get_balance,
        name="get_balance",
        description="Get the authenticated user's simulated account balance.",
        schema=AccountArgs,
    ),
    _tool(
        search_transactions,
        name="search_transactions",
        description="Search the authenticated user's simulated transaction history.",
        schema=TransactionSearchArgs,
    ),
    _tool(
        get_portfolio,
        name="get_portfolio",
        description="Get the authenticated user's simulated investment portfolio.",
        schema=NoArgs,
    ),
    _tool(
        transfer_funds,
        name="transfer_funds",
        description="Transfer simulated funds to a named destination after confirmation.",
        schema=TransferArgs,
    ),
    _tool(
        pay_bill,
        name="pay_bill",
        description="Pay a simulated bill to a biller after confirmation.",
        schema=BillPaymentArgs,
    ),
    _tool(
        add_beneficiary,
        name="add_beneficiary",
        description="Add a beneficiary to the authenticated user's simulated address book.",
        schema=BeneficiaryArgs,
    ),
    _tool(
        buy_investment,
        name="buy_investment",
        description="Buy a quantity of an investment in the simulated portfolio.",
        schema=InvestmentArgs,
    ),
    _tool(
        sell_investment,
        name="sell_investment",
        description="Sell a quantity from the authenticated user's simulated portfolio.",
        schema=InvestmentArgs,
    ),
    _tool(
        withdraw_funds,
        name="withdraw_funds",
        description="Withdraw simulated cash from an account after confirmation.",
        schema=WithdrawalArgs,
    ),
)
