"""Self-contained SQLite bank database backing the bank tool implementations.

The ``users`` table continues the teammate-owned Saudi banking schema (one row
per customer with their IBAN, Arabic bank name, balance, daily spend limit,
and Nafath status). This module adds the two tables the agent tools need:

- ``beneficiaries``: each customer's approved transfer destinations. A
  destination must be added and active here before any money can move to it.
- ``transactions``: a per-account ledger (debits and credits) used for
  transfer receipts and the monthly report.

Ownership never comes from model-controlled arguments. The authenticated
identity is read from ``BANK_TOOL_USER_ID`` / ``BANK_TOOL_TENANT_ID`` (the
trusted integration channel for this deployment) and resolved against
``users.Username``. The database file location is controlled with
``BANK_DB_PATH``.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from calendar import monthrange
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from agentic.tools.runtime_identity import current_tool_identity

T = TypeVar("T")

_DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "bank.db"

_seed_lock = threading.Lock()
_seeded_paths: set[str] = set()

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class BankToolArgs(BaseModel):
    """Base argument schema that rejects model-invented or misspelled fields."""

    model_config = ConfigDict(extra="forbid")


def db_path() -> str:
    return os.getenv("BANK_DB_PATH", str(_DEFAULT_DB_PATH))


def owner_identity() -> tuple[str, str]:
    """Read the request-scoped owner, with an explicit local-demo fallback."""

    return current_tool_identity() or (
        os.getenv("BANK_TOOL_USER_ID", "evaluation-user"),
        os.getenv("BANK_TOOL_TENANT_ID", "evaluation-tenant"),
    )


def money(value: Any) -> Decimal:
    """Normalize a stored or supplied amount to an exact two-decimal value."""

    return Decimal(str(value)).quantize(Decimal("0.01"))


def normalize_account_number(value: str) -> str:
    """Canonicalize an IBAN/account number for comparison and storage."""

    return "".join(value.split()).replace("-", "").upper()


# Saudi Arabia is UTC+3 with no daylight saving. All bank data — transaction
# timestamps, the daily-limit day window, and monthly report boundaries — is
# recorded and computed in Riyadh time.
RIYADH_TZ = timezone(timedelta(hours=3))


def riyadh_now() -> datetime:
    return datetime.now(RIYADH_TZ)


def timestamp(moment: datetime | None = None) -> str:
    return (moment or riyadh_now()).strftime(TIMESTAMP_FORMAT)


def month_bounds(month: str) -> tuple[str, str]:
    """Return inclusive-start/exclusive-end timestamp bounds for ``YYYY-MM``."""

    year, month_number = int(month[:4]), int(month[5:7])
    start = datetime(year, month_number, 1)
    end = start + timedelta(days=monthrange(year, month_number)[1])
    return start.strftime(TIMESTAMP_FORMAT), end.strftime(TIMESTAMP_FORMAT)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uuid TEXT PRIMARY KEY,
    Username TEXT NOT NULL UNIQUE,
    Full_Name_Ar TEXT NOT NULL,
    dateOfBirth TEXT,
    gender TEXT CHECK (gender IN ('Male', 'Female')),
    Bank_Name_Ar TEXT NOT NULL,
    Account_Number TEXT NOT NULL UNIQUE,
    Account_Type_Ar TEXT NOT NULL,
    Balance_SAR REAL NOT NULL DEFAULT 0 CHECK (Balance_SAR >= 0),
    Daily_Spend_Limit_SAR REAL NOT NULL DEFAULT 5000,
    hashedPassword TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    Nafath_Linked TEXT NOT NULL DEFAULT 'No' CHECK (Nafath_Linked IN ('Yes', 'No')),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS beneficiaries (
    uuid TEXT PRIMARY KEY,
    owner_uuid TEXT NOT NULL REFERENCES users (uuid),
    Full_Name TEXT NOT NULL,
    Short_Name TEXT NOT NULL,
    Account_Number TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL,
    UNIQUE (owner_uuid, Account_Number)
);
CREATE INDEX IF NOT EXISTS ix_beneficiaries_owner ON beneficiaries (owner_uuid);
-- A unique index (not a table constraint) so databases created before this
-- rule existed also receive it.
CREATE UNIQUE INDEX IF NOT EXISTS ux_beneficiaries_owner_short_name
    ON beneficiaries (owner_uuid, Short_Name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS qattas (
    uuid TEXT PRIMARY KEY,
    creator_uuid TEXT NOT NULL REFERENCES users (uuid),
    Name TEXT NOT NULL,
    Total_Amount_SAR REAL NOT NULL CHECK (Total_Amount_SAR > 0),
    Share_Amount_SAR REAL NOT NULL CHECK (Share_Amount_SAR > 0),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed')),
    createdAt TEXT NOT NULL,
    updatedAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_qattas_creator ON qattas (creator_uuid);

CREATE TABLE IF NOT EXISTS qatta_bills (
    uuid TEXT PRIMARY KEY,
    qatta_uuid TEXT NOT NULL REFERENCES qattas (uuid),
    participant_uuid TEXT NOT NULL REFERENCES users (uuid),
    Amount_SAR REAL NOT NULL CHECK (Amount_SAR > 0),
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK (status IN ('unpaid', 'paid')),
    paidAt TEXT,
    createdAt TEXT NOT NULL,
    UNIQUE (qatta_uuid, participant_uuid)
);
CREATE INDEX IF NOT EXISTS ix_qatta_bills_participant
    ON qatta_bills (participant_uuid, status);

CREATE TABLE IF NOT EXISTS fatoorahs (
    uuid TEXT PRIMARY KEY,
    user_uuid TEXT NOT NULL REFERENCES users (uuid),
    Bill_Number TEXT NOT NULL UNIQUE CHECK (Bill_Number NOT GLOB '*[^0-9]*'),
    Biller_Name_Ar TEXT NOT NULL,
    Amount_SAR REAL NOT NULL CHECK (Amount_SAR > 0),
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK (status IN ('unpaid', 'paid')),
    dueDate TEXT,
    paidAt TEXT,
    createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fatoorahs_user_status ON fatoorahs (user_uuid, status);

CREATE TABLE IF NOT EXISTS transactions (
    uuid TEXT PRIMARY KEY,
    user_uuid TEXT NOT NULL REFERENCES users (uuid),
    Account_Number TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
    Transaction_Type TEXT NOT NULL,
    Amount_SAR REAL NOT NULL CHECK (Amount_SAR > 0),
    Counterparty_Name TEXT,
    Counterparty_Account TEXT,
    Description TEXT NOT NULL,
    Category TEXT NOT NULL DEFAULT 'general',
    Balance_After_SAR REAL NOT NULL,
    Reference TEXT NOT NULL,
    createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transactions_user_created
    ON transactions (user_uuid, createdAt);

CREATE TABLE IF NOT EXISTS investment_assets (
    symbol TEXT PRIMARY KEY,
    Name TEXT NOT NULL,
    Price_SAR REAL NOT NULL CHECK (Price_SAR > 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    updatedAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investment_holdings (
    uuid TEXT PRIMARY KEY,
    user_uuid TEXT NOT NULL REFERENCES users (uuid),
    symbol TEXT NOT NULL REFERENCES investment_assets (symbol),
    Quantity REAL NOT NULL CHECK (Quantity >= 0),
    Average_Cost_SAR REAL NOT NULL CHECK (Average_Cost_SAR >= 0),
    updatedAt TEXT NOT NULL,
    UNIQUE (user_uuid, symbol)
);
CREATE INDEX IF NOT EXISTS ix_investment_holdings_user
    ON investment_holdings (user_uuid);
"""


