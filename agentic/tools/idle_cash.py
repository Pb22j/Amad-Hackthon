"""Three-month idle-cash analysis and wallet-only liquid-savings action.

Linked-bank balances and payment history are analytical inputs only. The
state-changing capability can move money solely from the authenticated user's
Nafi wallet into their Nafi liquid-savings account.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool

from agentic.tools.bank_db import (
    BankConnection,
    BankRow,
    BankToolArgs,
    find_user_by_username,
    money,
    next_reference,
    owner_identity,
    riyadh_now,
    run_in_bank_db,
    timestamp,
    tool_result,
    update_nafi_balance,
    user_accounts,
)


_ANALYSIS_MONTHS = 3
_EMERGENCY_MONTHS = 3
_RECOMMENDATION_TTL = timedelta(hours=24)
_METHODOLOGY_VERSION = "stable-floor-v1"
_INTERNAL_CASH_MOVEMENTS = frozenset(
    {
        "nafi_top_up",
        "nafi_top_up_source",
        "nafi_liquid_savings_debit",
        "nafi_liquid_savings_credit",
    }
)
_SAVINGS_ACCOUNT_TYPES = frozenset(
    {"saving", "savings", "liquid savings", "ادخار", "توفير", "مدخرات"}
)


class AnalyzeIdleCashArgs(BankToolArgs):
    """Idle-cash analysis intentionally uses one audited three-month method."""


class TransferIdleCashArgs(BankToolArgs):
    """Execution resolves the latest active recommendation server-side."""


def _is_savings_account(account: BankRow) -> bool:
    account_type = str(account["account_type"] or "").strip().casefold()
    return account_type in _SAVINGS_ACCOUNT_TYPES


def _month_starts(now: datetime) -> list[datetime]:
    starts: list[datetime] = []
    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(_ANALYSIS_MONTHS):
        starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    starts.reverse()
    return starts


def _projected_month_spend(spent: Decimal, *, month: datetime, now: datetime) -> Decimal:
    if month.year != now.year or month.month != now.month:
        return money(spent)
    elapsed_days = max(now.day, 1)
    days_in_month = monthrange(now.year, now.month)[1]
    return money(spent / elapsed_days * days_in_month)


def _active_savings_account(connection: BankConnection, user_uuid: str) -> BankRow | None:
    return connection.execute(
        "SELECT * FROM nafi_savings_accounts"
        " WHERE user_uuid = %s AND account_type = 'liquid'",
        (user_uuid,),
    ).fetchone()


def _latest_active_recommendation(
    connection: BankConnection, user_uuid: str, *, for_update: bool = False
) -> BankRow | None:
    suffix = " FOR UPDATE" if for_update else ""
    return connection.execute(
        "SELECT * FROM idle_cash_recommendations"
        " WHERE user_uuid = %s AND status = 'active'"
        " ORDER BY created_at DESC LIMIT 1" + suffix,
        (user_uuid,),
    ).fetchone()


def _current_operating_bank_cash(connection: BankConnection, username: str) -> Decimal:
    return sum(
        (
            money(account["balance_sar"])
            for account in user_accounts(connection, username)
            if not _is_savings_account(account)
        ),
        start=money(0),
    )


def _validate_recommended_wallet_action(
    connection: BankConnection,
    *,
    username: str,
    lock: bool,
) -> tuple[BankRow, BankRow, BankRow, Decimal, Decimal] | dict[str, Any]:
    user = find_user_by_username(connection, username)
    if user is None:
        return tool_result(
            status="failed",
            summary="The authenticated customer profile was not found.",
            data={},
            error_code="customer_not_found",
        )
    recommendation = _latest_active_recommendation(
        connection, user["uuid"], for_update=lock
    )
    if recommendation is None:
        return tool_result(
            status="failed",
            summary=(
                "Run the three-month idle-cash analysis first so Nafi can present "
                "an explicit recommendation before any action."
            ),
            data={"bank_accounts_are_read_only": True},
            error_code="idle_cash_recommendation_required",
        )
    now = riyadh_now()
    if recommendation["expires_at"] <= now:
        connection.execute(
            "UPDATE idle_cash_recommendations SET status = 'expired' WHERE uuid = %s",
            (recommendation["uuid"],),
        )
        return tool_result(
            status="failed",
            summary="The idle-cash recommendation expired. Run the analysis again.",
            data={"recommendation_id": str(recommendation["uuid"])},
            error_code="idle_cash_recommendation_expired",
        )
    amount = money(recommendation["recommended_wallet_transfer_sar"])
    if amount <= 0:
        deposit_required = money(recommendation["bank_deposit_required_sar"])
        return tool_result(
            status="failed",
            summary=(
                "No wallet transfer is currently recommended. Deposit the bank-held "
                "idle cash into the Nafi wallet first, then run the analysis again."
                if deposit_required > 0
                else "The current analysis found no regularly idle cash available to move."
            ),
            data={
                "recommendation_id": str(recommendation["uuid"]),
                "bank_deposit_required_sar": str(deposit_required),
                "bank_accounts_are_read_only": True,
            },
            error_code=(
                "wallet_deposit_required" if deposit_required > 0 else "no_idle_cash"
            ),
        )
    savings = _active_savings_account(connection, user["uuid"])
    if savings is None:
        return tool_result(
            status="failed",
            summary="The Nafi liquid-savings account is unavailable.",
            data={},
            error_code="liquid_savings_account_not_found",
        )
    if lock:
        wallet_row = connection.execute(
            "SELECT nafi_balance FROM users WHERE uuid = %s FOR UPDATE",
            (user["uuid"],),
        ).fetchone()
        savings_row = connection.execute(
            "SELECT balance_sar FROM nafi_savings_accounts WHERE uuid = %s FOR UPDATE",
            (savings["uuid"],),
        ).fetchone()
        if wallet_row is None or savings_row is None:
            return tool_result(
                status="failed",
                summary="The Nafi wallet or liquid-savings account is unavailable.",
                data={},
                error_code="nafi_account_not_found",
            )
        wallet_balance = money(wallet_row["nafi_balance"])
        savings_balance = money(savings_row["balance_sar"])
    else:
        wallet_balance = money(user["nafi_balance"])
        savings_balance = money(savings["balance_sar"])

    emergency_target = money(recommendation["emergency_reserve_target_sar"])
    current_bank_cash = _current_operating_bank_cash(connection, username)
    wallet_emergency_required = max(emergency_target - current_bank_cash, money(0))
    safe_wallet_excess = max(wallet_balance - wallet_emergency_required, money(0))
    if amount > safe_wallet_excess:
        return tool_result(
            status="failed",
            summary=(
                "Balances changed and the saved recommendation no longer preserves the "
                "emergency reserve. Run the analysis again."
            ),
            data={
                "recommendation_id": str(recommendation["uuid"]),
                "recommended_amount_sar": str(amount),
                "currently_safe_wallet_amount_sar": str(safe_wallet_excess),
            },
            error_code="idle_cash_recommendation_stale",
        )
    return user, savings, recommendation, wallet_balance, savings_balance


async def analyze_idle_cash() -> dict[str, Any]:
    """Analyze three months of payment data and persist an exact recommendation."""

    username, _ = owner_identity()
    now = riyadh_now()

    def work(connection: BankConnection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        savings = _active_savings_account(connection, user["uuid"])
        if savings is None:
            return tool_result(
                status="failed",
                summary="The Nafi liquid-savings account is unavailable.",
                data={},
                error_code="liquid_savings_account_not_found",
            )

        starts = _month_starts(now)
        month_keys = [start.strftime("%Y-%m") for start in starts]
        rows = connection.execute(
            "SELECT * FROM transactions"
            " WHERE user_uuid = %s AND createdat >= %s AND createdat <= %s"
            " ORDER BY createdat",
            (user["uuid"], timestamp(starts[0]), timestamp(now)),
        ).fetchall()
        monthly = {
            key: {"income": money(0), "spent": money(0), "transactions": 0}
            for key in month_keys
        }
        balance_floors: dict[str, Decimal] = {}
        for row in rows:
            key = row["createdat"].strftime("%Y-%m")
            if key not in monthly:
                continue
            transaction_type = str(row["transaction_type"] or "").casefold()
            account_number = str(row["account_number"])
            balance_after = money(row["balance_after_sar"])
            balance_floors[account_number] = min(
                balance_floors.get(account_number, balance_after), balance_after
            )
            if transaction_type in _INTERNAL_CASH_MOVEMENTS:
                continue
            amount = money(row["amount_sar"])
            monthly[key]["transactions"] += 1
            if row["direction"] == "debit":
                monthly[key]["spent"] += amount
            else:
                monthly[key]["income"] += amount

        observed_projected_spends = [
            _projected_month_spend(monthly[key]["spent"], month=start, now=now)
            for key, start in zip(month_keys, starts, strict=True)
        ]
        months_with_payments = sum(
            1 for key in month_keys if monthly[key]["spent"] > 0
        )
        # A zero month may be genuine or may reflect an incomplete linked-bank
        # feed. Require payment evidence in at least two months, then use the
        # highest observed month for any zero month so the reserve is never
        # reduced merely because data is absent.
        sufficient_history = months_with_payments >= 2
        conservative_missing_month_spend = max(
            observed_projected_spends, default=money(0)
        )
        projected_spends = [
            spend if spend > 0 else conservative_missing_month_spend
            for spend in observed_projected_spends
        ]
        average_monthly_spend = money(
            sum(projected_spends, start=money(0)) / _ANALYSIS_MONTHS
        )
        emergency_target = money(average_monthly_spend * _EMERGENCY_MONTHS)

        linked_bank_operating_cash = money(0)
        linked_bank_liquid_savings = money(0)
        stable_bank_operating_cash = money(0)
        bank_views: list[dict[str, Any]] = []
        for account in user_accounts(connection, username):
            balance = money(account["balance_sar"])
            account_number = str(account["account_number"])
            if _is_savings_account(account):
                linked_bank_liquid_savings += balance
                classification = "existing_liquid_savings"
                stable_floor = money(0)
            else:
                linked_bank_operating_cash += balance
                floor = balance_floors.get(account_number)
                stable_floor = min(balance, floor) if floor is not None else money(0)
                stable_bank_operating_cash += stable_floor
                classification = "operating_cash"
            bank_views.append(
                {
                    "bank_name": account["bank_name_en"] or account["bank_name_ar"],
                    "account_type": account["account_type"],
                    "classification": classification,
                    "balance_sar": str(balance),
                    "stable_floor_sar": str(stable_floor),
                    "read_only": True,
                }
            )

        wallet_balance = money(user["nafi_balance"])
        wallet_floor = min(
            wallet_balance,
            balance_floors.get(str(user["nafi_iban"]), wallet_balance),
        )
        stable_operating_cash = money(stable_bank_operating_cash + wallet_floor)
        regular_idle_cash = (
            max(stable_operating_cash - emergency_target, money(0))
            if sufficient_history
            else money(0)
        )
        wallet_emergency_required = max(
            emergency_target - stable_bank_operating_cash, money(0)
        )
        safe_wallet_excess = max(wallet_balance - wallet_emergency_required, money(0))
        recommended_wallet_transfer = min(regular_idle_cash, safe_wallet_excess)
        bank_deposit_required = max(
            regular_idle_cash - recommended_wallet_transfer, money(0)
        )

        connection.execute(
            "UPDATE idle_cash_recommendations"
            " SET status = CASE WHEN expires_at <= %s THEN 'expired' ELSE 'superseded' END"
            " WHERE user_uuid = %s AND status = 'active'",
            (now, user["uuid"]),
        )
        recommendation_id = str(uuid4())
        expires_at = now + _RECOMMENDATION_TTL
        connection.execute(
            """
            INSERT INTO idle_cash_recommendations
              (uuid, user_uuid, status, methodology_version, analysis_started_at,
               analysis_ended_at, analysis_months, emergency_months,
               average_monthly_spend_sar, emergency_reserve_target_sar,
               stable_operating_cash_sar, regular_idle_cash_sar,
               recommended_wallet_transfer_sar, bank_deposit_required_sar,
               wallet_balance_snapshot_sar, wallet_liquid_savings_snapshot_sar,
               linked_bank_operating_cash_sar, linked_bank_liquid_savings_sar,
               created_at, expires_at)
            VALUES
              (%s, %s, 'active', %s, %s, %s, 3, 3, %s, %s, %s, %s,
               %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                recommendation_id,
                user["uuid"],
                _METHODOLOGY_VERSION,
                starts[0],
                now,
                average_monthly_spend,
                emergency_target,
                stable_operating_cash,
                regular_idle_cash,
                recommended_wallet_transfer,
                bank_deposit_required,
                wallet_balance,
                money(savings["balance_sar"]),
                linked_bank_operating_cash,
                linked_bank_liquid_savings,
                now,
                expires_at,
            ),
        )

        monthly_view = [
            {
                "month": key,
                "income_sar": str(monthly[key]["income"]),
                "spent_sar": str(monthly[key]["spent"]),
                "projected_full_month_spend_sar": str(observed),
                "reserve_month_spend_sar": str(projected),
                "imputed_for_reserve": observed == 0 and projected > 0,
                "transaction_count": monthly[key]["transactions"],
            }
            for key, observed, projected in zip(
                month_keys,
                observed_projected_spends,
                projected_spends,
                strict=True,
            )
        ]
        if not sufficient_history:
            recommendation_summary = (
                "No transfer is recommended because fewer than two of the three "
                "analyzed months contain payment history."
            )
        elif recommended_wallet_transfer > 0:
            recommendation_summary = (
                f"Move {recommended_wallet_transfer} SAR from the Nafi wallet to "
                f"Nafi Liquid Savings while retaining {emergency_target} SAR as "
                "the three-month emergency target across operating cash."
            )
        elif bank_deposit_required > 0:
            recommendation_summary = (
                f"{bank_deposit_required} SAR appears regularly idle in linked-bank "
                "cash, but it must be deposited into the Nafi wallet before Nafi can act."
            )
        else:
            recommendation_summary = "No regularly idle cash is currently available to move."

        data = {
            "recommendation_id": recommendation_id,
            "recommendation_expires_at": expires_at,
            "methodology": {
                "version": _METHODOLOGY_VERSION,
                "analysis_months": _ANALYSIS_MONTHS,
                "emergency_months": _EMERGENCY_MONTHS,
                "definition": (
                    "Regular idle cash is the stable three-month operating-cash floor "
                    "above a three-month projected spending reserve. A zero month is "
                    "conservatively imputed with the highest observed monthly spend."
                ),
            },
            "history_sufficient": sufficient_history,
            "months_with_payment_data": months_with_payments,
            "monthly_cash_flow": monthly_view,
            "average_monthly_spend_sar": str(average_monthly_spend),
            "emergency_reserve_target_sar": str(emergency_target),
            "stable_operating_cash_sar": str(stable_operating_cash),
            "regular_idle_cash_sar": str(regular_idle_cash),
            "current_nafi_wallet_balance_sar": str(wallet_balance),
            "current_nafi_liquid_savings_sar": str(money(savings["balance_sar"])),
            "recommended_wallet_transfer_sar": str(recommended_wallet_transfer),
            "bank_deposit_required_sar": str(bank_deposit_required),
            "linked_bank_accounts": bank_views,
            "linked_bank_accounts_are_read_only": True,
            "no_bank_money_moved": True,
            "recommendation": recommendation_summary,
            "explicit_consent_required": recommended_wallet_transfer > 0,
            "consent_question": (
                f"Would you like Nafi to transfer {recommended_wallet_transfer} SAR "
                "from your Nafi wallet to Nafi Liquid Savings?"
                if recommended_wallet_transfer > 0
                else None
            ),
            "consent_question_ar": (
                f"هل تريد من نافي تحويل {recommended_wallet_transfer} ريال من "
                "محفظة نافي إلى مدخرات نافي السائلة؟"
                if recommended_wallet_transfer > 0
                else None
            ),
            "wallet_deposit_notice": (
                "Nafi only performs this action on money already in the Nafi wallet. "
                "To let Nafi act on idle cash held at a linked bank, first deposit "
                "that money into the wallet, then run the analysis again."
            ),
            "wallet_deposit_notice_ar": (
                "نافي ينفذ هذا الإجراء فقط على الأموال الموجودة بالفعل في محفظة نافي. "
                "إذا أردت أن يتصرف نافي في سيولة خاملة موجودة في بنك مرتبط، فأودعها "
                "أولاً في المحفظة ثم أعد التحليل."
            ),
        }
        return tool_result(
            status="completed",
            summary=recommendation_summary,
            data=data,
            operation_id=next_reference(connection, "idle-cash-analysis"),
        )

    return await run_in_bank_db(work)


