"""``analyze_finances`` — deterministic financial insights from the ledger.

The tool computes everything from the database with plain arithmetic — no
model is involved — so every number the agent narrates is exact and
reproducible: per-month income/spend/net and savings rate, category trends
with month-over-month change, top spending counterparties, auto-detected
recurring commitments, an end-of-month spend projection, unpaid fatoorah
exposure, and deterministic insight flags the agent can explain. The agent's
own model turns this data into the advisory answer.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

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
)

_TOP_COUNTERPARTIES = 5
_MAX_FOCUS_TRANSACTIONS = 20
_RECURRING_MIN_MONTHS = 2
_SPIKE_THRESHOLD_PERCENT = 25
_SPIKE_MIN_AMOUNT = Decimal("100")
_LOW_SAVINGS_RATE_PERCENT = 10
_DUE_SOON_DAYS = 14
_INTERNAL_CASH_MOVEMENTS = {
    "nafi_top_up",
    "nafi_top_up_source",
    "nafi_liquid_savings_debit",
    "nafi_liquid_savings_credit",
}


class AnalyzeFinancesArgs(BankToolArgs):
    months: int = Field(
        default=3,
        ge=1,
        le=12,
        description="How many calendar months back to analyze, including the current one.",
    )
    focus_category: str | None = Field(
        default=None,
        max_length=100,
        description="Optional category (e.g. مطاعم, فواتير) to break down in detail.",
    )


def _month_starts(now: datetime, months: int) -> list[datetime]:
    """Month starts from oldest to the current month, in Riyadh time."""

    starts: list[datetime] = []
    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for _ in range(months):
        starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    starts.reverse()
    return starts


def _percent(part: Decimal, whole: Decimal) -> str:
    return str(round(float(part / whole * 100), 1))


async def analyze_finances(
    months: int = 3, focus_category: str | None = None
) -> dict[str, Any]:
    """Analyze the user's ledger over the last ``months`` calendar months."""

    username, _ = owner_identity()
    now = riyadh_now()
    focus = focus_category.strip() if focus_category else None

    def work(connection: BankConnection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )

        starts = _month_starts(now, months)
        month_keys = [start.strftime("%Y-%m") for start in starts]
        rows = connection.execute(
            "SELECT * FROM transactions WHERE user_uuid = %s AND createdAt >= %s"
            " ORDER BY createdAt",
            (user["uuid"], timestamp(starts[0])),
        ).fetchall()

        zero = Decimal("0.00")
        monthly = {
            key: {"income": zero, "spent": zero} for key in month_keys
        }
        categories: dict[str, dict[str, Decimal]] = {}
        counterparties: dict[str, dict[str, Any]] = {}
        largest_expense: BankRow | None = None
        focus_transactions: list[dict[str, Any]] = []
        for row in rows:
            if str(row["Transaction_Type"] or "").casefold() in _INTERNAL_CASH_MOVEMENTS:
                continue
            key = row["createdAt"].strftime("%Y-%m")
            if key not in monthly:
                continue
            amount = money(row["Amount_SAR"])
            bucket = monthly[key]
            category = categories.setdefault(
                row["Category"], {month_key: zero for month_key in month_keys}
            )
            if row["direction"] == "debit":
                bucket["spent"] += amount
                category[key] += amount
                name = row["Counterparty_Name"] or row["Description"]
                entry = counterparties.setdefault(
                    name, {"total": zero, "count": 0, "months": set()}
                )
                entry["total"] += amount
                entry["count"] += 1
                entry["months"].add(key)
                if largest_expense is None or amount > money(largest_expense["Amount_SAR"]):
                    largest_expense = row
            else:
                bucket["income"] += amount
            if focus and row["Category"] == focus and len(focus_transactions) < _MAX_FOCUS_TRANSACTIONS:
                focus_transactions.append(
                    {
                        "date": row["createdAt"],
                        "direction": row["direction"],
                        "amount_sar": str(amount),
                        "counterparty": row["Counterparty_Name"],
                        "description": row["Description"],
                    }
                )

        monthly_view = []
        total_income = zero
        total_spent = zero
        for key in month_keys:
            income, spent = monthly[key]["income"], monthly[key]["spent"]
            total_income += income
            total_spent += spent
            monthly_view.append(
                {
                    "month": key,
                    "income_sar": str(income),
                    "spent_sar": str(spent),
                    "net_sar": str(income - spent),
                    "savings_rate_percent": (
                        _percent(income - spent, income) if income > 0 else None
                    ),
                }
            )

        current_key, previous_key = month_keys[-1], (
            month_keys[-2] if len(month_keys) > 1 else None
        )
        category_trends = {}
        flags: list[dict[str, str]] = []
        for name, per_month in sorted(categories.items()):
            this_month = per_month[current_key]
            previous = per_month[previous_key] if previous_key else zero
            change = (
                str(round(float((this_month - previous) / previous * 100), 1))
                if previous > 0
                else None
            )
            category_trends[name] = {
                "total_sar": str(sum(per_month.values(), zero)),
                "this_month_sar": str(this_month),
                "previous_month_sar": str(previous),
                "change_percent": change,
            }
            if (
                change is not None
                and float(change) >= _SPIKE_THRESHOLD_PERCENT
                and this_month >= _SPIKE_MIN_AMOUNT
            ):
                flags.append(
                    {
                        "code": "spending_up",
                        "detail": f"{name}: {change}% مقارنة بالشهر الماضي",
                    }
                )

        top = sorted(
            counterparties.items(), key=lambda item: item[1]["total"], reverse=True
        )[:_TOP_COUNTERPARTIES]
        top_view = [
            {"name": name, "total_sar": str(entry["total"]), "count": entry["count"]}
            for name, entry in top
        ]

        recurring = []
        recurring_monthly_total = zero
        for name, entry in sorted(counterparties.items()):
            active_months = len(entry["months"])
            if active_months >= min(months, _RECURRING_MIN_MONTHS) and months > 1:
                average = money(entry["total"] / active_months)
                recurring.append(
                    {
                        "name": name,
                        "months_seen": active_months,
                        "average_monthly_sar": str(average),
                    }
                )
                recurring_monthly_total += average

        # End-of-month projection from the current month's daily average.
        days_in_month = monthrange(now.year, now.month)[1]
        spent_so_far = monthly[current_key]["spent"]
        daily_average = money(spent_so_far / now.day)
        projected_spend = money(daily_average * days_in_month)
        balance = money(user["nafi_balance"])
        remaining_projected = projected_spend - spent_so_far
        projection = {
            "spent_so_far_sar": str(spent_so_far),
            "daily_average_sar": str(daily_average),
            "projected_month_total_sar": str(projected_spend),
            "days_elapsed": now.day,
            "days_in_month": days_in_month,
            "balance_covers_projection": remaining_projected <= balance,
        }
        if remaining_projected > balance:
            flags.append(
                {
                    "code": "projection_exceeds_balance",
                    "detail": (
                        f"الصرف المتوقع المتبقي {remaining_projected} أعلى من الرصيد {balance}"
                    ),
                }
            )

        unpaid_rows = connection.execute(
            "SELECT * FROM fatoorahs WHERE user_uuid = %s AND status = 'unpaid'"
            " ORDER BY dueDate",
            (user["uuid"],),
        ).fetchall()
        unpaid_total = sum((money(row["Amount_SAR"]) for row in unpaid_rows), zero)
        due_soon_cutoff = now + timedelta(days=_DUE_SOON_DAYS)
        due_soon = [
            row for row in unpaid_rows if row["dueDate"] and row["dueDate"] <= due_soon_cutoff
        ]
        if due_soon:
            flags.append(
                {
                    "code": "unpaid_bills_due_soon",
                    "detail": (
                        f"{len(due_soon)} فاتورة غير مدفوعة تستحق خلال "
                        f"{_DUE_SOON_DAYS} يوم بمجموع "
                        f"{sum((money(row['Amount_SAR']) for row in due_soon), zero)}"
                    ),
                }
            )

        if total_income > 0:
            overall_rate = float(
                (total_income - total_spent) / total_income * 100
            )
            if overall_rate < _LOW_SAVINGS_RATE_PERCENT:
                flags.append(
                    {
                        "code": "savings_rate_below_10",
                        "detail": f"معدل الادخار للفترة {round(overall_rate, 1)}%",
                    }
                )

        data: dict[str, Any] = {
            "period_months": months,
            "currency": "SAR",
            "current_nafi_balance_sar": str(balance),
            "current_balance_sar": str(balance),
            "totals": {
                "income_sar": str(total_income),
                "spent_sar": str(total_spent),
                "net_sar": str(total_income - total_spent),
                "savings_rate_percent": (
                    _percent(total_income - total_spent, total_income)
                    if total_income > 0
                    else None
                ),
            },
            "monthly": monthly_view,
            "category_trends": category_trends,
            "top_counterparties": top_view,
            "recurring_commitments": recurring,
            "recurring_monthly_total_sar": str(recurring_monthly_total),
            "current_month_projection": projection,
            "unpaid_fatoorahs": {
                "count": len(unpaid_rows),
                "total_sar": str(unpaid_total),
                "soonest_due": unpaid_rows[0]["dueDate"] if unpaid_rows else None,
            },
            "largest_expense": (
                {
                    "amount_sar": str(money(largest_expense["Amount_SAR"])),
                    "counterparty": largest_expense["Counterparty_Name"],
                    "date": largest_expense["createdAt"],
                }
                if largest_expense is not None
                else None
            ),
            "flags": flags,
        }
        if focus:
            data["focus_category"] = {
                "category": focus,
                "transactions": focus_transactions,
            }

        return tool_result(
            status="completed",
            summary=(
                f"Analyzed {months} months: income {total_income} SAR, spent "
                f"{total_spent} SAR, {len(flags)} insight flags."
            ),
            data=data,
            operation_id=next_reference(connection, "analysis"),
        )

    return await run_in_bank_db(work)


TOOL: BaseTool = StructuredTool.from_function(
    coroutine=analyze_finances,
    name="analyze_finances",
    description=(
        "Analyze the authenticated user's finances over recent months: income vs "
        "spending and savings rate per month, category trends with month-over-month "
        "change, top spending destinations, detected recurring commitments, an "
        "end-of-month spend projection, unpaid bill exposure, and deterministic "
        "insight flags. Use it for advisory questions like 'أين تذهب أموالي؟' or "
        "'هل أستطيع التوفير؟'."
    ),
    args_schema=AnalyzeFinancesArgs,
)