def _connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _transaction(connection: sqlite3.Connection, work: Callable[[sqlite3.Connection], T]) -> T:
    connection.execute("BEGIN IMMEDIATE")
    try:
        result = work(connection)
        connection.execute("COMMIT")
        return result
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _ensure_ready(path: str) -> None:
    with _seed_lock:
        if path in _seeded_paths:
            return
        connection = _connect(path)
        try:
            connection.executescript(_SCHEMA)
            _transaction(connection, _seed_if_empty)
            # These run separately so databases created before each feature
            # existed still receive its demo rows.
            _transaction(connection, _seed_qatta_if_empty)
            _transaction(connection, _seed_fatoorahs_if_empty)
            _transaction(connection, _seed_investments_if_empty)
        finally:
            connection.close()
        _seeded_paths.add(path)


async def run_in_bank_db(work: Callable[[sqlite3.Connection], T]) -> T:
    """Run ``work`` inside one atomic database transaction on a worker thread."""

    path = db_path()

    def _execute() -> T:
        _ensure_ready(path)
        connection = _connect(path)
        try:
            return _transaction(connection, work)
        finally:
            connection.close()

    return await asyncio.to_thread(_execute)


def reset_bank_state() -> None:
    """Drop the database file and forget seeding — used between test scenarios."""

    with _seed_lock:
        path = db_path()
        _seeded_paths.discard(path)
        Path(path).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Seed data — continues the teammate-owned users dataset.