async def preflight_transfer_idle_cash_to_savings() -> dict[str, Any]:
    """Resolve and validate the latest recommendation before exact confirmation."""

    username, _ = owner_identity()

    def work(connection: BankConnection) -> dict[str, Any]:
        validation = _validate_recommended_wallet_action(
            connection, username=username, lock=False
        )
        if isinstance(validation, dict):
            return validation
        _, savings, recommendation, wallet_balance, savings_balance = validation
        amount = money(recommendation["recommended_wallet_transfer_sar"])
        return tool_result(
            status="completed",
            summary="The recommended wallet-only liquid-savings transfer is eligible.",
            data={
                "recommendation_id": str(recommendation["uuid"]),
                "confirmation_arguments": {
                    "recommendation_id": str(recommendation["uuid"]),
                    "amount_sar": str(amount),
                    "source": "Nafi Wallet",
                    "destination": savings["name"],
                    "emergency_reserve_target_sar": str(
                        money(recommendation["emergency_reserve_target_sar"])
                    ),
                },
                "wallet_balance_sar": str(wallet_balance),
                "liquid_savings_balance_sar": str(savings_balance),
                "bank_accounts_are_read_only": True,
            },
        )

    return await run_in_bank_db(work)


async def transfer_idle_cash_to_savings() -> dict[str, Any]:
    """Move the latest recommended amount within Nafi; never debit a linked bank."""

    username, _ = owner_identity()

    def work(connection: BankConnection) -> dict[str, Any]:
        validation = _validate_recommended_wallet_action(
            connection, username=username, lock=True
        )
        if isinstance(validation, dict):
            return validation
        user, savings, recommendation, wallet_balance, savings_balance = validation
        amount = money(recommendation["recommended_wallet_transfer_sar"])
        wallet_after = wallet_balance - amount
        savings_after = savings_balance + amount
        reference = next_reference(connection, "idle-cash-savings")
        now = riyadh_now()
        update_nafi_balance(connection, user, wallet_after)
        connection.execute(
            "UPDATE nafi_savings_accounts"
            " SET balance_sar = %s, updated_at = %s WHERE uuid = %s",
            (savings_after, now, savings["uuid"]),
        )
        connection.execute(
            """
            INSERT INTO transactions
              (uuid, user_uuid, account_number, direction, transaction_type,
               amount_sar, counterparty_name, counterparty_account, description,
               category, balance_after_sar, reference, createdat)
            VALUES
              (%s, %s, %s, 'debit', 'nafi_liquid_savings_debit', %s,
               %s, %s, 'Move idle cash to Nafi Liquid Savings',
               'مدخرات سائلة', %s, %s, %s),
              (%s, %s, %s, 'credit', 'nafi_liquid_savings_credit', %s,
               'Nafi Wallet', %s, 'Idle cash added to Nafi Liquid Savings',
               'مدخرات سائلة', %s, %s, %s)
            """,
            (
                str(uuid4()),
                user["uuid"],
                user["nafi_iban"],
                amount,
                savings["name"],
                savings["account_number"],
                wallet_after,
                reference,
                now,
                str(uuid4()),
                user["uuid"],
                savings["account_number"],
                amount,
                user["nafi_iban"],
                savings_after,
                reference,
                now,
            ),
        )
        connection.execute(
            "UPDATE idle_cash_recommendations"
            " SET status = 'executed', executed_at = %s, execution_reference = %s"
            " WHERE uuid = %s",
            (now, reference, recommendation["uuid"]),
        )
        return tool_result(
            status="completed",
            summary=f"Moved {amount} SAR from the Nafi wallet to Nafi Liquid Savings.",
            data={
                "reference": reference,
                "recommendation_id": str(recommendation["uuid"]),
                "amount_sar": str(amount),
                "new_nafi_wallet_balance_sar": str(wallet_after),
                "new_nafi_liquid_savings_balance_sar": str(savings_after),
                "linked_bank_accounts_changed": False,
            },
            receipt_id=f"receipt-{reference}",
            operation_id=reference,
        )

    return await run_in_bank_db(work)


ANALYZE_IDLE_CASH_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=analyze_idle_cash,
    name="analyze_idle_cash",
    description=(
        "Analyze exactly three months of the authenticated user's payment data and "
        "read-only linked-bank balances, estimate the stable regularly idle cash, "
        "retain a three-month emergency reserve, and recommend an exact wallet-only "
        "amount for Nafi Liquid Savings. Always use this for idle-cash, excess-cash, "
        "cash-sweep, or emergency-buffer recommendations."
    ),
    args_schema=AnalyzeIdleCashArgs,
)

TRANSFER_IDLE_CASH_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=transfer_idle_cash_to_savings,
    name="transfer_idle_cash_to_savings",
    description=(
        "Execute the latest active idle-cash recommendation by moving its exact "
        "server-calculated amount from the Nafi wallet to Nafi Liquid Savings. "
        "It never debits a linked bank and requires explicit confirmation and OTP."
    ),
    args_schema=TransferIdleCashArgs,
)
