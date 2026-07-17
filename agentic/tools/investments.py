"""PostgreSQL-backed demo portfolio reads and confirmed investment trades."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    BankConnection,
    BankRow,
    find_user_by_username,
    money,
    next_reference,
    owner_identity,
    run_in_bank_db,
    spent_today,
    timestamp,
    tool_result,
    update_nafi_balance,
)


class PortfolioArgs(BankToolArgs):
    pass


class TradeArgs(BankToolArgs):
    symbol: str = Field(
        min_length=1,
        max_length=40,
        pattern=r"^[A-Za-z0-9.\-\u0600-\u06FF ]+$",
        description=(
            "Supported demo symbol or company alias: ARAMCO/2222/أرامكو, "
            "ALRAJHI/1120/الراجحي, or SABIC/2010/سابك."
        ),
    )
    quantity: float = Field(gt=0, le=1_000_000)


SYMBOL_ALIASES = {
    "2222": "ARAMCO",
    "SAUDI ARAMCO": "ARAMCO",
    "ARAMCO": "ARAMCO",
    "أرامكو": "ARAMCO",
    "ارامكو": "ARAMCO",
    "1120": "ALRAJHI",
    "AL RAJHI": "ALRAJHI",
    "ALRAJHI": "ALRAJHI",
    "الراجحي": "ALRAJHI",
    "2010": "SABIC",
    "SABIC": "SABIC",
    "سابك": "SABIC",
}


def normalize_investment_symbol(value: str) -> str:
    normalized = " ".join(value.strip().split()).upper()
    return SYMBOL_ALIASES.get(normalized, normalized)


def _asset(connection: BankConnection, symbol: str) -> BankRow | None:
    return connection.execute(
        "SELECT * FROM investment_assets WHERE symbol = %s AND status = 'active'",
        (symbol.strip().upper(),),
    ).fetchone()


def _quantity_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


async def get_portfolio() -> dict[str, Any]:
    username, _ = owner_identity()

    def work(connection: BankConnection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="Customer not found.",
                data={},
                error_code="customer_not_found",
            )
        rows = connection.execute(
            "SELECT h.*, a.Name, a.Price_SAR FROM investment_holdings h"
            " JOIN investment_assets a ON a.symbol = h.symbol"
            " WHERE h.user_uuid = %s AND h.Quantity > 0 ORDER BY h.symbol",
            (user["uuid"],),
        ).fetchall()
        holdings = []
        market_total = Decimal("0.00")
        cost_total = Decimal("0.00")
        for row in rows:
            quantity = Decimal(str(row["Quantity"]))
            price = money(row["Price_SAR"])
            average = money(row["Average_Cost_SAR"])
            market_value = money(quantity * price)
            cost_value = money(quantity * average)
            market_total += market_value
            cost_total += cost_value
            holdings.append(
                {
                    "symbol": row["symbol"],
                    "name": row["Name"],
                    "quantity": _quantity_text(quantity),
                    "price_sar": str(price),
                    "average_cost_sar": str(average),
                    "market_value_sar": str(market_value),
                    "unrealized_gain_sar": str(market_value - cost_value),
                }
            )
        return tool_result(
            status="completed",
            summary=f"Portfolio contains {len(holdings)} holdings worth {market_total} SAR.",
            data={
                "holdings": holdings,
                "market_value_sar": str(market_total),
                "cost_basis_sar": str(cost_total),
                "unrealized_gain_sar": str(market_total - cost_total),
                "currency": "SAR",
            },
            operation_id=next_reference(connection, "portfolio"),
        )

    return await run_in_bank_db(work)


async def buy_investment(symbol: str, quantity: float | Decimal) -> dict[str, Any]:
    return await _trade(symbol=symbol, quantity=quantity, side="buy")


async def sell_investment(symbol: str, quantity: float | Decimal) -> dict[str, Any]:
    return await _trade(symbol=symbol, quantity=quantity, side="sell")


async def _trade(*, symbol: str, quantity: float | Decimal, side: str) -> dict[str, Any]:
    username, _ = owner_identity()
    normalized_symbol = normalize_investment_symbol(symbol)
    normalized_quantity = Decimal(str(quantity))

    def work(connection: BankConnection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="Customer not found.",
                data={},
                error_code="customer_not_found",
            )
        asset = _asset(connection, normalized_symbol)
        if asset is None:
            return tool_result(
                status="failed",
                summary="Investment symbol is unavailable.",
                data={"symbol": normalized_symbol},
                error_code="investment_not_found",
            )
        price = money(asset["Price_SAR"])
        total = money(price * normalized_quantity)
        holding = connection.execute(
            "SELECT * FROM investment_holdings WHERE user_uuid = %s AND symbol = %s",
            (user["uuid"], normalized_symbol),
        ).fetchone()
        balance = money(user["nafi_balance"])
        now = timestamp()
        reference = next_reference(connection, f"investment-{side}")
        if side == "buy":
            if total > balance:
                return tool_result(
                    status="failed",
                    summary="The available Nafi wallet balance is insufficient for this purchase.",
                    data={"required_sar": str(total), "available_balance_sar": str(balance)},
                    error_code="insufficient_funds",
                )
            daily_limit = money(user["Daily_Spend_Limit_SAR"])
            already_spent = spent_today(connection, user["uuid"])
            if already_spent + total > daily_limit:
                return tool_result(
                    status="failed",
                    summary="This investment purchase would exceed the daily spend limit.",
                    data={
                        "required_sar": str(total),
                        "spent_today_sar": str(already_spent),
                        "daily_limit_sar": str(daily_limit),
                    },
                    error_code="daily_limit_exceeded",
                )
            old_quantity = Decimal(str(holding["Quantity"])) if holding else Decimal("0")
            old_cost = money(holding["Average_Cost_SAR"]) if holding else Decimal("0.00")
            new_quantity = old_quantity + normalized_quantity
            average_cost = money((old_quantity * old_cost + total) / new_quantity)
            balance_after = balance - total
            if holding:
                connection.execute(
                    "UPDATE investment_holdings SET Quantity = %s, Average_Cost_SAR = %s, updatedAt = %s WHERE uuid = %s",
                    (float(new_quantity), float(average_cost), now, holding["uuid"]),
                )
            else:
                connection.execute(
                    "INSERT INTO investment_holdings (uuid, user_uuid, symbol, Quantity, Average_Cost_SAR, updatedAt) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        str(uuid4()),
                        user["uuid"],
                        normalized_symbol,
                        float(new_quantity),
                        float(average_cost),
                        now,
                    ),
                )
            direction, transaction_type = "debit", "investment_buy"
        else:
            owned = Decimal(str(holding["Quantity"])) if holding else Decimal("0")
            if normalized_quantity > owned:
                return tool_result(
                    status="failed",
                    summary="The portfolio does not contain enough units to sell.",
                    data={
                        "requested_quantity": str(normalized_quantity),
                        "owned_quantity": str(owned),
                    },
                    error_code="insufficient_holdings",
                )
            new_quantity = owned - normalized_quantity
            average_cost = money(holding["Average_Cost_SAR"])
            balance_after = balance + total
            connection.execute(
                "UPDATE investment_holdings SET Quantity = %s, updatedAt = %s WHERE uuid = %s",
                (float(new_quantity), now, holding["uuid"]),
            )
            direction, transaction_type = "credit", "investment_sell"
        update_nafi_balance(connection, user, balance_after)
        connection.execute(
            "INSERT INTO transactions (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR, Counterparty_Name, Counterparty_Account, Description, Category, Balance_After_SAR, Reference, createdAt)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, 'استثمار', %s, %s, %s)",
            (
                str(uuid4()),
                user["uuid"],
                user["nafi_iban"],
                direction,
                transaction_type,
                float(total),
                asset["Name"],
                f"{side} {normalized_quantity} {normalized_symbol}",
                float(balance_after),
                reference,
                now,
            ),
        )
        return tool_result(
            status="completed",
            summary=(
                f"{side.title()} completed for {_quantity_text(normalized_quantity)} units "
                f"of {normalized_symbol} at {price} SAR."
            ),
            data={
                "symbol": normalized_symbol,
                "quantity": _quantity_text(normalized_quantity),
                "unit_price_sar": str(price),
                "total_sar": str(total),
                "remaining_quantity": _quantity_text(new_quantity),
                "new_nafi_balance_sar": str(balance_after),
                "new_balance_sar": str(balance_after),
                "executed_at": now,
            },
            receipt_id=f"receipt-{reference}",
            operation_id=reference,
        )

    return await run_in_bank_db(work)


GET_PORTFOLIO_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=get_portfolio,
    name="get_portfolio",
    description="Get the authenticated customer's current demo investment portfolio and valuation.",
    args_schema=PortfolioArgs,
)
BUY_INVESTMENT_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=buy_investment,
    name="buy_investment",
    description=(
        "Buy a quantity of a supported demo investment using only the Nafi wallet balance "
        "after exact confirmation and OTP. "
        "Supported assets are ARAMCO (2222/أرامكو), ALRAJHI (1120/الراجحي), "
        "and SABIC (2010/سابك)."
    ),
    args_schema=TradeArgs,
)
SELL_INVESTMENT_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=sell_investment,
    name="sell_investment",
    description=(
        "Sell a held quantity of a demo investment and credit proceeds only to the Nafi wallet "
        "after exact confirmation and OTP. "
        "Supported assets are ARAMCO (2222/أرامكو), ALRAJHI (1120/الراجحي), "
        "and SABIC (2010/سابك)."
    ),
    args_schema=TradeArgs,
)