# --------------------------------------------------------------------------

_DEMO_HASH = "b2372c8b34afcaa4dddda3084c16012fbd463639519d15fff945f3c321b15d43"

_SEED_USERS: tuple[dict[str, Any], ...] = (
    {
        "uuid": "81526b85-5f2b-4bc5-a623-adad6198009c",
        "Username": "admin",
        "Full_Name_Ar": "عبدالإله سعيد المسفر",
        "dateOfBirth": "2005-03-15",
        "gender": "Male",
        "Bank_Name_Ar": "مصرف الإنماء",
        "Account_Number": "SA80050000100200300401",
        "Account_Type_Ar": "حساب جاري",
        "Balance_SAR": 150000.0,
        "Daily_Spend_Limit_SAR": 50000.0,
        "hashedPassword": "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f",
        "status": "active",
        "Nafath_Linked": "Yes",
        "createdAt": "2026-01-01 10:00:00",
        "updatedAt": "2026-07-14 06:00:00",
    },
    {
        "uuid": "c38af53d-56fd-4302-addc-6b6c751b2592",
        "Username": "user_76316",
        "Full_Name_Ar": "سعود العنزي",
        "dateOfBirth": "1990-04-10",
        "gender": "Male",
        "Bank_Name_Ar": "مصرف الراجحي",
        "Account_Number": "SA91000032763205429515",
        "Account_Type_Ar": "محفظة استثمارية",
        "Balance_SAR": 4425.36,
        "Daily_Spend_Limit_SAR": 50000.0,
        "hashedPassword": _DEMO_HASH,
        "status": "inactive",
        "Nafath_Linked": "Yes",
        "createdAt": "2024-04-17 00:00:00",
        "updatedAt": "2024-05-08 00:00:00",
    },
    {
        "uuid": "6eb24d8f-7301-48e7-892e-6fce09985ab9",
        "Username": "user_69491",
        "Full_Name_Ar": "لطيفة العنزي",
        "dateOfBirth": "1981-01-04",
        "gender": "Female",
        "Bank_Name_Ar": "البنك الأهلي السعودي",
        "Account_Number": "SA98000068368508501525",
        "Account_Type_Ar": "حساب ادخار",
        "Balance_SAR": 32716.0,
        "Daily_Spend_Limit_SAR": 10000.0,
        "hashedPassword": _DEMO_HASH,
        "status": "active",
        "Nafath_Linked": "Yes",
        "createdAt": "2023-01-13 00:00:00",
        "updatedAt": "2023-01-23 00:00:00",
    },
    # The identity used by the agent evaluation harness and local tests.
    {
        "uuid": "3f1f7a3e-8d1e-4a67-9f7d-2b6f3a1c9e01",
        "Username": "evaluation-user",
        "Full_Name_Ar": "أحمد فهد العتيبي",
        "dateOfBirth": "1994-08-22",
        "gender": "Male",
        "Bank_Name_Ar": "مصرف الإنماء",
        "Account_Number": "SA4405000068201234567890",
        "Account_Type_Ar": "حساب جاري",
        "Balance_SAR": 25431.50,
        "Daily_Spend_Limit_SAR": 5000.0,
        "hashedPassword": _DEMO_HASH,
        "status": "active",
        "Nafath_Linked": "Yes",
        "createdAt": "2025-11-02 09:30:00",
        "updatedAt": "2026-07-01 08:15:00",
    },
    {
        "uuid": "9d2c5b74-6a0f-4e3b-8c11-5e9a7d4f2b02",
        "Username": "user_55210",
        "Full_Name_Ar": "محمد ناصر القحطاني",
        "dateOfBirth": "1988-11-30",
        "gender": "Male",
        "Bank_Name_Ar": "بنك الرياض",
        "Account_Number": "SA0320000005556667772222",
        "Account_Type_Ar": "حساب جاري",
        "Balance_SAR": 8400.0,
        "Daily_Spend_Limit_SAR": 20000.0,
        "hashedPassword": _DEMO_HASH,
        "status": "active",
        "Nafath_Linked": "Yes",
        "createdAt": "2024-09-19 00:00:00",
        "updatedAt": "2026-06-11 00:00:00",
    },
    {
        "uuid": "7c3d9f81-2e5a-4b18-9d64-1f8e6a2c4b05",
        "Username": "waleed",
        "Full_Name_Ar": "الوليد خالد الشمري",
        "dateOfBirth": "1999-05-20",
        "gender": "Male",
        "Bank_Name_Ar": "بنك البلاد",
        "Account_Number": "SA6015000078965432101234",
        "Account_Type_Ar": "حساب جاري",
        "Balance_SAR": 15000.0,
        "Daily_Spend_Limit_SAR": 10000.0,
        "hashedPassword": _DEMO_HASH,
        "status": "active",
        "Nafath_Linked": "Yes",
        "createdAt": "2025-08-15 00:00:00",
        "updatedAt": "2026-07-01 00:00:00",
    },
    {
        "uuid": "5a8e1c29-3b7d-4f56-a0e2-7c4d9b8e6f03",
        "Username": "user_83777",
        "Full_Name_Ar": "نورة سلطان الحربي",
        "dateOfBirth": "1997-02-14",
        "gender": "Female",
        "Bank_Name_Ar": "البنك السعودي الأول",
        "Account_Number": "SA1545000003334445553333",
        "Account_Type_Ar": "حساب جاري",
        "Balance_SAR": 19750.0,
        "Daily_Spend_Limit_SAR": 15000.0,
        "hashedPassword": _DEMO_HASH,
        "status": "active",
        "Nafath_Linked": "No",
        "createdAt": "2025-03-08 00:00:00",
        "updatedAt": "2026-05-27 00:00:00",
    },
)

