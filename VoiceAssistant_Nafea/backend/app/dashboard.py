"""Read-only, authenticated dashboard projection over the shared banking database."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row


_BANKS: tuple[tuple[tuple[str, ...], str, str, str | None], ...] = (
    (("الراجحي", "rajhi"), "rajhi", "Al Rajhi Bank", "890"),
    (("الإنماء", "الانماء", "alinma"), "alinma", "Alinma Bank", "132"),
    (("السعودي الأول", "sab"), "sab", "Saudi Awwal Bank", None),
    (("الأهلي", "snb"), "snb", "Saudi National Bank", None),
    (("الرياض", "riyad"), "riyad", "Riyad Bank", None),
    (("البلاد", "albilad"), "albilad", "Bank Albilad", None),
    (("الفرنسي", "fransi"), "fransi", "Banque Saudi Fransi", None),
    (("العربي الوطني", "anb"), "anb", "Arab National Bank", None),
)

_ASSET_NAMES_AR = {
    "ARAMCO": "أرامكو السعودية",
    "ALRAJHI": "مصرف الراجحي",
    "SABIC": "سابك",
}


def _money(value: Any) -> str:
    return format(Decimal(str(value or 0)).quantize(Decimal("0.01")), "f")


def _percent(numerator: Decimal, denominator: Decimal) -> float:
    if denominator == 0:
        return 0.0
    return float((numerator / denominator * Decimal("100")).quantize(Decimal("0.1")))


def _masked_account(account_number: str) -> str:
    normalized = "".join(account_number.split())
    if len(normalized) <= 8:
        return normalized
    return f"{normalized[:4]}{'*' * (len(normalized) - 8)}{normalized[-4:]}"


def _bank(bank_name_ar: str | None) -> dict[str, str | None]:
    raw = (bank_name_ar or "").strip()
    folded = raw.casefold()
    for needles, bank_id, name_en, code in _BANKS:
        if any(needle.casefold() in folded for needle in needles):
            return {
                "bank_id": bank_id,
                "bank_name": name_en,
                "bank_name_ar": raw or name_en,
                "code": code,
            }
    return {
        "bank_id": "generic",
        "bank_name": raw or "Connected bank",
        "bank_name_ar": raw or "بنك مرتبط",
        "code": None,
    }


class DashboardStore:
    """Build a single customer dashboard from trusted session identity."""

    def __init__(self, database_url: str) -> None:
        normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        if not normalized.startswith("postgresql://"):
            raise ValueError("DashboardStore requires a PostgreSQL URL")
        self.database_url = normalized

    def snapshot(self, *, user_id: str, tenant_id: str) -> dict[str, Any]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.execute("SET TIME ZONE 'Asia/Riyadh'")
            user = connection.execute(
                """
                SELECT uuid::text AS id, username::text, full_name_ar, full_name_en,
                       nafi_iban
                FROM users
                WHERE username = %s
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if user is None:
                raise LookupError("Authenticated customer profile was not found")
            accounts = connection.execute(
                """SELECT uuid::text AS id, bank_name_ar, account_number,
                          account_type, balance_sar, is_primary
                     FROM bank_accounts WHERE user_uuid = %s
                     ORDER BY is_primary DESC, uuid""",
                (user["id"],),
            ).fetchall()

            holdings = connection.execute(
                """
                SELECT h.symbol, h.quantity, h.average_cost_sar, a.name, a.price_sar
                FROM investment_holdings h
                JOIN investment_assets a ON a.symbol = h.symbol
                WHERE h.user_uuid = %s AND h.quantity > 0 AND a.status = 'active'
                ORDER BY h.symbol
                """,
                (user["id"],),
            ).fetchall()
            transactions = connection.execute(
                """
                SELECT uuid::text AS id, direction, transaction_type, amount_sar,
                       counterparty_name, description, createdat
                FROM transactions
                WHERE user_uuid = %s
                ORDER BY createdat DESC
                LIMIT 4
                """,
                (user["id"],),
            ).fetchall()
            bills = connection.execute(
                """
                SELECT uuid::text AS id, biller_name_ar, amount_sar, duedate
                FROM fatoorahs
                WHERE user_uuid = %s AND status = 'unpaid'
                ORDER BY duedate NULLS LAST, createdat DESC
                LIMIT 2
                """,
                (user["id"],),
            ).fetchall()
            recipients = connection.execute(
                """
                SELECT b.uuid::text AS id, target.full_name_ar AS full_name,
                       b.short_name::text, account.bank_name_ar
                FROM beneficiaries b
                JOIN users target ON target.uuid = b.beneficiary_uuid
                JOIN bank_accounts account
                  ON account.user_uuid = target.uuid AND account.is_primary
                WHERE b.owner_uuid = %s
                ORDER BY b.createdat DESC
                LIMIT 3
                """,
                (user["id"],),
            ).fetchall()
            stats = connection.execute(
                """
                SELECT
                  COALESCE(SUM(amount_sar) FILTER (
                    WHERE direction = 'debit'
                      AND createdat >= date_trunc('month', CURRENT_TIMESTAMP)
                  ), 0) AS monthly_spend_sar,
                  (SELECT COUNT(*) FROM fatoorahs
                    WHERE user_uuid = %s AND status = 'unpaid') AS unpaid_bills,
                  (SELECT COUNT(*) FROM beneficiaries
                    WHERE owner_uuid = %s) AS saved_recipients
                FROM transactions
                WHERE user_uuid = %s
                """,
                (user["id"], user["id"], user["id"]),
            ).fetchone()

        balance = sum(
            (Decimal(str(account["balance_sar"])) for account in accounts),
            start=Decimal("0"),
        )
        portfolio_value = Decimal("0")
        portfolio_cost = Decimal("0")
        holding_values: list[tuple[dict[str, Any], Decimal, Decimal]] = []
        for holding in holdings:
            quantity = Decimal(str(holding["quantity"]))
            price = Decimal(str(holding["price_sar"]))
            average_cost = Decimal(str(holding["average_cost_sar"]))
            market_value = quantity * price
            cost_value = quantity * average_cost
            portfolio_value += market_value
            portfolio_cost += cost_value
            holding_values.append((holding, market_value, cost_value))

        portfolio_gain = portfolio_value - portfolio_cost
        net_worth = balance + portfolio_value
        net_basis = balance + portfolio_cost
        account_views = [
            {
                "id": account["id"],
                **_bank(account["bank_name_ar"]),
                "account_type": account["account_type"],
                "masked_account_number": _masked_account(account["account_number"]),
                "status": "active",
            }
            for account in accounts
        ]

        recent = []
        for transaction in transactions:
            transaction_type = str(transaction["transaction_type"] or "").casefold()
            if transaction["direction"] == "credit":
                kind = "deposit"
            elif "transfer" in transaction_type or "gift" in transaction_type:
                kind = "transfer"
            else:
                kind = "payment"
            counterparty = transaction["counterparty_name"] or transaction["description"]
            recent.append(
                {
                    "id": transaction["id"],
                    "kind": kind,
                    "counterparty": counterparty,
                    "amount_sar": _money(transaction["amount_sar"]),
                    "occurred_at": transaction["createdat"].isoformat(),
                }
            )

        upcoming = []
        for bill in bills:
            biller = str(bill["biller_name_ar"])
            upcoming.append(
                {
                    "id": bill["id"],
                    "icon": "phone" if "stc" in biller.casefold() or "جوال" in biller else "utilities",
                    "biller": biller,
                    "amount_sar": _money(bill["amount_sar"]),
                    "due_at": bill["duedate"].isoformat() if bill["duedate"] else None,
                }
            )

        return {
            "as_of": datetime.now(timezone.utc).isoformat(),
            "user": {
                "name": user["full_name_en"] or user["full_name_ar"],
                "name_ar": user["full_name_ar"],
                "initial": (user["full_name_en"] or user["full_name_ar"] or user_id)[0],
            },
            "net_worth": {
                "amount_sar": _money(net_worth),
                "delta_percent": _percent(net_worth - net_basis, net_basis),
            },
            "accounts": account_views,
            "portfolio": {
                "value_sar": _money(portfolio_value),
                "total_return_percent": _percent(portfolio_gain, portfolio_cost),
                "holdings": [
                    {
                        "ticker": holding["symbol"],
                        "name": holding["name"],
                        "name_ar": _ASSET_NAMES_AR.get(holding["symbol"], holding["name"]),
                        "weight_percent": _percent(market_value, portfolio_value),
                        "return_percent": _percent(market_value - cost_value, cost_value),
                    }
                    for holding, market_value, cost_value in holding_values
                ],
            },
            "activity": {
                "recent": recent,
                "upcoming": upcoming,
                "metrics": {
                    "linked_accounts": len(account_views),
                    "monthly_spend_sar": _money(stats["monthly_spend_sar"]),
                    "unpaid_bills": int(stats["unpaid_bills"]),
                    "saved_recipients": int(stats["saved_recipients"]),
                },
            },
            "recipients": [
                {
                    "id": recipient["id"],
                    "name": recipient["short_name"] or recipient["full_name"],
                    "name_ar": recipient["full_name"],
                    "bank": _bank(recipient["bank_name_ar"]),
                }
                for recipient in recipients
            ],
        }
