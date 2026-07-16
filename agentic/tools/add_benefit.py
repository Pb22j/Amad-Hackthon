"""``add_benefit`` — register and activate a beneficiary for transfers.

A destination becomes transferable only after its unique Nafi IBAN resolves to
a real user who is not already in the owner's beneficiary list. Rejections return stable error
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
    find_user_by_nafi_iban,
    find_user_by_username,
    normalize_account_number,
    owner_identity,
    run_in_bank_db,
    timestamp,
    tool_result,
)


class AddBenefitArgs(BankToolArgs):
    nafi_iban: str = Field(
        min_length=10,
        max_length=34,
        pattern=r"^[A-Za-z0-9\- ]+$",
        description="The beneficiary's unique Nafi IBAN.",
    )
    short_name: str = Field(
        min_length=1,
        max_length=50,
        description="Short nickname the user wants to save for this beneficiary.",
    )


class ListBeneficiariesArgs(BankToolArgs):
    pass


async def list_beneficiaries() -> dict[str, Any]:
    """Return the authenticated customer's authoritative beneficiary list."""

    username, _ = owner_identity()

    def work(connection: BankConnection) -> dict[str, Any]:
        owner = find_user_by_username(connection, username)
        if owner is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        statement = (
            "SELECT target.full_name_ar, target.full_name_en, target.nafi_iban,"
            " b.short_name"
            " FROM beneficiaries b"
            " JOIN users target ON target.uuid = b.beneficiary_uuid"
            " WHERE b.owner_uuid = %s"
        )
        parameters: list[Any] = [owner["uuid"]]
        statement += " ORDER BY b.Short_Name, target.full_name_ar"
        rows = connection.execute(statement, tuple(parameters)).fetchall()
        beneficiaries = [
            {
                "full_name": row["full_name_ar"],
                "full_name_en": row["full_name_en"],
                "short_name": row["Short_Name"],
                "nafi_iban": row["nafi_iban"],
                "wallet": "Nafi",
            }
            for row in rows
        ]
        return tool_result(
            status="completed",
            summary=f"Found {len(beneficiaries)} saved beneficiaries.",
            data={"beneficiaries": beneficiaries, "count": len(beneficiaries)},
        )

    return await run_in_bank_db(work)


async def add_benefit(
    nafi_iban: str,
    short_name: str,
) -> dict[str, Any]:
    """Validate and activate a new beneficiary in the owner's benefit list."""

    username, _ = owner_identity()
    normalized = normalize_account_number(nafi_iban)

    def work(connection: BankConnection) -> dict[str, Any]:
        owner = find_user_by_username(connection, username)
        if owner is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )

        if find_beneficiary(connection, owner["uuid"], normalized) is not None:
            return tool_result(
                status="failed",
                summary="This Nafi user is already in the beneficiary list.",
                data={"nafi_iban": normalized},
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

        target = find_user_by_nafi_iban(connection, normalized)
        if target is None:
            return tool_result(
                status="failed",
                summary="The Nafi IBAN does not match an existing Nafi user.",
                data={"nafi_iban": normalized},
                error_code="nafi_iban_not_found",
            )
        if target["uuid"] == owner["uuid"]:
            return tool_result(
                status="failed",
                summary="Your own Nafi IBAN cannot be added as a beneficiary.",
                data={"nafi_iban": normalized},
                error_code="cannot_add_own_account",
            )
        beneficiary_id = str(uuid4())
        now = timestamp()
        connection.execute(
            "INSERT INTO beneficiaries"
            " (uuid, owner_uuid, beneficiary_uuid, Short_Name, createdAt)"
            " VALUES (%s, %s, %s, %s, %s)",
            (
                beneficiary_id,
                owner["uuid"],
                target["uuid"],
                short_name.strip(),
                now,
            ),
        )
        return tool_result(
            status="completed",
            summary=f"Beneficiary {short_name.strip()} was verified and activated for transfers.",
            data={
                "beneficiary": {
                    "full_name": target["Full_Name_Ar"],
                    "full_name_en": target["full_name_en"],
                    "short_name": short_name.strip(),
                    "nafi_iban": normalized,
                    "wallet": "Nafi",
                }
            },
            operation_id=beneficiary_id,
        )

    return await run_in_bank_db(work)


TOOL: BaseTool = StructuredTool.from_function(
    coroutine=add_benefit,
    name="add_benefit",
    description=(
        "Add a beneficiary by unique Nafi IBAN after resolving the authoritative Nafi user. "
        "Only the Nafi IBAN and a short name are required."
    ),
    args_schema=AddBenefitArgs,
)


LIST_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=list_beneficiaries,
    name="list_beneficiaries",
    description=(
        "List the authenticated customer's saved Nafi beneficiaries. "
        "Use this authoritative read when the user asks to view beneficiaries or when a "
        "saved name must be resolved before a transfer. Do not use Qatta tools for this."
    ),
    args_schema=ListBeneficiariesArgs,
)