# Latifa is pre-registered for the evaluation user so a transfer works out of
# the box; Mohammed and Noura stay unregistered so ``add_benefit`` has real
# active accounts to verify and add. Saud's account is inactive on purpose to
# demonstrate rejection paths.
_SEED_BENEFICIARIES: tuple[dict[str, str], ...] = (
    {
        "owner_username": "evaluation-user",
        "Full_Name": "لطيفة العنزي",
        "Short_Name": "لطيفة",
        "Account_Number": "SA98000068368508501525",
    },
    {
        "owner_username": "admin",
        "Full_Name": "لطيفة العنزي",
        "Short_Name": "لطيفة",
        "Account_Number": "SA98000068368508501525",
    },
)


def _monthly_activity(month_start: datetime) -> tuple[dict[str, Any], ...]:
    """Deterministic activity template applied to each seeded month."""

    def at(day: int, hour: int) -> datetime:
        return month_start.replace(day=day, hour=hour)

    return (
        {"moment": at(1, 9), "direction": "credit", "amount": Decimal("15500.00"),
         "type": "salary", "counterparty": "شركة أمد للتقنية",
         "description": "إيداع راتب شهري", "category": "راتب"},
        {"moment": at(3, 18), "direction": "debit", "amount": Decimal("4200.00"),
         "type": "rent", "counterparty": "شركة الفيصلية العقارية",
         "description": "إيجار شقة", "category": "سكن"},
        {"moment": at(6, 12), "direction": "debit", "amount": Decimal("612.40"),
         "type": "purchase", "counterparty": "أسواق بنده",
         "description": "مشتريات بقالة", "category": "بقالة"},
        {"moment": at(9, 20), "direction": "debit", "amount": Decimal("389.00"),
         "type": "bill_payment", "counterparty": "الشركة السعودية للكهرباء",
         "description": "فاتورة كهرباء", "category": "فواتير"},
        {"moment": at(12, 14), "direction": "debit", "amount": Decimal("145.00"),
         "type": "bill_payment", "counterparty": "STC",
         "description": "فاتورة جوال وإنترنت", "category": "فواتير"},
        {"moment": at(15, 10), "direction": "credit", "amount": Decimal("750.00"),
         "type": "transfer_in", "counterparty": "لطيفة العنزي",
         "description": "تسديد مشاركة رحلة", "category": "حوالات"},
        {"moment": at(19, 21), "direction": "debit", "amount": Decimal("264.75"),
         "type": "purchase", "counterparty": "هنقرستيشن",
         "description": "طلبات طعام", "category": "مطاعم"},
        {"moment": at(24, 16), "direction": "debit", "amount": Decimal("980.00"),
         "type": "purchase", "counterparty": "مكتبة جرير",
         "description": "مشتريات إلكترونيات", "category": "تسوق"},
    )


