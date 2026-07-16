"""Fund the authenticated user's Nafi wallet from one owned linked bank account."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field, field_validator

from agentic.tools.bank_db import (
    BankConnection,
    BankRow,
    BankToolArgs,
    find_user_by_username,
    money,
    next_reference,
    masked_account_number,
    owner_identity,
    resolve_account_candidates,
    run_in_bank_db,
    resolve_user_account,
    timestamp,
    tool_result,
    update_nafi_balance,
    user_accounts,
)
from agentic.tools.entity_resolution import normalize_entity_text


class FundNafiWalletArgs(BankToolArgs):
    source_account: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "The linked bank account to debit, using the bank name, account type, "
            "masked/last-four account number, or 'primary', exactly as the user stated it."
        ),
    )
    amount: float = Field(description="Amount to deposit into the Nafi wallet in SAR.")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0 or value > 9_999_999_999:
            raise ValueError("amount must be positive and no more than 9,999,999,999 SAR")
        return value


async def source_account_is_grounded(
    source_account: str, user_statements: tuple[str, ...]
) -> bool:
    """Verify a canonical account value resolves to an account named by the user."""

    username, _ = owner_identity()

    def work(connection: BankConnection) -> bool:
        accounts = user_accounts(connection, username)
        canonical = resolve_account_candidates(accounts, source_account).match
        if canonical is None:
            return False
        canonical_id = str(canonical["uuid"])
        statement_matches: list[set[str]] = []
        for statement in user_statements:
            matches: set[str] = set()
            tokens = normalize_entity_text(statement).split()
            checked = 0
            for width in range(1, min(4, len(tokens)) + 1):
                for start in range(0, len(tokens) - width + 1):
                    phrase = " ".join(tokens[start : start + width])
                    if not any(character.isalpha() for character in phrase):
                        continue
                    checked += 1
                    if checked > 120:
                        break
                    resolved = resolve_account_candidates(accounts, phrase).match
                    if resolved is not None:
                        matches.add(str(resolved["uuid"]))
                if checked > 120:
                    break
            statement_matches.append(matches)

        # The current request is authoritative when it names an account. Only
        # fall back to prior statements when the current request names none.
        current_matches = statement_matches[0] if statement_matches else set()
        if current_matches:
            return current_matches == {canonical_id}
        prior_matches = set().union(*statement_matches[1:]) if len(statement_matches) > 1 else set()
        return prior_matches == {canonical_id}

    return await run_in_bank_db(work)


def _validate_deposit(
    connection: BankConnection,
    *,
    username: str,
    source_account: str,
    amount: Decimal,
) -> tuple[BankRow, BankRow, Decimal, Decimal] | dict[str, Any]:
    owner = find_user_by_username(connection, username)
    if owner is None:
        return tool_result(
            status="failed",
            summary="The authenticated customer profile was not found.",
            data={},
            error_code="customer_not_found",
        )
    resolution = resolve_user_account(
        connection, username=username, account=source_account
    )
    account = resolution.match
    if account is None:
        if resolution.candidates:
            return tool_result(
                status="failed",
                summary="More than one linked bank account matches the requested source.",
                data={
                    "source_account": source_account,
                    "candidates": [
                        {
                            "bank_name": candidate["bank_name_en"]
                            or candidate["bank_name_ar"],
                            "bank_name_ar": candidate["bank_name_ar"],
                            "account_type": candidate["account_type"],
                            "masked_account_number": masked_account_number(
                                str(candidate["account_number"])
                            ),
                            "available_balance_sar": str(money(candidate["balance_sar"])),
                        }
                        for candidate in resolution.candidates
                    ],
                },
                error_code="source_account_ambiguous",
            )
        return tool_result(
            status="failed",
            summary="The selected linked bank account was not found for this customer.",
            data={"source_account": source_account},
            error_code="source_account_not_found",
        )
    bank_balance = money(account["balance_sar"])
    if amount > bank_balance:
        return tool_result(
            status="failed",
            summary="The selected bank account does not have enough balance for this deposit.",
            data={
                "requested_amount_sar": str(amount),
                "available_balance_sar": str(bank_balance),
                "masked_account_number": masked_account_number(
                    str(account["account_number"])
                ),
            },
            error_code="insufficient_bank_funds",
        )
    return owner, account, money(owner["nafi_balance"]), bank_balance


async def preflight_fund_nafi_wallet(
    source_account: str, amount: float | Decimal
) -> dict[str, Any]:
    """Validate account ownership and funds before requesting confirmation."""

    username, _ = owner_identity()
    normalized_amount = money(amount)

    def work(connection: BankConnection) -> dict[str, Any]:
        validation = _validate_deposit(
            connection,
            username=username,
            source_account=source_account,
            amount=normalized_amount,
        )
        if isinstance(validation, dict):
            return validation
        _, account, wallet_balance, bank_balance = validation
        return tool_result(
            status="completed",
            summary="Wallet deposit prerequisites validated.",
            data={
                "amount_sar": str(normalized_amount),
                "current_nafi_balance_sar": str(wallet_balance),
                "resolved_source": {
                    "bank_name": account["bank_name_en"] or account["bank_name_ar"],
                    "bank_name_ar": account["bank_name_ar"],
                    "account_type": account["account_type"],
                    "masked_account_number": masked_account_number(
                        str(account["account_number"])
                    ),
                    "available_balance_sar": str(bank_balance),
                },
            },
        )

    return await run_in_bank_db(work)


async def fund_nafi_wallet(
    source_account: str, amount: float | Decimal
) -> dict[str, Any]:
    """Atomically debit one linked bank account and credit the Nafi wallet."""

    username, _ = owner_identity()
    normalized_amount = money(amount)

    def work(connection: BankConnection) -> dict[str, Any]:
        validation = _validate_deposit(
            connection,
            username=username,
            source_account=source_account,
            amount=normalized_amount,
        )
        if isinstance(validation, dict):
            return validation
        owner, account, wallet_balance, bank_balance = validation
        # Re-lock both authoritative balances after preflight. The transaction
        # then rechecks the selected bank balance before either update occurs.
        locked_owner = connection.execute(
            "SELECT nafi_balance FROM users WHERE uuid = %s FOR UPDATE",
            (owner["uuid"],),
        ).fetchone()
        locked_account = connection.execute(
            "SELECT balance_sar FROM bank_accounts WHERE uuid = %s FOR UPDATE",
            (account["uuid"],),
        ).fetchone()
        if locked_owner is None or locked_account is None:
            return tool_result(
                status="failed",
                summary="The selected account is no longer available.",
                data={},
                error_code="source_account_not_found",
            )
        wallet_balance = money(locked_owner["nafi_balance"])
        bank_balance = money(locked_account["balance_sar"])
        if normalized_amount > bank_balance:
            return tool_result(
                status="failed",
                summary="The selected bank account no longer has enough balance.",
                data={
                    "requested_amount_sar": str(normalized_amount),
                    "available_balance_sar": str(bank_balance),
                },
                error_code="insufficient_bank_funds",
            )

        bank_balance_after = bank_balance - normalized_amount
        wallet_balance_after = wallet_balance + normalized_amount
        reference = next_reference(connection, "wallet-deposit")
        now = timestamp()
        connection.execute(
            "UPDATE bank_accounts SET balance_sar = %s WHERE uuid = %s",
            (bank_balance_after, account["uuid"]),
        )
        update_nafi_balance(connection, owner, wallet_balance_after)
        connection.execute(
            """
            INSERT INTO transactions
              (uuid, user_uuid, account_number, direction, transaction_type,
               amount_sar, counterparty_name, counterparty_account, description,
               category, balance_after_sar, reference, createdat)
            VALUES
              (%s, %s, %s, 'debit', 'nafi_top_up_source', %s, 'Nafi Wallet',
               %s, 'Fund Nafi wallet from linked bank', 'شحن المحفظة', %s, %s, %s),
              (%s, %s, %s, 'credit', 'nafi_top_up', %s, %s, %s,
               'Nafi wallet funding', 'شحن المحفظة', %s, %s, %s)
            """,
            (
                str(uuid4()), owner["uuid"], account["account_number"],
                normalized_amount, owner["nafi_iban"], bank_balance_after, reference, now,
                str(uuid4()), owner["uuid"], owner["nafi_iban"], normalized_amount,
                account["bank_name_ar"], account["account_number"],
                wallet_balance_after, reference, now,
            ),
        )
        return tool_result(
            status="completed",
            summary=f"Added {normalized_amount} SAR to the Nafi wallet.",
            data={
                "reference": reference,
                "amount_sar": str(normalized_amount),
                "source_bank": account["bank_name_en"] or account["bank_name_ar"],
                "source_masked_account_number": masked_account_number(
                    str(account["account_number"])
                ),
                "source_bank_balance_sar": str(bank_balance_after),
                "new_nafi_balance_sar": str(wallet_balance_after),
            },
            receipt_id=f"receipt-{reference}",
            operation_id=reference,
        )

    return await run_in_bank_db(work)


TOOL: BaseTool = StructuredTool.from_function(
    coroutine=fund_nafi_wallet,
    name="fund_nafi_wallet",
    description=(
        "Deposit money into the authenticated user's Nafi wallet by debiting one selected, "
        "owned linked bank account. Use only when the user explicitly asks to add, fund, "
        "deposit, or top up their Nafi wallet. The user must specify the source bank/account "
        "and amount. Account ownership and available bank funds are verified before exact "
        "confirmation and OTP; execution atomically debits the bank and credits nafi_balance."
    ),
    args_schema=FundNafiWalletArgs,
)
