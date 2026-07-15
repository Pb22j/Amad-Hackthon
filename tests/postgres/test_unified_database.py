"""PostgreSQL-specific checks for the unified application data model."""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest


@pytest.fixture
def unified_postgres_url() -> str:
    value = os.getenv("TEST_POSTGRES_URL")
    if not value:
        pytest.skip("TEST_POSTGRES_URL is not configured")
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.mark.postgres
def test_unified_columns_use_native_postgresql_types(unified_postgres_url: str) -> None:
    with psycopg.connect(unified_postgres_url) as connection:
        rows = connection.execute(
            """SELECT table_name, column_name, data_type
               FROM information_schema.columns
               WHERE table_schema='public' AND (
                   (table_name='users' AND column_name IN ('uuid','balance_sar','dateofbirth')) OR
                   (table_name='transactions' AND column_name IN ('amount_sar','metadata','createdat')) OR
                   (table_name='interaction_events' AND column_name='payload_json') OR
                   (table_name='voice_turns' AND column_name='encrypted_text')
               )"""
        ).fetchall()
    types = {(table, column): data_type for table, column, data_type in rows}
    assert types[("users", "uuid")] == "uuid"
    assert types[("users", "balance_sar")] == "numeric"
    assert types[("users", "dateofbirth")] == "date"
    assert types[("transactions", "amount_sar")] == "numeric"
    assert types[("transactions", "metadata")] == "jsonb"
    assert types[("transactions", "createdat")] == "timestamp with time zone"
    assert types[("interaction_events", "payload_json")] == "jsonb"
    assert types[("voice_turns", "encrypted_text")] == "bytea"


@pytest.mark.postgres
def test_financial_checks_and_transaction_rollback(unified_postgres_url: str) -> None:
    connection = psycopg.connect(unified_postgres_url)
    try:
        user_id, original = connection.execute(
            "SELECT uuid, balance_sar FROM users WHERE username='evaluation-user'"
        ).fetchone()
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                connection.execute(
                    "UPDATE users SET balance_sar=-1 WHERE uuid=%s", (user_id,)
                )
        connection.rollback()
        assert connection.execute(
            "SELECT balance_sar FROM users WHERE uuid=%s", (user_id,)
        ).fetchone()[0] == original

        with connection.transaction(force_rollback=True):
            connection.execute(
                "UPDATE users SET balance_sar=balance_sar-10 WHERE uuid=%s", (user_id,)
            )
            assert connection.execute(
                "SELECT balance_sar FROM users WHERE uuid=%s", (user_id,)
            ).fetchone()[0] == original - Decimal("10.00")
        assert connection.execute(
            "SELECT balance_sar FROM users WHERE uuid=%s", (user_id,)
        ).fetchone()[0] == original
    finally:
        connection.close()


@pytest.mark.postgres
def test_foreign_keys_and_paired_ledger_reference(unified_postgres_url: str) -> None:
    connection = psycopg.connect(unified_postgres_url)
    try:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with connection.transaction():
                connection.execute(
                    """INSERT INTO transactions
                       (uuid,user_uuid,account_number,direction,transaction_type,amount_sar,
                        description,balance_after_sar,reference,createdat)
                       VALUES (%s,%s,'SA00','debit','test',1,'test',0,%s,now())""",
                    (str(uuid4()), str(uuid4()), f"test-{uuid4()}"),
                )
        connection.rollback()

        users = connection.execute(
            "SELECT uuid,account_number,balance_sar FROM users WHERE status='active' LIMIT 2"
        ).fetchall()
        reference = f"paired-test-{uuid4()}"
        with connection.transaction(force_rollback=True):
            for (user_id, account, balance), direction in zip(users, ("debit", "credit")):
                connection.execute(
                    """INSERT INTO transactions
                       (uuid,user_uuid,account_number,direction,transaction_type,amount_sar,
                        description,balance_after_sar,reference,createdat)
                       VALUES (%s,%s,%s,%s,'transfer_test',1,'paired ledger test',%s,%s,now())""",
                    (str(uuid4()), user_id, account, direction, balance, reference),
                )
            assert connection.execute(
                "SELECT count(*) FROM transactions WHERE reference=%s", (reference,)
            ).fetchone()[0] == 2
    finally:
        connection.close()