def _seed_user_history(connection: sqlite3.Connection, user: sqlite3.Row) -> None:
    """Insert three calendar months of ledger history ending at today's balance."""

    now = riyadh_now().replace(tzinfo=None)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    history: list[dict[str, Any]] = []
    for offset in (2, 1, 0):
        cursor_month = month_start
        for _ in range(offset):
            cursor_month = (cursor_month - timedelta(days=1)).replace(day=1)
        history.extend(
            item for item in _monthly_activity(cursor_month) if item["moment"] <= now
        )
    history.sort(key=lambda item: item["moment"])

    # Replay backwards from the current balance so ``Balance_After_SAR`` of the
    # newest entry equals the user's seeded balance exactly.
    balances_after: list[Decimal] = []
    running = money(user["Balance_SAR"])
    for item in reversed(history):
        balances_after.append(running)
        delta = item["amount"]
        running += delta if item["direction"] == "debit" else -delta
    balances_after.reverse()

    for sequence, (item, balance_after) in enumerate(zip(history, balances_after), start=1):
        connection.execute(
            "INSERT INTO transactions"
            " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
            "  Counterparty_Name, Counterparty_Account, Description, Category,"
            "  Balance_After_SAR, Reference, createdAt)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                user["uuid"],
                user["Account_Number"],
                item["direction"],
                item["type"],
                float(item["amount"]),
                item["counterparty"],
                item["description"],
                item["category"],
                float(balance_after),
                f"seed-{user['Username']}-{sequence:06d}",
                timestamp(item["moment"]),
            ),
        )


def _seed_if_empty(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        return

    for user in _SEED_USERS:
        connection.execute(
            "INSERT INTO users"
            " (uuid, Username, Full_Name_Ar, dateOfBirth, gender, Bank_Name_Ar,"
            "  Account_Number, Account_Type_Ar, Balance_SAR, Daily_Spend_Limit_SAR,"
            "  hashedPassword, status, Nafath_Linked, createdAt, updatedAt)"
            " VALUES (:uuid, :Username, :Full_Name_Ar, :dateOfBirth, :gender, :Bank_Name_Ar,"
            "  :Account_Number, :Account_Type_Ar, :Balance_SAR, :Daily_Spend_Limit_SAR,"
            "  :hashedPassword, :status, :Nafath_Linked, :createdAt, :updatedAt)",
            user,
        )

    now = timestamp()
    for beneficiary in _SEED_BENEFICIARIES:
        owner = connection.execute(
            "SELECT uuid FROM users WHERE Username = ?", (beneficiary["owner_username"],)
        ).fetchone()
        connection.execute(
            "INSERT INTO beneficiaries"
            " (uuid, owner_uuid, Full_Name, Short_Name, Account_Number, status,"
            "  createdAt, updatedAt)"
            " VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                str(uuid4()),
                owner["uuid"],
                beneficiary["Full_Name"],
                beneficiary["Short_Name"],
                beneficiary["Account_Number"],
                now,
                now,
            ),
        )

    for username in ("evaluation-user", "admin"):
        user = connection.execute(
            "SELECT * FROM users WHERE Username = ?", (username,)
        ).fetchone()
        _seed_user_history(connection, user)


