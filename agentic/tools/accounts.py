"""Bank-backed balance and transaction lookup tools for the demo ledger."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    BankConnection,
    find_user_by_username,
    money,
    masked_account_number,
    next_reference,
    owner_identity,
    resolve_user_account,
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


async def get_balance(account: str = "primary") -> dict[str, Any]:
    username, _ = owner_identity()

    def work(connection: BankConnection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        accounts = connection.execute(
            """SELECT a.* FROM bank_accounts a JOIN users u ON u.uuid = a.user_uuid
               WHERE u.username = %s ORDER BY a.is_primary DESC, a.uuid""",
            (username,),
        ).fetchall()
        resolution = resolve_user_account(
            connection, username=username, account=account
        )
        selected = resolution.match
        if selected is None and resolution.candidates:
            return tool_result(
                status="failed",
                summary="More than one account closely matches the requested account.",
                data={
                    "account": account,
                    "candidates": [
                        {
                            "bank_name": row["bank_name_ar"],
                            "account_type": row["account_type"],
                            "masked_account_number": masked_account_number(
                                row["account_number"]
                            ),
                        }
                        for row in resolution.candidates
                    ],
                },
                error_code="account_ambiguous",
            )
        if selected is None:
            return tool_result(
                status="failed",
                summary="The requested account does not belong to the authenticated customer.",
                data={},
                error_code="account_not_found",
            )
        balance = money(selected["balance_sar"])
        total = sum((money(row["balance_sar"]) for row in accounts), start=money(0))
        nafi_balance = money(user["nafi_balance"])
        nafi_liquid_savings = money(user["nafi_liquid_savings_balance"])
        return tool_result(
            status="completed",
            summary=(
                f"The spendable Nafi wallet balance is {nafi_balance} SAR. "
                f"Linked bank accounts hold {total} SAR and are read-only to Nafi actions."
            ),
            data={
                "nafi_balance_sar": str(nafi_balance),
                "spendable_balance_sar": str(nafi_balance),
                "nafi_liquid_savings_balance_sar": str(nafi_liquid_savings),
                "balance_sar": str(balance),
                "total_balance_sar": str(total),
                "currency": "SAR",
                "account_type": selected["account_type"],
                "bank_name": selected["bank_name_ar"],
                "masked_account_number": masked_account_number(selected["account_number"]),
                "accounts": [
                    {
                        "bank_name": row["bank_name_ar"],
                        "account_type": row["account_type"],
                        "balance_sar": str(money(row["balance_sar"])),
                        "masked_account_number": masked_account_number(row["account_number"]),
                        "is_primary": bool(row["is_primary"]),
                    }
                    for row in accounts
                ],
            },
            operation_id=next_reference(connection, "balance"),
        )

    return await run_in_bank_db(work)


async def search_transactions(query: str = "", limit: int = 10) -> dict[str, Any]:
    username, _ = owner_identity()
    needle = query.strip().casefold()

    def work(connection: BankConnection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        rows = connection.execute(
            "SELECT * FROM transactions WHERE user_uuid = %s ORDER BY createdAt DESC LIMIT 250",
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
    description=(
        "Get the spendable Nafi wallet balance, Nafi liquid-savings balance, plus "
        "read-only linked bank-account balances. Only nafi_balance_sar can fund "
        "Nafi financial actions."
    ),
    args_schema=GetBalanceArgs,
)

SEARCH_TRANSACTIONS_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=search_transactions,
    name="search_transactions",
    description="Search the authenticated customer's bank ledger by text and return recent matches.",
    args_schema=SearchTransactionsArgs,
)
