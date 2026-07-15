#!/usr/bin/env python3
"""Seed PostgreSQL from the project CSV datasets with realistic banking history.

Run Alembic first. The import is transactional and idempotent: source records retain
stable identifiers, while generated enrichment uses UUIDv5 and deterministic values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

import psycopg

from agentic.config.environment import load_backend_environment

RIYADH = timezone(timedelta(hours=3))
ROOT = Path(__file__).resolve().parents[1]
DEMO_HASH = "b2372c8b34afcaa4dddda3084c16012fbd463639519d15fff945f3c321b15d43"


def _postgres_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _dt(value: Any, *, fallback: datetime | None = None) -> datetime:
    if value in (None, ""):
        return fallback or datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=RIYADH)
    return parsed


def _date(value: Any) -> Any:
    return datetime.strptime(str(value), "%Y-%m-%d").date() if value else None


def _password_hash(password: str, username: str) -> str:
    salt = hashlib.sha256(f"amad-demo:{username}".encode()).digest()[:16]
    # Source credentials are synthetic and must never be usable in production.
    # A bounded work factor keeps the 1,000-row hackathon import practical while
    # still ensuring no plaintext credential crosses the migration boundary.
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**10, r=8, p=1)
    return f"scrypt$1024$8$1${salt.hex()}${digest.hex()}"


def _unique_username(source: str, account: str, ordinal: int, total: int) -> str:
    return source if total == 1 or ordinal == 1 else f"{source}__{account[-6:]}"


def _email(username: str, index: int) -> str:
    safe = "".join(ch if ch.isalnum() else "." for ch in username.lower()).strip(".")
    return f"{safe}.{index:04d}@demo.amad.sa"


def _phone(index: int) -> str:
    return f"+9665{10000000 + index:08d}"


def _monthly_activity(month_start: datetime) -> tuple[dict[str, Any], ...]:
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


def import_platform_users(
    rows: Iterable[dict[str, str]], target: psycopg.Connection[Any]
) -> int:
    rows = list(rows)
    now = datetime.now(timezone.utc)
    with target.cursor() as cur:
        for row in rows:
            user_id = int(row["id"])
            created = _dt(row["createdAt"])
            cur.execute(
                """INSERT INTO platform_users
                   (id, username, full_name, email, password_hash, phone_e164, country_code,
                    city, role, preferred_language, timezone, verified, status,
                    last_login_at, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,'SA',%s,%s,'ar','Asia/Riyadh',%s,'active',%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                     username=EXCLUDED.username, full_name=EXCLUDED.full_name,
                     email=EXCLUDED.email, phone_e164=EXCLUDED.phone_e164,
                     verified=EXCLUDED.verified, updated_at=EXCLUDED.updated_at""",
                (user_id, row["username"], row["fullName"], row["email"],
                 _password_hash(row["password"], row["username"]),
                 row["phone"] if row["phone"].startswith("+") else f"+{row['phone']}",
                 row["city"], row["role"], row["verified"].lower() == "true",
                 created + timedelta(days=30 + user_id % 180), created, now),
            )
        cur.execute("SELECT setval(pg_get_serial_sequence('platform_users','id'), COALESCE(MAX(id),1)) FROM platform_users")
    return len(rows)


def import_bank_users(
    rows: Iterable[dict[str, str]], target: psycopg.Connection[Any]
) -> tuple[int, dict[str, str]]:
    rows = list(rows)
    counts = Counter(str(row["Username"]) for row in rows)
    seen: Counter[str] = Counter()
    resolved: dict[str, str] = {}
    now = datetime.now(timezone.utc)
    with target.cursor() as cur:
        for index, row in enumerate(rows, start=1):
            source_username = str(row["Username"])
            seen[source_username] += 1
            username = _unique_username(source_username, row["Account_Number"], seen[source_username], counts[source_username])
            resolved.setdefault(source_username, str(row["uuid"]))
            created, updated = _dt(row["createdAt"]), _dt(row["updatedAt"])
            nafath = row["Nafath_Linked"] or "No"
            status = row["status"] or "inactive"
            balance = Decimal(str(row["Balance_SAR"] or 0)).quantize(Decimal("0.01"))
            risk = "medium" if status == "inactive" else ("low" if balance < 100000 else "medium")
            cur.execute(
                """INSERT INTO users
                   (uuid,tenant_id,username,source_username,full_name_ar,dateofbirth,gender,
                    email,phone_e164,bank_name_ar,account_number,account_type_ar,balance_sar,
                    available_balance_sar,daily_spend_limit_sar,hashedpassword,status,
                    nafath_linked,kyc_status,kyc_tier,risk_rating,last_login_at,createdat,updatedat)
                   VALUES (%s,'evaluation-tenant',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (uuid) DO UPDATE SET
                    username=EXCLUDED.username, source_username=EXCLUDED.source_username,
                    balance_sar=EXCLUDED.balance_sar, available_balance_sar=EXCLUDED.available_balance_sar,
                    updatedat=EXCLUDED.updatedat""",
                (row["uuid"], username, source_username, row["Full_Name_Ar"], _date(row["dateOfBirth"]),
                 row["gender"], _email(username, index), _phone(index), row["Bank_Name_Ar"],
                 row["Account_Number"], row["Account_Type_Ar"], balance, balance,
                 Decimal(str(row["Daily_Spend_Limit_SAR"] or 5000)), row["hashedPassword"] or DEMO_HASH,
                 status, nafath, "verified" if nafath == "Yes" else "pending", 2 if nafath == "Yes" else 1,
                 risk, min(updated + timedelta(days=index % 30), now), created, updated),
            )
    return len(rows), resolved


def add_operational_users(target: psycopg.Connection[Any]) -> dict[str, str]:
    demo = (
        ("3f1f7a3e-8d1e-4a67-9f7d-2b6f3a1c9e01", "evaluation-user", "أحمد فهد العتيبي", "1994-08-22", "Male", "مصرف الإنماء", "SA4405000068201234567890", "حساب جاري", "25431.50", "5000"),
        ("7c3d9f81-2e5a-4b18-9d64-1f8e6a2c4b05", "waleed", "الوليد خالد الشمري", "1999-05-20", "Male", "بنك البلاد", "SA6015000078965432101234", "حساب جاري", "15000", "10000"),
        ("9d2c5b74-6a0f-4e3b-8c11-5e9a7d4f2b02", "user_55210", "محمد ناصر القحطاني", "1988-11-30", "Male", "بنك الرياض", "SA0320000005556667772222", "حساب جاري", "8400", "20000"),
        ("5a8e1c29-3b7d-4f56-a0e2-7c4d9b8e6f03", "user_83777", "نورة سلطان الحربي", "1997-02-14", "Female", "البنك السعودي الأول", "SA1545000003334445553333", "حساب جاري", "19750", "15000"),
    )
    ids: dict[str, str] = {}
    now = datetime.now(timezone.utc)
    with target.cursor() as cur:
        for index, item in enumerate(demo, start=2001):
            uid, username, name, dob, gender, bank, account, account_type, balance, limit = item
            cur.execute(
                """INSERT INTO users
                   (uuid,tenant_id,username,source_username,full_name_ar,dateofbirth,gender,email,
                    phone_e164,bank_name_ar,account_number,account_type_ar,balance_sar,
                    available_balance_sar,daily_spend_limit_sar,hashedpassword,status,nafath_linked,
                    kyc_status,kyc_tier,risk_rating,last_login_at,createdat,updatedat)
                   VALUES (%s,'evaluation-tenant',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           'active','Yes','verified',2,'low',%s,%s,%s)
                   ON CONFLICT (uuid) DO NOTHING""",
                (uid, username, username, name, _date(dob), gender, _email(username,index), _phone(index),
                 bank, account, account_type, Decimal(balance), Decimal(balance), Decimal(limit), DEMO_HASH,
                 now - timedelta(days=2), now - timedelta(days=300), now),
            )
            ids[username] = uid
        cur.execute("SELECT uuid::text, source_username FROM users")
        for uid, source_username in cur.fetchall():
            ids.setdefault(source_username, uid)
    return ids


def seed_financial_data(target: psycopg.Connection[Any], users: dict[str, str]) -> dict[str, int]:
    now = datetime.now(RIYADH)
    counts = {
        "beneficiaries": 0,
        "transactions": 0,
        "qattas": 0,
        "qatta_bills": 0,
        "bills": 0,
        "holdings": 0,
    }
    with target.cursor() as cur:
        cur.execute("SELECT uuid::text, username::text, full_name_ar, account_number, balance_sar, status FROM users ORDER BY uuid")
        all_users = cur.fetchall()
        active = [row for row in all_users if row[5] == "active"]
        # Two deterministic beneficiaries per active customer (bounded and realistic).
        for index, owner in enumerate(active):
            for offset, short in ((1, "العائلة"), (2, "صديق")):
                recipient = active[(index + offset) % len(active)]
                if recipient[0] == owner[0]:
                    continue
                bid = str(uuid5(NAMESPACE_URL, f"amad:beneficiary:{owner[0]}:{recipient[3]}"))
                cur.execute(
                    """INSERT INTO beneficiaries
                       (uuid,owner_uuid,full_name,short_name,account_number,status,verified_at,createdat,updatedat)
                       VALUES (%s,%s,%s,%s,%s,'active',%s,%s,%s)
                       ON CONFLICT (owner_uuid,account_number) DO NOTHING""",
                    (bid, owner[0], recipient[2], f"{short}-{offset}", recipient[3], now - timedelta(days=30), now - timedelta(days=60), now),
                )
                counts["beneficiaries"] += cur.rowcount
        # Stable tool fixtures: Latifa is the known active beneficiary for the
        # evaluation and administrator accounts.
        latifa = next((row for row in all_users if row[1] == "user_69491"), None)
        for owner_name in ("evaluation-user", "admin"):
            owner = next((row for row in all_users if row[1] == owner_name), None)
            if owner and latifa:
                beneficiary_id = str(
                    uuid5(NAMESPACE_URL, f"amad:beneficiary:{owner[0]}:{latifa[3]}")
                )
                cur.execute(
                    """INSERT INTO beneficiaries
                       (uuid,owner_uuid,full_name,short_name,account_number,status,
                        verified_at,createdat,updatedat)
                       VALUES (%s,%s,%s,'لطيفة',%s,'active',%s,%s,%s)
                       ON CONFLICT (owner_uuid,account_number) DO UPDATE SET
                         full_name=EXCLUDED.full_name,
                         short_name=EXCLUDED.short_name,
                         status='active',
                         verified_at=EXCLUDED.verified_at,
                         updatedat=EXCLUDED.updatedat""",
                    (
                        beneficiary_id,
                        owner[0],
                        latifa[2],
                        latifa[3],
                        now - timedelta(days=30),
                        now - timedelta(days=60),
                        now,
                    ),
                )
        # Three months of ledger data for every active account.
        for uid, username, _name, account, current_balance, _status in active:
            history: list[dict[str, Any]] = []
            month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            for offset in (2, 1, 0):
                start = month
                for _ in range(offset):
                    start = (start - timedelta(days=1)).replace(day=1)
                history.extend(item for item in _monthly_activity(start) if item["moment"] <= now)
            history.sort(key=lambda item: item["moment"])
            running = Decimal(str(current_balance))
            balances: list[Decimal] = []
            for item in reversed(history):
                balances.append(running)
                running += item["amount"] if item["direction"] == "debit" else -item["amount"]
            balances.reverse()
            for sequence, (item, balance_after) in enumerate(zip(history, balances), start=1):
                reference = f"seed-{str(username).replace('_','-')}-{sequence:03d}-{uid[-6:]}"
                tid = str(uuid5(NAMESPACE_URL, f"amad:transaction:{uid}:{item['moment'].isoformat()}:{sequence}"))
                cur.execute(
                    """INSERT INTO transactions
                       (uuid,user_uuid,account_number,direction,transaction_type,amount_sar,
                        counterparty_name,description,category,balance_after_sar,reference,channel,merchant_city,createdat)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'seed','Riyadh',%s)
                       ON CONFLICT (uuid) DO NOTHING""",
                    (tid, uid, account, item["direction"], item["type"], item["amount"], item["counterparty"],
                     item["description"], item["category"], balance_after, reference, item["moment"]),
                )
                counts["transactions"] += cur.rowcount
        assets = (("ARAMCO","Saudi Aramco","27.80"),("ALRAJHI","Al Rajhi Bank","96.40"),("SABIC","SABIC","61.20"))
        for symbol, name, price in assets:
            cur.execute("INSERT INTO investment_assets (symbol,name,price_sar,updatedat) VALUES (%s,%s,%s,%s) ON CONFLICT (symbol) DO UPDATE SET price_sar=EXCLUDED.price_sar,updatedat=EXCLUDED.updatedat", (symbol,name,Decimal(price),now))
        for username in ("evaluation-user", "admin"):
            uid = users.get(username)
            if uid:
                hid = str(uuid5(NAMESPACE_URL, f"amad:holding:{uid}:ARAMCO"))
                cur.execute("INSERT INTO investment_holdings (uuid,user_uuid,symbol,quantity,average_cost_sar,updatedat) VALUES (%s,%s,'ARAMCO',20,26.50,%s) ON CONFLICT (user_uuid,symbol) DO NOTHING", (hid,uid,now))
                counts["holdings"] += cur.rowcount
        creator_id = users.get("admin")
        participants = [users.get(name) for name in ("admin", "evaluation-user", "user_69491")]
        if creator_id and all(participants):
            cur.execute(
                """SELECT uuid::text FROM qattas
                   WHERE creator_uuid=%s AND name='قطة عشاء الجمعة' AND status='open'
                   ORDER BY createdat LIMIT 1""",
                (creator_id,),
            )
            existing_qatta = cur.fetchone()
            if existing_qatta:
                qatta_id = existing_qatta[0]
            else:
                qatta_id = str(uuid5(NAMESPACE_URL, "amad:qatta:friday-dinner"))
                cur.execute(
                    """INSERT INTO qattas
                       (uuid,creator_uuid,name,total_amount_sar,share_amount_sar,status,createdat,updatedat)
                       VALUES (%s,%s,'قطة عشاء الجمعة',300,100,'open',%s,%s)
                       ON CONFLICT (uuid) DO NOTHING""",
                    (qatta_id, creator_id, now, now),
                )
                counts["qattas"] += cur.rowcount
            for participant_id, status in zip(participants, ("paid", "unpaid", "unpaid")):
                qatta_bill_id = str(
                    uuid5(NAMESPACE_URL, f"amad:qatta-bill:{qatta_id}:{participant_id}")
                )
                cur.execute(
                    """INSERT INTO qatta_bills
                       (uuid,qatta_uuid,participant_uuid,amount_sar,status,paidat,createdat)
                       VALUES (%s,%s,%s,100,%s,%s,%s)
                       ON CONFLICT (qatta_uuid,participant_uuid) DO NOTHING""",
                    (qatta_bill_id, qatta_id, participant_id, status,
                     now if status == "paid" else None, now),
                )
                counts["qatta_bills"] += cur.rowcount
        bills = (("evaluation-user","30012345671234","الشركة السعودية للكهرباء","348.60"),("evaluation-user","20098765435678","شركة المياه الوطنية","86.25"),("evaluation-user","96655544439012","STC","129.00"),("admin","30011122238888","الشركة السعودية للكهرباء","512.40"),("waleed","40077766624444","المرور - رسوم مخالفات","20000.00"))
        for username, number, biller, amount in bills:
            if username not in users:
                continue
            fid = str(uuid5(NAMESPACE_URL, f"amad:bill:{number}"))
            cur.execute("INSERT INTO fatoorahs (uuid,user_uuid,bill_number,biller_name_ar,amount_sar,status,duedate,createdat) VALUES (%s,%s,%s,%s,%s,'unpaid',%s,%s) ON CONFLICT (bill_number) DO NOTHING", (fid,users[username],number,biller,Decimal(amount),now+timedelta(days=14),now))
            counts["bills"] += cur.rowcount
    return counts


def main() -> None:
    load_backend_environment()
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--basic-users-csv", type=Path, default=ROOT / "fake_users_1000 (1).csv"
    )
    parser.add_argument(
        "--advanced-users-csv",
        type=Path,
        default=ROOT / "nafi_1000_fake_users_advanced.csv",
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL in .env.backend is required")
    for path in (args.basic_users_csv, args.advanced_users_csv):
        if not path.is_file():
            raise SystemExit(f"CSV source not found: {path}")
    with args.basic_users_csv.open(encoding="utf-8-sig", newline="") as basic_file:
        basic_rows = list(csv.DictReader(basic_file))
    with args.advanced_users_csv.open(encoding="utf-8-sig", newline="") as advanced_file:
        advanced_rows = list(csv.DictReader(advanced_file))
    with psycopg.connect(_postgres_url(args.database_url)) as target:
        platform_count = import_platform_users(basic_rows, target)
        bank_count, _ = import_bank_users(advanced_rows, target)
        users = add_operational_users(target)
        seeded = seed_financial_data(target, users)
    print(
        json.dumps(
            {"platform_users": platform_count, "bank_users": bank_count, **seeded},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
