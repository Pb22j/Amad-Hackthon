"""PostgreSQL connection and shared queries for the financial tools.

The Alembic schema and ``scripts/seed_postgres.py`` own all DDL and demo data.
Tool identity always comes from authenticated request context, never model
arguments. Connections use Riyadh time and every tool callback is atomic.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import unicodedata
from calendar import monthrange
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, TypeVar

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from agentic.tools.runtime_identity import current_tool_identity

T = TypeVar("T")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
RIYADH_TZ = timezone(timedelta(hours=3))

_schema_lock = threading.Lock()
_checked_urls: set[str] = set()


class BankToolArgs(BaseModel):
    """Base argument schema that rejects model-invented or misspelled fields."""

    model_config = ConfigDict(extra="forbid")


class BankRow:
    """Case-insensitive mapping compatible with the legacy tool field names."""

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values
        self._keys = list(values)
        self._folded = {key.casefold(): key for key in values}

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[self._keys[key]]
        return self._values[self._folded.get(key.casefold(), key)]

    def keys(self) -> list[str]:
        return self._keys.copy()


class BankCursor:
    def __init__(self, cursor: psycopg.Cursor[Any]) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self) -> BankRow | None:
        row = self._cursor.fetchone()
        return BankRow(row) if row is not None else None

    def fetchall(self) -> list[BankRow]:
        return [BankRow(row) for row in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[BankRow]:
        for row in self._cursor:
            yield BankRow(row)


class BankConnection:
    def __init__(self, url: str) -> None:
        self._connection = psycopg.connect(url, autocommit=True, row_factory=dict_row)
        self._connection.execute("SET TIME ZONE 'Asia/Riyadh'")

    def execute(self, statement: str, parameters: Any = None) -> BankCursor:
        cursor = self._connection.cursor()
        cursor.execute(statement, parameters or ())
        return BankCursor(cursor)

    def close(self) -> None:
        self._connection.close()


def bank_database_url() -> str:
    configured = os.getenv("BANK_DATABASE_URL") or os.getenv("DATABASE_URL", "")
    normalized = configured.replace("postgresql+psycopg://", "postgresql://", 1)
    if not normalized.startswith("postgresql://"):
        raise RuntimeError("BANK_DATABASE_URL must be a PostgreSQL URL")
    return normalized


def owner_identity() -> tuple[str, str]:
    return current_tool_identity() or (
        os.getenv("BANK_TOOL_USER_ID", "evaluation-user"),
        os.getenv("BANK_TOOL_TENANT_ID", "evaluation-tenant"),
    )


def money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def normalize_account_number(value: str) -> str:
    return "".join(value.split()).replace("-", "").upper()


def normalize_beneficiary_name(value: str) -> str:
    """Normalize harmless spelling differences used when resolving saved names."""

    folded = unicodedata.normalize("NFKC", value).casefold().strip()
    folded = "".join(
        character
        for character in folded
        if not unicodedata.combining(character) and character != "ـ"
    )
    folded = folded.translate(
        str.maketrans(
            {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي"}
        )
    )
    return " ".join(folded.split())


_ARABIC_TRANSLITERATION = str.maketrans(
    {
        "ا": "a", "أ": "a", "إ": "a", "آ": "a", "ٱ": "a",
        "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h",
        "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
        "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t",
        "ظ": "z", "ع": "", "غ": "gh", "ف": "f", "ق": "q",
        "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h",
        "ة": "a", "و": "u", "ؤ": "u", "ي": "i", "ى": "i",
        "ئ": "i", "ء": "",
    }
)


def beneficiary_name_key(value: str) -> str:
    """Return a conservative consonant key for Arabic/Latin name matching."""

    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and character != "ـ"
    )
    transliterated = normalized.translate(_ARABIC_TRANSLITERATION)
    latin = unicodedata.normalize("NFKD", transliterated)
    letters = "".join(character for character in latin if character.isascii() and character.isalpha())
    return "".join(character for character in letters if character not in "aeiouy")


def riyadh_now() -> datetime:
    return datetime.now(RIYADH_TZ)


def timestamp(moment: datetime | None = None) -> str:
    return (moment or riyadh_now()).strftime(TIMESTAMP_FORMAT)


def month_bounds(month: str) -> tuple[str, str]:
    year, month_number = int(month[:4]), int(month[5:7])
    start = datetime(year, month_number, 1)
    end = start + timedelta(days=monthrange(year, month_number)[1])
    return start.strftime(TIMESTAMP_FORMAT), end.strftime(TIMESTAMP_FORMAT)


def _transaction(connection: BankConnection, work: Callable[[BankConnection], T]) -> T:
    connection.execute("BEGIN")
    try:
        result = work(connection)
        connection.execute("COMMIT")
        return result
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _ensure_ready(url: str) -> None:
    with _schema_lock:
        if url in _checked_urls:
            return
        connection = BankConnection(url)
        try:
            connection.execute("SELECT 1 FROM users LIMIT 1")
            connection.execute("SELECT 1 FROM bank_accounts LIMIT 1")
            connection.execute("SELECT 1 FROM transactions LIMIT 1")
        finally:
            connection.close()
        _checked_urls.add(url)


async def run_in_bank_db(work: Callable[[BankConnection], T]) -> T:
    """Run one financial-tool operation in an atomic PostgreSQL transaction."""

    url = bank_database_url()

    def execute() -> T:
        _ensure_ready(url)
        connection = BankConnection(url)
        try:
            return _transaction(connection, work)
        finally:
            connection.close()

    return await asyncio.to_thread(execute)


_USER_ACCOUNT_PROJECTION = """
    SELECT u.uuid, u.username, u.full_name_ar, u.full_name_en, u.nafi_iban,
           u.daily_spend_limit_sar,
           a.uuid AS account_uuid, a.account_number, a.account_type AS account_type_ar,
           a.bank_name_ar, a.bank_name_en, a.balance_sar,
           (SELECT COALESCE(SUM(total.balance_sar), 0)
              FROM bank_accounts total WHERE total.user_uuid = u.uuid) AS total_balance_sar
      FROM users u
      JOIN bank_accounts a ON a.user_uuid = u.uuid
