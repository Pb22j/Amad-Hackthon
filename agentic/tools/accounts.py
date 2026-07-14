"""Bank-backed balance and transaction lookup tools for the demo ledger."""

from __future__ import annotations

import sqlite3
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    find_user_by_username,
    money,
    next_reference,
    normalize_account_number,
    owner_identity,
    run_in_bank_db,
    tool_result,
)


class GetBalanceArgs(BankToolArgs):
    account: str = Field(
        default="primary",
        min_length=1,
        max_length=100,
        description="Account alias or account number; defaults to the primary account.",
    )


class SearchTransactionsArgs(BankToolArgs):
    query: str = Field(
        default="", max_length=200, description="Optional text to match transaction details."
    )
    limit: int = Field(default=10, ge=1, le=50)


def _masked_account(account_number: str) -> str:
    return f"{account_number[:4]}{'*' * max(len(account_number) - 8, 0)}{account_number[-4:]}"


async def get_balance(account: str = "primary") -> dict[str, Any]:
    username, _ = owner_identity()

    def work(connection: sqlite3.Connection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        requested = normalize_account_number(account)
        aliases = {"PRIMARY", "CHECKING", "CURRENT", "الرئيسي", "الجاري"}
        if requested not in aliases and requested != user["Account_Number"]:
            return tool_result(
                status="failed",
                summary="The requested account does not belong to the authenticated customer.",
                data={},
                error_code="account_not_found",
            )
        balance = money(user["Balance_SAR"])
        return tool_result(
            status="completed",
            summary=f"The available primary-account balance is {balance} SAR.",
            data={
                "balance_sar": str(balance),
                "currency": "SAR",
                "account_type": user["Account_Type_Ar"],
                "bank_name": user["Bank_Name_Ar"],
                "masked_account_number": _masked_account(user["Account_Number"]),
                "account_status": user["status"],
            },
            operation_id=next_reference(connection, "balance"),
        )

    return await run_in_bank_db(work)


async def search_transactions(query: str = "", limit: int = 10) -> dict[str, Any]:
    username, _ = owner_identity()
    needle = query.strip().casefold()

    def work(connection: sqlite3.Connection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        rows = connection.execute(
            "SELECT * FROM transactions WHERE user_uuid = ? ORDER BY createdAt DESC LIMIT 250",
            (user["uuid"],),
        ).fetchall()
        if needle:
            rows = [
                row
                for row in rows
                if needle
                in " ".join(
                    str(row[key] or "")
                    for key in (
                        "Transaction_Type",
                        "Counterparty_Name",
                        "Description",
                        "Category",
                        "Reference",
                    )
                ).casefold()
            ]
        selected = rows[:limit]
        items = [
            {
                "date": row["createdAt"],
                "direction": row["direction"],
                "type": row["Transaction_Type"],
                "amount_sar": str(money(row["Amount_SAR"])),
                "counterparty": row["Counterparty_Name"],
                "description": row["Description"],
                "category": row["Category"],
                "reference": row["Reference"],
            }
            for row in selected
        ]
        return tool_result(
            status="completed",
            summary=f"Found {len(items)} matching transactions.",
            data={"query": query.strip(), "transactions": items, "truncated": len(rows) > limit},
            operation_id=next_reference(connection, "transaction-search"),
        )

    return await run_in_bank_db(work)


GET_BALANCE_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=get_balance,
    name="get_balance",
    description="Get the authenticated customer's current bank balance and account status.",
    args_schema=GetBalanceArgs,
)

SEARCH_TRANSACTIONS_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=search_transactions,
    name="search_transactions",
    description="Search the authenticated customer's bank ledger by text and return recent matches.",
    args_schema=SearchTransactionsArgs,
)