def _seed_qatta_if_empty(connection: sqlite3.Connection) -> None:
    """Seed one open demo qatta: عبدالإله's dinner split with two unpaid shares."""

    if connection.execute("SELECT COUNT(*) FROM qattas").fetchone()[0]:
        return
    creator = connection.execute(
        "SELECT uuid FROM users WHERE Username = 'admin'"
    ).fetchone()
    if creator is None:
        return
    now = timestamp()
    qatta_id = str(uuid4())
    connection.execute(
        "INSERT INTO qattas"
        " (uuid, creator_uuid, Name, Total_Amount_SAR, Share_Amount_SAR, status,"
        "  createdAt, updatedAt)"
        " VALUES (?, ?, 'قطة عشاء الجمعة', 300.0, 100.0, 'open', ?, ?)",
        (qatta_id, creator["uuid"], now, now),
    )
    for username, status in (("admin", "paid"), ("evaluation-user", "unpaid"),
                             ("user_69491", "unpaid")):
        participant = connection.execute(
            "SELECT uuid FROM users WHERE Username = ?", (username,)
        ).fetchone()
        connection.execute(
            "INSERT INTO qatta_bills"
            " (uuid, qatta_uuid, participant_uuid, Amount_SAR, status, paidAt, createdAt)"
            " VALUES (?, ?, ?, 100.0, ?, ?, ?)",
            (
                str(uuid4()),
                qatta_id,
                participant["uuid"],
                status,
                now if status == "paid" else None,
                now,
            ),
        )


# SADAD-style numeric bill numbers; the last four digits identify the bill
# for payment, so they are distinct per user.
_SEED_FATOORAHS: tuple[dict[str, Any], ...] = (
    {"owner_username": "evaluation-user", "Bill_Number": "30012345671234",
     "Biller_Name_Ar": "الشركة السعودية للكهرباء", "Amount_SAR": 348.60},
    {"owner_username": "evaluation-user", "Bill_Number": "20098765435678",
     "Biller_Name_Ar": "شركة المياه الوطنية", "Amount_SAR": 86.25},
    {"owner_username": "evaluation-user", "Bill_Number": "96655544439012",
     "Biller_Name_Ar": "STC", "Amount_SAR": 129.00},
    {"owner_username": "admin", "Bill_Number": "30011122238888",
     "Biller_Name_Ar": "الشركة السعودية للكهرباء", "Amount_SAR": 512.40},
    # Deliberately larger than وليد's 15,000 balance to demo the rejection.
    {"owner_username": "waleed", "Bill_Number": "40077766624444",
     "Biller_Name_Ar": "المرور - رسوم مخالفات", "Amount_SAR": 20000.00},
)


def _seed_fatoorahs_if_empty(connection: sqlite3.Connection) -> None:
    """Seed unpaid demo bills, each assigned to a specific bank customer."""

    if connection.execute("SELECT COUNT(*) FROM fatoorahs").fetchone()[0]:
        return
    now = riyadh_now()
    created = timestamp(now)
    due = timestamp(now + timedelta(days=14))
    for fatoorah in _SEED_FATOORAHS:
        owner = connection.execute(
            "SELECT uuid FROM users WHERE Username = ?",
            (fatoorah["owner_username"],),
        ).fetchone()
        if owner is None:
            continue
        connection.execute(
            "INSERT INTO fatoorahs"
            " (uuid, user_uuid, Bill_Number, Biller_Name_Ar, Amount_SAR, status,"
            "  dueDate, paidAt, createdAt)"
            " VALUES (?, ?, ?, ?, ?, 'unpaid', ?, NULL, ?)",
            (
                str(uuid4()),
                owner["uuid"],
                fatoorah["Bill_Number"],
                fatoorah["Biller_Name_Ar"],
                fatoorah["Amount_SAR"],
                due,
                created,
            ),
        )


