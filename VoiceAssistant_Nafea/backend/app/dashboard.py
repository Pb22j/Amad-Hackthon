"""Authenticated dashboard projection and direct Nafi wallet funding."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


class DepositAccountNotFound(LookupError):
    """The selected linked account is not owned by the authenticated user."""


class DepositInsufficientFunds(ValueError):
    """The selected linked account cannot cover the requested deposit."""


class DepositRequestConflict(ValueError):
    """An idempotency key was already used for different deposit details."""


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


def _allocation_percentages(values: list[Decimal], total: Decimal) -> list[float]:
    """Round allocations to one decimal while preserving an exact 100.0 total."""

    if total <= 0 or not values:
        return [0.0 for _ in values]
    rounded = [
        (value / total * Decimal("100")).quantize(Decimal("0.1"))
        for value in values
    ]
    remainder = Decimal("100.0") - sum(rounded, start=Decimal("0"))
    largest_index = max(range(len(values)), key=values.__getitem__)
    rounded[largest_index] += remainder
    return [float(value) for value in rounded]


def calculate_portfolio_analytics(
    holdings: list[tuple[str, str, str, Decimal]],
    *,
    portfolio_value: Decimal,
    supported_asset_count: int,
) -> dict[str, Any]:
    """Return deterministic allocation and concentration analytics.

    The diversification score is a normalized Herfindahl-Hirschman index over
    the supported investment universe. It is 0 for a single-position portfolio
    and 100 for an equal allocation across every supported asset.
    """

    if portfolio_value <= 0 or not holdings:
        return {
            "diversification_score": 0,
            "diversification_level": "focused",
            "largest_holding_percent": 0.0,
            "sector_allocations": [],
        }

    weights = [market_value / portfolio_value for _, _, _, market_value in holdings]
    largest_holding_percent = _percent(max(market_value for *_, market_value in holdings), portfolio_value)
    hhi = sum((weight * weight for weight in weights), start=Decimal("0"))
    universe_size = max(supported_asset_count, len(holdings), 1)
    max_diversification = Decimal("1") - (Decimal("1") / Decimal(universe_size))
    raw_score = (
        (Decimal("1") - hhi) / max_diversification * Decimal("100")
        if max_diversification > 0
        else Decimal("0")
    )
    diversification_score = int(
        max(Decimal("0"), min(Decimal("100"), raw_score)).quantize(Decimal("1"))
    )
    if diversification_score >= 75:
        diversification_level = "diversified"
    elif diversification_score >= 45:
        diversification_level = "balanced"
    else:
        diversification_level = "focused"

    sectors: dict[str, dict[str, Any]] = {}
    for sector, sector_name, sector_name_ar, market_value in holdings:
        entry = sectors.setdefault(
            sector,
            {
                "sector": sector,
                "name": sector_name,
                "name_ar": sector_name_ar,
                "market_value": Decimal("0"),
            },
        )
        entry["market_value"] += market_value

    sorted_sectors = sorted(
        sectors.values(), key=lambda item: item["market_value"], reverse=True
    )
    sector_percentages = _allocation_percentages(
        [entry["market_value"] for entry in sorted_sectors], portfolio_value
    )

    return {
        "diversification_score": diversification_score,
        "diversification_level": diversification_level,
        "largest_holding_percent": largest_holding_percent,
        "sector_allocations": [
            {
                "sector": entry["sector"],
                "name": entry["name"],
                "name_ar": entry["name_ar"],
                "market_value_sar": _money(entry["market_value"]),
                "weight_percent": sector_percentages[index],
            }
            for index, entry in enumerate(sorted_sectors)
        ],
    }


def calculate_investment_projection(
    *,
    starting_value: Decimal,
    monthly_contribution: Decimal,
    years: int,
    annual_return_percent: Decimal = Decimal("7.0"),
    one_time_contribution: Decimal = Decimal("0"),
    inflation_percent: Decimal = Decimal("2.5"),
    target_amount: Decimal | None = None,
) -> dict[str, Any]:
    """Project custom cash flows using effective annual return and inflation."""

    if starting_value < 0 or monthly_contribution < 0 or one_time_contribution < 0:
        raise ValueError("Investment projection amounts cannot be negative")
    if years < 1 or years > 50:
        raise ValueError("Investment projection horizon must be between 1 and 50 years")
    if annual_return_percent < Decimal("-20") or annual_return_percent > Decimal("30"):
        raise ValueError("Annual return assumption must be between -20 and 30 percent")
    if inflation_percent < 0 or inflation_percent > Decimal("20"):
        raise ValueError("Inflation assumption must be between 0 and 20 percent")
    if target_amount is not None and target_amount <= 0:
        raise ValueError("Investment target must be greater than zero")

    months = years * 12
    with localcontext() as context:
        context.prec = 34
        invested_starting_value = starting_value + one_time_contribution
        annual_factor = Decimal("1") + annual_return_percent / Decimal("100")
        monthly_rate = annual_factor ** (Decimal("1") / Decimal("12")) - Decimal("1")

        def value_at(month: int) -> Decimal:
            growth_factor = (Decimal("1") + monthly_rate) ** month
            contribution_value = (
                monthly_contribution * (growth_factor - Decimal("1")) / monthly_rate
                if monthly_rate != 0
                else monthly_contribution * month
            )
            return invested_starting_value * growth_factor + contribution_value

        projected_value = value_at(months)
        total_contributions = invested_starting_value + monthly_contribution * months
        estimated_growth = projected_value - total_contributions
        inflation_factor = (
            Decimal("1") + inflation_percent / Decimal("100")
        ) ** years
        inflation_adjusted_value = projected_value / inflation_factor
        target_gap = (
            max(Decimal("0"), target_amount - projected_value)
            if target_amount is not None
            else None
        )
        target_surplus = (
            max(Decimal("0"), projected_value - target_amount)
            if target_amount is not None
            else None
        )
        if target_amount is not None:
            ending_factor = (Decimal("1") + monthly_rate) ** months
            amount_needed_from_monthly = max(
                Decimal("0"), target_amount - invested_starting_value * ending_factor
            )
            required_monthly_contribution = (
                amount_needed_from_monthly * monthly_rate / (ending_factor - Decimal("1"))
                if monthly_rate != 0
                else amount_needed_from_monthly / months
            )
        else:
            required_monthly_contribution = None
        milestones = []
        for index in range(1, 13):
            milestone_month = max(1, round(index / 12 * months))
            milestones.append(
                {
                    "month": milestone_month,
                    "value_sar": _money(value_at(milestone_month)),
                    "contributions_sar": _money(
                        invested_starting_value
                        + monthly_contribution * milestone_month
                    ),
                }
            )

    return {
        "starting_value_sar": _money(starting_value),
        "one_time_contribution_sar": _money(one_time_contribution),
        "monthly_contribution_sar": _money(monthly_contribution),
        "years": years,
        "annual_return_percent": float(annual_return_percent),
        "inflation_percent": float(inflation_percent),
        "contribution_timing": "end_of_month",
        "projected_value_sar": _money(projected_value),
        "inflation_adjusted_value_sar": _money(inflation_adjusted_value),
        "total_contributions_sar": _money(total_contributions),
        "estimated_growth_sar": _money(estimated_growth),
        "target_amount_sar": _money(target_amount) if target_amount is not None else None,
        "target_gap_sar": _money(target_gap) if target_gap is not None else None,
        "target_surplus_sar": _money(target_surplus) if target_surplus is not None else None,
        "target_achieved": projected_value >= target_amount if target_amount is not None else None,
        "required_monthly_contribution_sar": (
            _money(required_monthly_contribution)
            if required_monthly_contribution is not None
            else None
        ),
        "milestones": milestones,
    }


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

    def user_identity(self, *, user_id: str, tenant_id: str) -> dict[str, str]:
        """Return the authenticated customer's canonical, server-owned names."""

        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            user = connection.execute(
                """
                SELECT full_name_ar, full_name_en
                  FROM users
                 WHERE username = %s
                 LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if user is None:
            raise LookupError("Authenticated customer profile was not found")
        return {
            "full_name_ar": str(user["full_name_ar"] or "").strip(),
            "full_name_en": str(user["full_name_en"] or "").strip(),
        }

    def preview_wallet_deposit(
        self,
        *,
        user_id: str,
        tenant_id: str,
        source_account_id: str,
        amount: Decimal,
    ) -> dict[str, Any]:
        """Validate a wallet deposit without reserving or moving any money."""

        normalized_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
        if normalized_amount <= 0:
            raise ValueError("Deposit amount must be greater than zero")
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            user = connection.execute(
                """
                SELECT uuid::text AS id, nafi_balance
                  FROM users
                 WHERE username = %s
                """,
                (user_id,),
            ).fetchone()
            if user is None:
                raise LookupError("Authenticated customer profile was not found")
            account = connection.execute(
                """
                SELECT uuid::text AS id, bank_name_ar, account_number, balance_sar
                  FROM bank_accounts
                 WHERE uuid = %s AND user_uuid = %s
                """,
                (source_account_id, user["id"]),
            ).fetchone()
            if account is None:
                raise DepositAccountNotFound(
                    "The selected linked bank account was not found"
                )
            bank_balance = Decimal(str(account["balance_sar"]))
            if normalized_amount > bank_balance:
                raise DepositInsufficientFunds(
                    "The selected bank account does not have enough balance"
                )
            bank = _bank(account["bank_name_ar"])
            return {
                "status": "awaiting_otp",
                "amount_sar": _money(normalized_amount),
                "source_account_id": account["id"],
                "source_bank_name": bank["bank_name"],
                "source_bank_name_ar": bank["bank_name_ar"],
                "source_masked_account_number": _masked_account(account["account_number"]),
                "source_bank_balance_sar": _money(bank_balance),
                "nafi_balance_sar": _money(user["nafi_balance"]),
            }

    def deposit_to_wallet(
        self,
        *,
        user_id: str,
        tenant_id: str,
        source_account_id: str,
        amount: Decimal,
        request_id: str,
    ) -> dict[str, Any]:
        """Atomically move funds from one owned linked bank into the Nafi wallet."""

        normalized_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
        if normalized_amount <= 0:
            raise ValueError("Deposit amount must be greater than zero")
        reference = f"wallet-deposit-{request_id.replace('-', '')}"
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.execute("SET TIME ZONE 'Asia/Riyadh'")
            with connection.transaction():
                user = connection.execute(
                    """
                    SELECT uuid::text AS id, nafi_iban, nafi_balance
                      FROM users
                     WHERE username = %s
                     FOR UPDATE
                    """,
                    (user_id,),
                ).fetchone()
                if user is None:
                    raise LookupError("Authenticated customer profile was not found")

                account = connection.execute(
                    """
                    SELECT uuid::text AS id, bank_name_ar, account_number, balance_sar
                      FROM bank_accounts
                     WHERE uuid = %s AND user_uuid = %s
                     FOR UPDATE
                    """,
                    (source_account_id, user["id"]),
                ).fetchone()
                if account is None:
                    raise DepositAccountNotFound(
                        "The selected linked bank account was not found"
                    )

                existing = connection.execute(
                    """
                    SELECT transaction_type, amount_sar, account_number, balance_after_sar
                      FROM transactions
                     WHERE user_uuid = %s AND reference = %s
                    """,
                    (user["id"], reference),
                ).fetchall()
                if existing:
                    rows = {row["transaction_type"]: row for row in existing}
                    bank_row = rows.get("nafi_top_up_source")
                    wallet_row = rows.get("nafi_top_up")
                    if (
                        bank_row is None
                        or wallet_row is None
                        or Decimal(str(wallet_row["amount_sar"])) != normalized_amount
                        or bank_row["account_number"] != account["account_number"]
                    ):
                        raise DepositRequestConflict(
                            "This deposit request ID was already used with different details"
                        )
                    return {
                        "status": "completed",
                        "reference": reference,
                        "receipt_id": f"receipt-{reference}",
                        "amount_sar": _money(normalized_amount),
                        "source_account_id": account["id"],
                        "source_bank_balance_sar": _money(bank_row["balance_after_sar"]),
                        "nafi_balance_sar": _money(wallet_row["balance_after_sar"]),
                        "idempotent_replay": True,
                    }

                bank_balance = Decimal(str(account["balance_sar"]))
                if normalized_amount > bank_balance:
                    raise DepositInsufficientFunds(
                        "The selected bank account does not have enough balance"
                    )

                wallet_balance = Decimal(str(user["nafi_balance"]))
                bank_balance_after = bank_balance - normalized_amount
                wallet_balance_after = wallet_balance + normalized_amount
                now = datetime.now(timezone.utc)

                connection.execute(
                    "UPDATE bank_accounts SET balance_sar = %s WHERE uuid = %s",
                    (bank_balance_after, account["id"]),
                )
                connection.execute(
                    "UPDATE users SET nafi_balance = %s WHERE uuid = %s",
                    (wallet_balance_after, user["id"]),
                )
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
                        str(uuid4()),
                        user["id"],
                        account["account_number"],
                        normalized_amount,
                        user["nafi_iban"],
                        bank_balance_after,
                        reference,
                        now,
                        str(uuid4()),
                        user["id"],
                        user["nafi_iban"],
                        normalized_amount,
                        account["bank_name_ar"],
                        account["account_number"],
                        wallet_balance_after,
                        reference,
                        now,
                    ),
                )

        return {
            "status": "completed",
            "reference": reference,
            "receipt_id": f"receipt-{reference}",
            "amount_sar": _money(normalized_amount),
            "source_account_id": source_account_id,
            "source_bank_balance_sar": _money(bank_balance_after),
            "nafi_balance_sar": _money(wallet_balance_after),
            "idempotent_replay": False,
        }

    def snapshot(self, *, user_id: str, tenant_id: str) -> dict[str, Any]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.execute("SET TIME ZONE 'Asia/Riyadh'")
            user = connection.execute(
                """
                SELECT uuid::text AS id, username::text, full_name_ar, full_name_en,
                       nafi_iban, nafi_balance,
                       (SELECT COALESCE(SUM(s.balance_sar), 0)
                          FROM nafi_savings_accounts s
                         WHERE s.user_uuid = users.uuid
                           AND s.account_type = 'liquid') AS nafi_liquid_savings_balance
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
                SELECT h.symbol, h.quantity, h.average_cost_sar, a.name, a.price_sar,
                       a.asset_class, a.exchange, a.currency_code, a.updatedat,
                       a.sector, a.sector_name, a.sector_name_ar
                FROM investment_holdings h
                JOIN investment_assets a ON a.symbol = h.symbol
                WHERE h.user_uuid = %s AND h.quantity > 0 AND a.status = 'active'
                ORDER BY h.symbol
                """,
                (user["id"],),
            ).fetchall()
            investment_assets = connection.execute(
                """
                SELECT symbol, name, asset_class, exchange, currency_code,
                       price_sar, updatedat, sector, sector_name, sector_name_ar
                FROM investment_assets
                WHERE status = 'active'
                ORDER BY symbol
                """
            ).fetchall()
            transactions = connection.execute(
                """
                SELECT uuid::text AS id, direction, transaction_type, amount_sar,
                       counterparty_name, description, createdat
                FROM transactions
                WHERE user_uuid = %s AND transaction_type != 'nafi_top_up_source'
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
                      AND transaction_type NOT IN (
                        'nafi_top_up_source', 'nafi_liquid_savings_debit',
                        'nafi_liquid_savings_credit'
                      )
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

        wallet_balance = Decimal(str(user["nafi_balance"]))
        liquid_savings_balance = Decimal(str(user["nafi_liquid_savings_balance"]))
        portfolio_gain = portfolio_value - portfolio_cost
        holding_weight_percentages = _allocation_percentages(
            [market_value for _, market_value, _ in holding_values], portfolio_value
        )
        portfolio_analytics = calculate_portfolio_analytics(
            [
                (
                    str(holding["sector"]),
                    str(holding["sector_name"]),
                    str(holding["sector_name_ar"]),
                    market_value,
                )
                for holding, market_value, _ in holding_values
            ],
            portfolio_value=portfolio_value,
            supported_asset_count=len(investment_assets),
        )
        net_worth = balance + wallet_balance + liquid_savings_balance + portfolio_value
        net_basis = balance + wallet_balance + liquid_savings_balance + portfolio_cost
        account_views = [
            {
                "id": account["id"],
                **_bank(account["bank_name_ar"]),
                "account_type": account["account_type"],
                "balance_sar": _money(account["balance_sar"]),
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
            "wallet": {
                "nafi_iban": user["nafi_iban"],
                "balance_sar": _money(user["nafi_balance"]),
                "liquid_savings_balance_sar": _money(liquid_savings_balance),
            },
            "accounts": account_views,
            "portfolio": {
                "value_sar": _money(portfolio_value),
                "cost_basis_sar": _money(portfolio_cost),
                "unrealized_gain_sar": _money(portfolio_gain),
                "total_return_percent": _percent(portfolio_gain, portfolio_cost),
                "analytics": portfolio_analytics,
                "holdings": [
                    {
                        "ticker": holding["symbol"],
                        "name": holding["name"],
                        "name_ar": _ASSET_NAMES_AR.get(holding["symbol"], holding["name"]),
                        "asset_class": holding["asset_class"],
                        "exchange": holding["exchange"],
                        "currency_code": holding["currency_code"],
                        "sector": holding["sector"],
                        "sector_name": holding["sector_name"],
                        "sector_name_ar": holding["sector_name_ar"],
                        "quantity": format(Decimal(str(holding["quantity"])).normalize(), "f"),
                        "price_sar": _money(holding["price_sar"]),
                        "average_cost_sar": _money(holding["average_cost_sar"]),
                        "market_value_sar": _money(market_value),
                        "unrealized_gain_sar": _money(market_value - cost_value),
                        "weight_percent": holding_weight_percentages[index],
                        "return_percent": _percent(market_value - cost_value, cost_value),
                    }
                    for index, (holding, market_value, cost_value) in enumerate(holding_values)
                ],
                "supported_assets": [
                    {
                        "ticker": asset["symbol"],
                        "name": asset["name"],
                        "name_ar": _ASSET_NAMES_AR.get(asset["symbol"], asset["name"]),
                        "asset_class": asset["asset_class"],
                        "exchange": asset["exchange"],
                        "currency_code": asset["currency_code"],
                        "sector": asset["sector"],
                        "sector_name": asset["sector_name"],
                        "sector_name_ar": asset["sector_name_ar"],
                        "price_sar": _money(asset["price_sar"]),
                        "updated_at": asset["updatedat"].isoformat(),
                    }
                    for asset in investment_assets
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

    def investment_projection(
        self,
        *,
        user_id: str,
        tenant_id: str,
        monthly_contribution: Decimal,
        years: int,
        annual_return_percent: Decimal,
        one_time_contribution: Decimal,
        inflation_percent: Decimal,
        target_amount: Decimal | None,
    ) -> dict[str, Any]:
        """Project the authenticated customer's current portfolio and contributions."""

        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                SELECT u.uuid::text AS id,
                       COALESCE(SUM(h.quantity * a.price_sar), 0) AS portfolio_value_sar
                FROM users u
                LEFT JOIN investment_holdings h
                  ON h.user_uuid = u.uuid AND h.quantity > 0
                LEFT JOIN investment_assets a
                  ON a.symbol = h.symbol AND a.status = 'active'
                WHERE u.username = %s
                GROUP BY u.uuid
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            raise LookupError("Authenticated customer profile was not found")
        return calculate_investment_projection(
            starting_value=Decimal(str(row["portfolio_value_sar"])),
            monthly_contribution=monthly_contribution,
            years=years,
            annual_return_percent=annual_return_percent,
            one_time_contribution=one_time_contribution,
            inflation_percent=inflation_percent,
            target_amount=target_amount,
        )