"""


def find_user_by_username(connection: BankConnection, username: str) -> BankRow | None:
    return connection.execute(
        _USER_ACCOUNT_PROJECTION
        + " WHERE u.username = %s ORDER BY a.is_primary DESC, a.uuid LIMIT 1",
        (username,),
    ).fetchone()


def find_user_by_account_number(
    connection: BankConnection, account_number: str
) -> BankRow | None:
    return connection.execute(
        _USER_ACCOUNT_PROJECTION + " WHERE a.account_number = %s LIMIT 1",
        (account_number,),
    ).fetchone()


def find_user_by_uuid(connection: BankConnection, user_uuid: str) -> BankRow | None:
    return connection.execute(
        _USER_ACCOUNT_PROJECTION
        + " WHERE u.uuid = %s ORDER BY a.is_primary DESC, a.uuid LIMIT 1",
        (user_uuid,),
    ).fetchone()


def find_user_by_nafi_iban(connection: BankConnection, nafi_iban: str) -> BankRow | None:
    return connection.execute(
        _USER_ACCOUNT_PROJECTION
        + " WHERE u.nafi_iban = %s ORDER BY a.is_primary DESC, a.uuid LIMIT 1",
        (normalize_account_number(nafi_iban),),
    ).fetchone()


def update_account_balance(
    connection: BankConnection, user: BankRow, balance: Decimal
) -> None:
    """Update the exact account selected in the projected user row."""

    connection.execute(
        "UPDATE bank_accounts SET balance_sar = %s WHERE uuid = %s",
        (balance, user["account_uuid"]),
    )


def find_beneficiary(
    connection: BankConnection, owner_uuid: str, destination: str
) -> BankRow | None:
    normalized = normalize_account_number(destination)
    projection = """
        SELECT b.uuid, b.owner_uuid, b.beneficiary_uuid, b.short_name,
               target.full_name_ar AS full_name, target.full_name_en,
               target.nafi_iban, account.account_number, account.bank_name_ar
          FROM beneficiaries b
          JOIN users target ON target.uuid = b.beneficiary_uuid
          JOIN bank_accounts account ON account.user_uuid = target.uuid AND account.is_primary
    """
    row = connection.execute(
        projection
        + " WHERE b.owner_uuid = %s AND (target.nafi_iban = %s OR account.account_number = %s)",
        (owner_uuid, normalized, normalized),
    ).fetchone()
    if row is not None:
        return row
    requested_name = normalize_beneficiary_name(destination)
    requested_key = beneficiary_name_key(destination)
    requested_token_keys = {
        beneficiary_name_key(token)
        for token in re.findall(r"[^\W\d_]+", destination, flags=re.UNICODE)
    }
    transliterated_matches: list[BankRow] = []
    short_name_matches: list[BankRow] = []
    for beneficiary in connection.execute(
        projection + " WHERE b.owner_uuid = %s", (owner_uuid,)
    ).fetchall():
        short_name = str(beneficiary["Short_Name"])
        full_name = str(beneficiary["Full_Name"])
        raw_names = {short_name, full_name}
        if requested_name in {normalize_beneficiary_name(name) for name in raw_names}:
            return beneficiary
        normalized_short_name = normalize_beneficiary_name(short_name)
        short_key = beneficiary_name_key(short_name)
        if (
            normalized_short_name
            and re.search(rf"(?<!\w){re.escape(normalized_short_name)}(?!\w)", requested_name)
        ) or (len(short_key) >= 2 and short_key in requested_token_keys):
            short_name_matches.append(beneficiary)
        if len(requested_key) >= 2 and requested_key in {
            beneficiary_name_key(name) for name in raw_names
        }:
            transliterated_matches.append(beneficiary)
    if len(short_name_matches) == 1:
        return short_name_matches[0]
    return transliterated_matches[0] if len(transliterated_matches) == 1 else None


def spent_today(connection: BankConnection, user_uuid: str) -> Decimal:
    day_start = riyadh_now().strftime("%Y-%m-%d 00:00:00")
    now = timestamp()
    total = connection.execute(
        "SELECT COALESCE(SUM(Amount_SAR), 0) FROM transactions"
        " WHERE user_uuid = %s AND direction = 'debit'"
        " AND createdAt >= %s AND createdAt <= %s",
        (user_uuid, day_start, now),
    ).fetchone()[0]
    return money(total)


def next_reference(connection: BankConnection, prefix: str) -> str:
    # UUID-backed suffix prevents collisions across concurrent workers.
    value = connection.execute(
        "SELECT replace(gen_random_uuid()::text, '-', '')"
    ).fetchone()[0]
    return f"bank-{prefix}-{value}"


def tool_result(
    *,
    status: str,
    summary: str,
    data: dict[str, Any],
    receipt_id: str | None = None,
    operation_id: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
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