def _seed_investments_if_empty(connection: sqlite3.Connection) -> None:
    """Seed deterministic demo prices and a small authenticated-user portfolio."""

    now = timestamp()
    assets = (
        ("ARAMCO", "Saudi Aramco", 27.80),
        ("ALRAJHI", "Al Rajhi Bank", 96.40),
        ("SABIC", "SABIC", 61.20),
    )
    for symbol, name, price in assets:
        connection.execute(
            "INSERT OR IGNORE INTO investment_assets"
            " (symbol, Name, Price_SAR, status, updatedAt)"
            " VALUES (?, ?, ?, 'active', ?)",
            (symbol, name, price, now),
        )
    owner = connection.execute(
        "SELECT uuid FROM users WHERE Username = 'evaluation-user'"
    ).fetchone()
    if owner is not None:
        connection.execute(
            "INSERT OR IGNORE INTO investment_holdings"
            " (uuid, user_uuid, symbol, Quantity, Average_Cost_SAR, updatedAt)"
            " VALUES (?, ?, 'ARAMCO', 20, 26.50, ?)",
            (str(uuid4()), owner["uuid"], now),
        )


# --------------------------------------------------------------------------
# Shared queries
# --------------------------------------------------------------------------

def find_user_by_username(connection: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM users WHERE Username = ?", (username,)
    ).fetchone()


def find_user_by_account_number(
    connection: sqlite3.Connection, account_number: str
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM users WHERE Account_Number = ?", (account_number,)
    ).fetchone()


def find_beneficiary(
    connection: sqlite3.Connection, owner_uuid: str, destination: str
) -> sqlite3.Row | None:
    """Match a beneficiary by exact account number or by saved short name."""

    normalized = normalize_account_number(destination)
    row = connection.execute(
        "SELECT * FROM beneficiaries WHERE owner_uuid = ? AND Account_Number = ?",
        (owner_uuid, normalized),
    ).fetchone()
    if row is not None:
        return row
    return connection.execute(
        "SELECT * FROM beneficiaries WHERE owner_uuid = ?"
        " AND (Short_Name = ? COLLATE NOCASE OR Full_Name = ? COLLATE NOCASE)",
        (owner_uuid, destination.strip(), destination.strip()),
    ).fetchone()


def spent_today(connection: sqlite3.Connection, user_uuid: str) -> Decimal:
    """Total debited today, used to enforce ``Daily_Spend_Limit_SAR``.

    Every outgoing financial debit contributes to the same limit. The day
    window follows Riyadh time, so the allowance resets at Saudi midnight.
    """

    day_start = riyadh_now().strftime("%Y-%m-%d 00:00:00")
    total = connection.execute(
        "SELECT COALESCE(SUM(Amount_SAR), 0) FROM transactions"
        " WHERE user_uuid = ? AND direction = 'debit' AND createdAt >= ?",
        (user_uuid, day_start),
    ).fetchone()[0]
    return money(total)


def next_reference(connection: sqlite3.Connection, prefix: str) -> str:
    count = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    return f"bank-{prefix}-{count + 1:06d}"


def tool_result(
    *,
    status: str,
    summary: str,
    data: dict[str, Any],
    receipt_id: str | None = None,
    operation_id: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Build the ``ToolResult`` envelope with trusted owner metadata."""

    user_id, tenant_id = owner_identity()
    return {
        "status": status,
        "summary": summary,
        "data": data,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "receipt_id": receipt_id,
        "operation_id": operation_id,
        "error_code": error_code,
    }
