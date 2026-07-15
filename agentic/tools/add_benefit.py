"""``add_benefit`` — register and activate a beneficiary for transfers.

A destination becomes transferable only after it passes both database checks:
the account number must belong to a real, active bank customer, and it must
not already be in the owner's beneficiary list. Rejections return stable error
codes instead of raising, so the agent can explain the outcome safely.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    BankConnection,
    find_beneficiary,
    find_user_by_account_number,
    find_user_by_username,
    normalize_account_number,
    owner_identity,
    run_in_bank_db,
    timestamp,
    tool_result,
)


class AddBenefitArgs(BankToolArgs):
    full_name_of_benefit_account: str = Field(
        min_length=1,
        max_length=200,
        description="Full name of the beneficiary account holder as provided by the user.",
    )
    benefit_account_number: str = Field(
        min_length=10,
        max_length=34,
        pattern=r"^[A-Za-z0-9\- ]+$",
        description="IBAN / account number of the beneficiary account.",
    )
    short_name: str = Field(
        min_length=1,
        max_length=50,
        description="Short nickname the user wants to save for this beneficiary.",
    )


async def add_benefit(
    full_name_of_benefit_account: str,
    benefit_account_number: str,
    short_name: str,
) -> dict[str, Any]:
    """Validate and activate a new beneficiary in the owner's benefit list."""

    username, _ = owner_identity()
    normalized = normalize_account_number(benefit_account_number)

    def work(connection: BankConnection) -> dict[str, Any]:
        owner = find_user_by_username(connection, username)
        if owner is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )

        existing = find_beneficiary(connection, owner["uuid"], normalized)
        if existing is not None:
            if existing["status"] == "inactive":
                target = find_user_by_account_number(connection, normalized)
                if target is None or target["status"] != "active":
                    return tool_result(
                        status="failed",
                        summary=(
                            "The destination bank account is not active, so the "
                            "beneficiary cannot be activated."
                        ),
                        data={"benefit_account_number": normalized},
                        error_code="account_inactive",
                    )
                now = timestamp()
                connection.execute(
                    "UPDATE beneficiaries SET status = 'active', updatedAt = %s"
                    " WHERE uuid = %s",
                    (now, existing["uuid"]),
                )
                return tool_result(
                    status="completed",
                    summary=(
                        f"Beneficiary {existing['Short_Name']} was automatically "
                        "activated for transfers."
                    ),
                    data={
                        "beneficiary": {
                            "full_name": existing["Full_Name"],
                            "short_name": existing["Short_Name"],
                            "account_number": existing["Account_Number"],
                            "bank_name": target["Bank_Name_Ar"],
                            "status": "active",
                        },
                        "automatically_activated": True,
                    },
                    operation_id=str(existing["uuid"]),
                )
            return tool_result(
                status="failed",
                summary="This account is already active in the beneficiary list, so it was not added again.",
                data={"benefit_account_number": normalized, "status": "active"},
                error_code="beneficiary_already_exists",
            )

        short_name_taken = connection.execute(
            "SELECT 1 FROM beneficiaries"
            " WHERE owner_uuid = %s AND LOWER(TRIM(Short_Name)) = LOWER(%s)",
            (owner["uuid"], short_name.strip()),
        ).fetchone()
        if short_name_taken is not None:
            return tool_result(
                status="failed",
                summary="This short name is already used by another beneficiary; short names must be unique.",
                data={"short_name": short_name.strip()},
                error_code="short_name_already_used",
            )

        target = find_user_by_account_number(connection, normalized)
        if target is None:
            return tool_result(
                status="failed",
                summary="The account number does not match any existing bank account.",
                data={"benefit_account_number": normalized},
                error_code="account_not_found",
            )
        if target["uuid"] == owner["uuid"]:
            return tool_result(
                status="failed",
                summary="The owner's own account cannot be added as a beneficiary.",
                data={"benefit_account_number": normalized},
                error_code="cannot_add_own_account",
            )
        if target["status"] != "active":
            return tool_result(
                status="failed",
                summary="The destination bank account is not active, so it cannot receive transfers.",
                data={"benefit_account_number": normalized},
                error_code="account_inactive",
            )

        beneficiary_id = str(uuid4())
        now = timestamp()
        connection.execute(
            "INSERT INTO beneficiaries"
            " (uuid, owner_uuid, Full_Name, Short_Name, Account_Number, status,"
            "  createdAt, updatedAt)"
            " VALUES (%s, %s, %s, %s, %s, 'active', %s, %s)",
            (
                beneficiary_id,
                owner["uuid"],
                full_name_of_benefit_account.strip(),
                short_name.strip(),
                normalized,
                now,
                now,
            ),
        )
        return tool_result(
            status="completed",
            summary=f"Beneficiary {short_name.strip()} was verified and activated for transfers.",
            data={
                "beneficiary": {
                    "full_name": full_name_of_benefit_account.strip(),
                    "short_name": short_name.strip(),
                    "account_number": normalized,
                    "bank_name": target["Bank_Name_Ar"],
                    "status": "active",
                },
                "automatically_activated": True,
            },
            operation_id=beneficiary_id,
        )

    return await run_in_bank_db(work)


TOOL: BaseTool = StructuredTool.from_function(
    coroutine=add_benefit,
    name="add_benefit",
    description=(
        "Add and activate a beneficiary account in the authenticated user's benefit list "
        "after verifying the account number belongs to a real bank customer and is not "
        "already registered. Required before any transfer to that account."
    ),
    args_schema=AddBenefitArgs,
)
