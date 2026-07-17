#!/usr/bin/env python3
"""Seed the Nafi demo database and six months of realistic financial history."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

import psycopg
from psycopg.types.json import Jsonb

from agentic.config.environment import load_backend_environment


def _postgres_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _id(kind: str, value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"nafi-demo:{kind}:{value}"))


def _password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


USERS = (
    ("evaluation-user", "أحمد فهد العتيبي", "Ahmed Fahad Alotaibi", "SA9900000000000000000001", "5000", "25431.50"),
    ("admin", "ماجد عبدالله السبيعي", "Majid Abdullah Alsubaie", "SA9900000000000000000002", "20000", "75000.00"),
    ("waleed", "الوليد خالد الشمري", "Waleed Khalid Alshammari", "SA9900000000000000000003", "10000", "15000.00"),
    ("mohammed", "محمد ناصر القحطاني", "Mohammed Nasser Alqahtani", "SA9900000000000000000004", "20000", "8400.00"),
    ("noura", "نورة سلطان الحربي", "Noura Sultan Alharbi", "SA9900000000000000000005", "15000", "19750.00"),
    ("latifa", "لطيفة محمد العنزي", "Latifa Mohammed Alanazi", "SA9900000000000000000006", "12000", "12500.00"),
    ("saud", "سعود عبدالله العنزي", "Saud Abdullah Alanazi", "SA9900000000000000000007", "8000", "9100.00"),
    ("faisal", "فيصل صالح الدوسري", "Faisal Saleh Aldosari", "SA9900000000000000000008", "9000", "18300.00"),
    ("sara", "سارة أحمد الغامدي", "Sara Ahmed Alghamdi", "SA9900000000000000000009", "7000", "22100.00"),
    ("khalid", "خالد عمر الزهراني", "Khalid Omar Alzahrani", "SA9900000000000000000010", "11000", "30750.00"),
)

ACCOUNTS = (
    ("evaluation-user", "مصرف الإنماء", "Alinma Bank", "SA4405000068201234567890", "Current", "25431.50", True),
    ("evaluation-user", "مصرف الراجحي", "Al Rajhi Bank", "SA0380000000608010167519", "Savings", "4200.00", False),
    ("admin", "البنك الأهلي السعودي", "Saudi National Bank", "SA1210000000123456789001", "Current", "75000.00", True),
    ("waleed", "بنك البلاد", "Bank Albilad", "SA6015000078965432101234", "Current", "15000.00", True),
    ("mohammed", "بنك الرياض", "Riyad Bank", "SA0320000005556667772222", "Current", "8400.00", True),
    ("noura", "البنك السعودي الأول", "Saudi Awwal Bank", "SA1545000003334445553333", "Current", "19750.00", True),
    ("latifa", "البنك الأهلي السعودي", "Saudi National Bank", "SA98000068368508501525", "Current", "12500.00", True),
    ("saud", "البنك العربي الوطني", "Arab National Bank", "SA91000032763205429515", "Current", "9100.00", True),
    ("faisal", "البنك السعودي الفرنسي", "Banque Saudi Fransi", "SA5565000000001234567801", "Current", "18300.00", True),
    ("sara", "مصرف الراجحي", "Al Rajhi Bank", "SA2280000000001234567802", "Current", "22100.00", True),
    ("khalid", "بنك الرياض", "Riyad Bank", "SA0620000000001234567803", "Current", "30750.00", True),
)


MONTHLY_INCOME = {
    "evaluation-user": Decimal("15500"),
    "admin": Decimal("23500"),
    "waleed": Decimal("14200"),
    "mohammed": Decimal("11800"),
    "noura": Decimal("16400"),
    "latifa": Decimal("13200"),
    "saud": Decimal("10500"),
    "faisal": Decimal("14600"),
    "sara": Decimal("12400"),
    "khalid": Decimal("17800"),
}

HISTORY_MONTHS = 6
RIYADH = ZoneInfo("Asia/Riyadh")
EXPENSE_FACTORS = {
    # Keep the primary evaluation profile cash-positive so idle-cash flows
    # have a meaningful safe surplus to recommend during demos and tests.
    "evaluation-user": Decimal(".48"),
}


def _month_starts(now: datetime, count: int = HISTORY_MONTHS) -> list[datetime]:
    cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    starts = []
    for _ in range(count):
        starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    return list(reversed(starts))


def _varied_amount(
    income: Decimal,
    ratio: str,
    *,
    username: str,
    month: datetime,
    label: str,
    spread_percent: int = 12,
) -> Decimal:
    """Return a stable, user-specific amount with small month-to-month variation."""

    digest = hashlib.sha256(
        f"{username}:{month:%Y-%m}:{label}".encode()
    ).digest()
    offset = int.from_bytes(digest[:2], "big") % (spread_percent * 2 + 1)
    multiplier = Decimal("1") + Decimal(offset - spread_percent) / Decimal("100")
    return (income * Decimal(ratio) * multiplier).quantize(Decimal("0.01"))


def _monthly_activity(
    username: str,
    month_start: datetime,
    *,
    now: datetime,
) -> tuple[dict[str, object], ...]:
    income = MONTHLY_INCOME[username]
    last_day = monthrange(month_start.year, month_start.month)[1]
    rows: list[dict[str, object]] = []

    def add(
        day: int,
        hour: int,
        direction: str,
        ratio: str,
        transaction_type: str,
        counterparty: str,
        description: str,
        category: str,
        channel: str,
        label: str,
        city: str = "الرياض",
    ) -> None:
        moment = month_start.replace(day=min(day, last_day), hour=hour)
        if moment > now:
            return
        amount = _varied_amount(
            income,
            ratio,
            username=username,
            month=month_start,
            label=label,
            spread_percent=2 if transaction_type == "salary" else 12,
        )
        if direction == "debit":
            amount = (
                amount * EXPENSE_FACTORS.get(username, Decimal("1"))
            ).quantize(Decimal("0.01"))
        rows.append(
            {
                "moment": moment,
                "direction": direction,
                "amount": amount,
                "type": transaction_type,
                "counterparty": counterparty,
                "description": description,
                "category": category,
                "channel": channel,
                "city": city,
            }
        )

    add(1, 9, "credit", "1", "salary", "جهة العمل", "إيداع الراتب الشهري", "راتب", "bank_transfer", "salary")
    add(2, 10, "debit", ".28", "rent", "شركة العقار السكنية", "دفعة الإيجار الشهرية", "سكن", "direct_debit", "rent")
    add(3, 8, "debit", ".008", "purchase", "بارنز", "قهوة ومخبوزات", "مطاعم", "card", "coffee")
    add(4, 19, "debit", ".035", "purchase", "أسواق بنده", "مشتريات بقالة أسبوعية", "بقالة", "card", "groceries-1")
    add(5, 17, "debit", ".018", "purchase", "محطة الدريس", "وقود", "مواصلات", "card", "fuel-1")
    add(6, 11, "debit", ".05", "bill_payment", "منصة مدرستي", "رسوم تعليم وتدريب", "تعليم", "online", "education")
    add(7, 21, "debit", ".018", "purchase", "هنقرستيشن", "طلب عشاء", "مطاعم", "card", "restaurant-1")
    add(8, 14, "debit", ".025", "bill_payment", "الشركة السعودية للكهرباء", "فاتورة الكهرباء", "فواتير", "sadad", "electricity")
    add(9, 18, "debit", ".035", "purchase", "لولو هايبرماركت", "مشتريات منزلية", "بقالة", "card", "groceries-2")
    add(10, 13, "debit", ".012", "bill_payment", "STC", "فاتورة الجوال والإنترنت", "فواتير", "sadad", "telecom")
    add(11, 16, "credit", ".025", "transfer_in", "صديق", "استرداد حصة مصروف مشترك", "حوالات", "bank_transfer", "shared-refund")
    add(12, 7, "debit", ".008", "subscription", "شاهد وسبوتيفاي", "اشتراكات رقمية", "ترفيه", "card", "subscriptions")
    add(13, 20, "debit", ".035", "cash_withdrawal", "صراف آلي", "سحب نقدي", "نقد", "atm", "cash")
    add(14, 18, "debit", ".035", "purchase", "أسواق التميمي", "مشتريات بقالة أسبوعية", "بقالة", "card", "groceries-3")
    add(15, 12, "debit", ".10", "transfer_out", "حوالة عائلية", "دعم ومصروف عائلي", "حوالات", "bank_transfer", "family")
    add(16, 17, "debit", ".018", "purchase", "ساسكو", "وقود وخدمات سيارة", "مواصلات", "card", "fuel-2")
    add(17, 21, "debit", ".018", "purchase", "جاهز", "طلب طعام", "مطاعم", "card", "restaurant-2")
    add(18, 11, "debit", ".02", "purchase", "صيدلية النهدي", "أدوية وعناية صحية", "صحة", "card", "health")
    add(19, 18, "debit", ".035", "purchase", "كارفور", "مشتريات بقالة أسبوعية", "بقالة", "card", "groceries-4")
    add(20, 10, "debit", ".025", "bill_payment", "شركة التعاونية", "قسط تأمين", "تأمين", "direct_debit", "insurance")
    add(21, 19, "debit", ".06", "purchase", "مكتبة جرير", "تسوق وإلكترونيات", "تسوق", "card", "shopping")
    add(22, 8, "debit", ".05", "savings_transfer", "حساب الادخار", "تحويل دوري للادخار", "مدخرات", "bank_transfer", "savings")
    add(24, 21, "debit", ".018", "purchase", "ذا شفز", "عشاء نهاية الأسبوع", "مطاعم", "card", "restaurant-3")
    add(25, 15, "debit", ".06", "purchase", "الخطوط السعودية", "سفر وترفيه", "سفر", "card", "travel")
    add(27, 13, "debit", ".01", "donation", "منصة إحسان", "تبرع شهري", "تبرعات", "online", "donation")
    return tuple(rows)


def seed_history(
    target: psycopg.Connection[object],
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Replace only deterministic seed rows with six calendar months of history."""

    current = (now or datetime.now(RIYADH)).astimezone(RIYADH)
    inserted = 0
    with target.cursor() as cur:
        cur.execute(
            "DELETE FROM transactions "
            "WHERE reference LIKE 'demo-history-%' OR reference LIKE 'seed-%'"
        )
        replaced = cur.rowcount
        cur.execute(
            """SELECT u.uuid, u.username, b.account_number, b.balance_sar
                 FROM users AS u
                 JOIN bank_accounts AS b ON b.user_uuid = u.uuid AND b.is_primary
                ORDER BY u.username"""
        )
        owners = cur.fetchall()
        for user_uuid, username, account_number, current_balance in owners:
            activity = [
                item
                for month in _month_starts(current)
                for item in _monthly_activity(username, month, now=current)
            ]
            net_change = sum(
                (
                    item["amount"]
                    if item["direction"] == "credit"
                    else -item["amount"]
                )
                for item in activity
            )
            running = max(Decimal("500.00"), Decimal(current_balance) - net_change)
            for index, item in enumerate(activity):
                amount = item["amount"]
                running += amount if item["direction"] == "credit" else -amount
                reference = (
                    f"demo-history-{username}-{item['moment']:%Y%m}-{index:03d}"
                )
                cur.execute(
                    """INSERT INTO transactions
                       (uuid,user_uuid,account_number,direction,transaction_type,
                        amount_sar,counterparty_name,description,category,
                        balance_after_sar,reference,channel,merchant_city,metadata,createdat)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        _id("transaction", reference),
                        user_uuid,
                        account_number,
                        item["direction"],
                        item["type"],
                        amount,
                        item["counterparty"],
                        item["description"],
                        item["category"],
                        running,
                        reference,
                        item["channel"],
                        item["city"],
                        Jsonb(
                            {
                                "source": "six_month_demo_seed",
                                "synthetic": True,
                                "profile": username,
                            }
                        ),
                        item["moment"],
                    ),
                )
                inserted += 1

    return {
        "history_users": len(owners),
        "history_months": HISTORY_MONTHS,
        "history_transactions": inserted,
        "replaced_seed_transactions": replaced,
    }


def seed(target: psycopg.Connection[object]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    users = {username: _id("user", username) for username, *_ in USERS}
    password_hash = _password_hash("password123")

    with target.cursor() as cur:
        for username, name_ar, name_en, nafi_iban, daily_limit, nafi_balance in USERS:
            cur.execute(
                """INSERT INTO users
                   (uuid, username, full_name_ar, full_name_en, password_hash,
                    nafi_iban, daily_spend_limit_sar, nafi_balance)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    users[username], username, name_ar, name_en, password_hash,
                    nafi_iban, Decimal(daily_limit), Decimal(nafi_balance),
                ),
            )

        for username, *_ in USERS:
            savings_uuid = _id("nafi-liquid-savings", username)
            savings_account_number = "NFS" + users[username].replace("-", "")[:29].upper()
            cur.execute(
                """INSERT INTO nafi_savings_accounts
                   (uuid,user_uuid,account_number,account_type,name,name_ar,
                    balance_sar,created_at,updated_at)
                   VALUES (%s,%s,%s,'liquid','Nafi Liquid Savings',
                           'مدخرات نافي السائلة',0,%s,%s)""",
                (
                    savings_uuid,
                    users[username],
                    savings_account_number,
                    now,
                    now,
                ),
            )

        for username, bank_ar, bank_en, account_number, account_type, balance, primary in ACCOUNTS:
            account_uuid = _id("account", account_number)
            cur.execute(
                """INSERT INTO bank_accounts
                   (uuid,user_uuid,bank_name_ar,bank_name_en,account_number,account_type,balance_sar,is_primary)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (account_uuid, users[username], bank_ar, bank_en, account_number, account_type, Decimal(balance), primary),
            )

        for owner, beneficiary, short_name in (
            ("evaluation-user", "latifa", "لطيفة"),
            ("evaluation-user", "waleed", "الوليد"),
            ("admin", "evaluation-user", "أحمد"),
            ("admin", "faisal", "فيصل"),
        ):
            cur.execute(
                """INSERT INTO beneficiaries
                   (uuid,owner_uuid,beneficiary_uuid,short_name,createdat)
                   VALUES (%s,%s,%s,%s,%s)""",
                (_id("beneficiary", f"{owner}:{beneficiary}"), users[owner],
                 users[beneficiary], short_name, now),
            )

        for symbol, name, price, sector, sector_name, sector_name_ar in (
            ("ARAMCO", "Saudi Aramco", "27.80", "energy", "Energy", "الطاقة"),
            ("ALRAJHI", "Al Rajhi Bank", "96.40", "financials", "Financials", "القطاع المالي"),
            ("SABIC", "SABIC", "61.20", "materials", "Materials", "المواد الأساسية"),
        ):
            cur.execute(
                """INSERT INTO investment_assets
                   (symbol,name,price_sar,sector,sector_name,sector_name_ar,updatedat)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (symbol, name, Decimal(price), sector, sector_name, sector_name_ar, now),
            )
        for username in ("evaluation-user", "admin"):
            cur.execute(
                """INSERT INTO investment_holdings
                   (uuid,user_uuid,symbol,quantity,average_cost_sar,updatedat)
                   VALUES (%s,%s,'ARAMCO',20,26.50,%s)""",
                (_id("holding", username), users[username], now),
            )

        for username, number, biller, amount in (
            ("evaluation-user", "30012345671234", "الشركة السعودية للكهرباء", "348.60"),
            ("evaluation-user", "20098765435678", "شركة المياه الوطنية", "86.25"),
            ("evaluation-user", "96655544439012", "STC", "129.00"),
            ("admin", "30011122238888", "الشركة السعودية للكهرباء", "512.40"),
            ("waleed", "40077766624444", "المرور - رسوم مخالفات", "20000.00"),
        ):
            cur.execute(
                """INSERT INTO fatoorahs
                   (uuid,user_uuid,bill_number,biller_name_ar,amount_sar,status,duedate,createdat)
                   VALUES (%s,%s,%s,%s,%s,'unpaid',%s,%s)""",
                (_id("bill", number), users[username], number, biller, Decimal(amount), now + timedelta(days=14), now),
            )

        qatta_id = _id("qatta", "friday-dinner")
        cur.execute(
            """INSERT INTO qattas
               (uuid,creator_uuid,name,total_amount_sar,share_amount_sar,status,createdat,updatedat)
               VALUES (%s,%s,'قطة عشاء الجمعة',300,100,'open',%s,%s)""",
            (qatta_id, users["admin"], now, now),
        )
        for username, status in (("admin", "paid"), ("evaluation-user", "unpaid"), ("latifa", "unpaid")):
            cur.execute(
                """INSERT INTO qatta_bills
                   (uuid,qatta_uuid,participant_uuid,amount_sar,status,paidat,createdat)
                   VALUES (%s,%s,%s,100,%s,%s,%s)""",
                (_id("qatta-bill", f"friday-dinner:{username}"), qatta_id, users[username],
                 status, now if status == "paid" else None, now),
            )

    history_counts = seed_history(target)
    return {
        "users": len(USERS),
        "bank_accounts": len(ACCOUNTS),
        "beneficiaries": 4,
        **history_counts,
    }


def main() -> None:
    load_backend_environment()
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--history-only",
        action="store_true",
        help="Refresh six months of deterministic history without reseeding users.",
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL in .env.backend is required")
    with psycopg.connect(_postgres_url(args.database_url)) as target:
        counts = seed_history(target) if args.history_only else seed(target)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
