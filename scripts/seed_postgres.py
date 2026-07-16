#!/usr/bin/env python3
"""Seed the minimal Nafi demo database with exactly ten users."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

import psycopg

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


def _monthly_activity(month_start: datetime) -> tuple[dict[str, object], ...]:
    def at(day: int, hour: int) -> datetime:
        return month_start.replace(day=day, hour=hour)

    return (
        {"moment": at(1, 9), "direction": "credit", "amount": Decimal("15500.00"), "type": "salary", "counterparty": "شركة أمد للتقنية", "description": "إيداع راتب شهري", "category": "راتب"},
        {"moment": at(3, 18), "direction": "debit", "amount": Decimal("4200.00"), "type": "rent", "counterparty": "شركة الفيصلية العقارية", "description": "إيجار شقة", "category": "سكن"},
        {"moment": at(6, 12), "direction": "debit", "amount": Decimal("612.40"), "type": "purchase", "counterparty": "أسواق بنده", "description": "مشتريات بقالة", "category": "بقالة"},
        {"moment": at(9, 20), "direction": "debit", "amount": Decimal("389.00"), "type": "bill_payment", "counterparty": "الشركة السعودية للكهرباء", "description": "فاتورة كهرباء", "category": "فواتير"},
        {"moment": at(12, 14), "direction": "debit", "amount": Decimal("145.00"), "type": "bill_payment", "counterparty": "STC", "description": "فاتورة جوال وإنترنت", "category": "فواتير"},
        {"moment": at(15, 10), "direction": "credit", "amount": Decimal("750.00"), "type": "transfer_in", "counterparty": "لطيفة العنزي", "description": "تسديد مشاركة رحلة", "category": "حوالات"},
        {"moment": at(19, 21), "direction": "debit", "amount": Decimal("264.75"), "type": "purchase", "counterparty": "هنقرستيشن", "description": "طلبات طعام", "category": "مطاعم"},
        {"moment": at(24, 16), "direction": "debit", "amount": Decimal("980.00"), "type": "purchase", "counterparty": "مكتبة جرير", "description": "مشتريات إلكترونيات", "category": "تسوق"},
    )


def seed(target: psycopg.Connection[object]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    users = {username: _id("user", username) for username, *_ in USERS}
    accounts: dict[str, tuple[str, str]] = {}
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

        for username, bank_ar, bank_en, account_number, account_type, balance, primary in ACCOUNTS:
            account_uuid = _id("account", account_number)
            cur.execute(
                """INSERT INTO bank_accounts
                   (uuid,user_uuid,bank_name_ar,bank_name_en,account_number,account_type,balance_sar,is_primary)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (account_uuid, users[username], bank_ar, bank_en, account_number, account_type, Decimal(balance), primary),
            )
            if primary:
                accounts[username] = (account_uuid, account_number)

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

        primary_uuid, primary_number = accounts["evaluation-user"]
        for months_ago in range(3):
            month = (now.replace(day=1, hour=8, minute=0, second=0, microsecond=0) - timedelta(days=months_ago * 31)).replace(day=1)
            running = Decimal("25431.50")
            for index, item in enumerate(_monthly_activity(month)):
                amount = item["amount"]
                running += amount if item["direction"] == "credit" else -amount
                reference = f"seed-{month:%Y%m}-{index}-{users['evaluation-user'][:8]}"
                cur.execute(
                    """INSERT INTO transactions
                       (uuid,user_uuid,account_number,direction,transaction_type,amount_sar,
                        counterparty_name,description,category,balance_after_sar,reference,createdat)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (_id("transaction", reference), users["evaluation-user"], primary_number,
                     item["direction"], item["type"], amount, item["counterparty"],
                     item["description"], item["category"], running, reference, item["moment"]),
                )

        for symbol, name, price in (("ARAMCO", "Saudi Aramco", "27.80"), ("ALRAJHI", "Al Rajhi Bank", "96.40"), ("SABIC", "SABIC", "61.20")):
            cur.execute(
                "INSERT INTO investment_assets (symbol,name,price_sar,updatedat) VALUES (%s,%s,%s,%s)",
                (symbol, name, Decimal(price), now),
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

    return {"users": len(USERS), "bank_accounts": len(ACCOUNTS), "beneficiaries": 4}


def main() -> None:
    load_backend_environment()
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL in .env.backend is required")
    with psycopg.connect(_postgres_url(args.database_url)) as target:
        counts = seed(target)
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
