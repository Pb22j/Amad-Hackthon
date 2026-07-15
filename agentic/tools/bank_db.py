"""PostgreSQL connection and shared queries for the financial tools.

The Alembic schema and ``scripts/seed_postgres.py`` own all DDL and demo data.
Tool identity always comes from authenticated request context, never model
arguments. Connections use Riyadh time and every tool callback is atomic.
"""

from __future__ import annotations

import asyncio
import os
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


def find_user_by_username(connection: BankConnection, username: str) -> BankRow | None:
    return connection.execute(
        "SELECT * FROM users WHERE Username = %s", (username,)
    ).fetchone()


def find_user_by_account_number(
    connection: BankConnection, account_number: str
) -> BankRow | None:
    return connection.execute(
        "SELECT * FROM users WHERE Account_Number = %s", (account_number,)
    ).fetchone()


def find_beneficiary(
    connection: BankConnection, owner_uuid: str, destination: str
) -> BankRow | None:
    normalized = normalize_account_number(destination)
    row = connection.execute(
        "SELECT * FROM beneficiaries WHERE owner_uuid = %s AND Account_Number = %s",
        (owner_uuid, normalized),
    ).fetchone()
    if row is not None:
        return row
    requested_name = normalize_beneficiary_name(destination)
    requested_key = beneficiary_name_key(destination)
    transliterated_matches: list[BankRow] = []
    for beneficiary in connection.execute(
        "SELECT * FROM beneficiaries WHERE owner_uuid = %s", (owner_uuid,)
    ).fetchall():
        raw_names = {
            str(beneficiary["Short_Name"]),
            str(beneficiary["Full_Name"]),
        }
        if requested_name in {normalize_beneficiary_name(name) for name in raw_names}:
            return beneficiary
        if len(requested_key) >= 2 and requested_key in {
            beneficiary_name_key(name) for name in raw_names
        }:
            transliterated_matches.append(beneficiary)
    return transliterated_matches[0] if len(transliterated_matches) == 1 else None


def spent_today(connection: BankConnection, user_uuid: str) -> Decimal:
    day_start = riyadh_now().strftime("%Y-%m-%d 00:00:00")
    total = connection.execute(
        "SELECT COALESCE(SUM(Amount_SAR), 0) FROM transactions"
        " WHERE user_uuid = %s AND direction = 'debit' AND createdAt >= %s",
        (user_uuid, day_start),
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
