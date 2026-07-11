"""Thread-safe SQLite persistence for tasks and mock application state."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping
from uuid import uuid4

from .domain import ActionPlan, ActionType, AuditEvent, Money, StepState, TaskRecord, TaskState, utc_now_iso
from .security import payload_hash, redact


class StorageError(RuntimeError):
    """Base persistence failure."""


class IdempotencyConflict(StorageError):
    """The same request id was submitted with a different payload."""


class ConcurrentTaskUpdate(StorageError):
    """An optimistic task update lost a version race."""


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _load(value: str | None, default: Any) -> Any:
    return json.loads(value) if value else default


@dataclass(frozen=True, slots=True)
class IdempotencyResult:
    task: TaskRecord
    created: bool


class SQLiteRepository:
    """A small transactional repository suitable for development and tests.

    A single ``check_same_thread=False`` connection plus an ``RLock`` supports
    the in-process task runner safely.  Each public mutation is atomic and the
    schema records enough state to reconcile an interrupted mock workflow.
    """

    def __init__(self, database_path: str = ":memory:") -> None:
        self._connection = sqlite3.connect(database_path, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = self._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                session_id TEXT NOT NULL, user_id TEXT NOT NULL, language TEXT NOT NULL,
                natural_language_request TEXT NOT NULL,
                application_approval_received INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL,
                action_type TEXT, plan_json TEXT, safe_result_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_user_created ON tasks(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS request_idempotency (
                request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, task_id TEXT NOT NULL,
                acknowledgement_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS task_steps (
                task_id TEXT NOT NULL, step_index INTEGER NOT NULL, command_type TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, state TEXT NOT NULL, provider_reference TEXT NOT NULL DEFAULT '',
                details_json TEXT NOT NULL DEFAULT '{}', retry_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL, PRIMARY KEY(task_id, step_index),
                UNIQUE(task_id, idempotency_key), FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, actor_id TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL, result TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}',
                provider_reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id, id);
            CREATE TABLE IF NOT EXISTS outbox_events (
                event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, dedupe_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL, destination TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT, created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS beneficiaries (
                beneficiary_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, iban TEXT NOT NULL,
                display_name TEXT NOT NULL, verification_state TEXT NOT NULL DEFAULT 'local',
                provider_reference TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, deleted_at TEXT, UNIQUE(user_id, iban)
            );
            CREATE TABLE IF NOT EXISTS qattas (
                qatta_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, total_minor INTEGER NOT NULL,
                currency TEXT NOT NULL, purpose TEXT NOT NULL, split_mode TEXT NOT NULL,
                due_date TEXT, state TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS qatta_shares (
                share_id TEXT PRIMARY KEY, qatta_id TEXT NOT NULL, participant_id TEXT NOT NULL,
                amount_minor INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'unpaid', payment_reference TEXT NOT NULL DEFAULT '',
                UNIQUE(qatta_id, participant_id), FOREIGN KEY(qatta_id) REFERENCES qattas(qatta_id)
            );
            CREATE TABLE IF NOT EXISTS gifts (
                gift_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, sender_id TEXT NOT NULL, recipient_id TEXT NOT NULL,
                payment_reference TEXT NOT NULL, message TEXT NOT NULL DEFAULT '', occasion TEXT NOT NULL DEFAULT '',
                theme TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, FOREIGN KEY(task_id) REFERENCES tasks(task_id)
            );
            CREATE TABLE IF NOT EXISTS store_items (
                sku TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                price_minor INTEGER NOT NULL, currency TEXT NOT NULL, stock INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, ui_metadata_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS inventory_reservations (
                reservation_id TEXT PRIMARY KEY, sku TEXT NOT NULL, order_id TEXT NOT NULL UNIQUE,
                quantity INTEGER NOT NULL, state TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(sku) REFERENCES store_items(sku)
            );
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL,
                total_minor INTEGER NOT NULL, currency TEXT NOT NULL, state TEXT NOT NULL,
                payment_reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                FOREIGN KEY(sku) REFERENCES store_items(sku)
            );
            """
        )
        # Small forward-only migration for databases created by the first MVP.
        task_columns = {
            str(row[1]) for row in self._connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "application_approval_received" not in task_columns:
            self._connection.execute(
                "ALTER TABLE tasks ADD COLUMN application_approval_received INTEGER NOT NULL DEFAULT 0"
            )
        beneficiary_columns = {
            str(row[1]) for row in self._connection.execute("PRAGMA table_info(beneficiaries)").fetchall()
        }
        if "provider_reference" not in beneficiary_columns:
            self._connection.execute(
                "ALTER TABLE beneficiaries ADD COLUMN provider_reference TEXT NOT NULL DEFAULT ''"
            )

    def create_or_get_task(self, task: TaskRecord, request_payload: Mapping[str, Any]) -> IdempotencyResult:
        """Atomically persist a request or return the original task for a retry."""
        digest = payload_hash(request_payload)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT payload_hash, task_id FROM request_idempotency WHERE request_id = ?", (task.request_id,)
            ).fetchone()
            if existing:
                if existing["payload_hash"] != digest:
                    raise IdempotencyConflict("request_id was already used with a different payload")
                return IdempotencyResult(self._read_task(connection, existing["task_id"]), False)
            connection.execute(
                """INSERT INTO tasks(task_id, request_id, session_id, user_id, language, natural_language_request,
                   application_approval_received, state, action_type, plan_json, safe_result_json,
                   created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._task_values(task),
            )
            connection.execute(
                "INSERT INTO request_idempotency(request_id, payload_hash, task_id, created_at) VALUES (?, ?, ?, ?)",
                (task.request_id, digest, task.task_id, utc_now_iso()),
            )
        return IdempotencyResult(task, True)

    # A concise alias makes request-service code read naturally.
    get_or_create_task = create_or_get_task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return self._row_to_task(row) if row else None

    def get_task_for_user(self, task_id: str, user_id: str) -> TaskRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id = ? AND user_id = ?", (task_id, user_id)
            ).fetchone()
            return self._row_to_task(row) if row else None

    def update_task(self, task: TaskRecord, *, expected_version: int | None = None) -> TaskRecord:
        expected = task.version if expected_version is None else expected_version
        now = utc_now_iso()
        candidate = TaskRecord(
            **{**task.to_dict(), "state": task.state, "action_type": task.action_type,
               "plan": task.plan, "safe_result": task.safe_result, "updated_at": now, "version": expected + 1}
        )
        with self._transaction() as connection:
            cursor = connection.execute(
                """UPDATE tasks SET state=?, action_type=?, plan_json=?, safe_result_json=?, updated_at=?, version=?
                   WHERE task_id=? AND version=?""",
                (candidate.state.value, candidate.action_type.value if candidate.action_type else None,
                 _dump(candidate.plan.to_dict()) if candidate.plan else None, _dump(candidate.safe_result),
                 candidate.updated_at, candidate.version, candidate.task_id, expected),
            )
            if cursor.rowcount != 1:
                raise ConcurrentTaskUpdate(f"task {task.task_id} has changed")
        return candidate

    def transition_task(
        self, task_id: str, state: TaskState, *, plan: ActionPlan | None = None,
        safe_result: Mapping[str, Any] | None = None, expected_version: int | None = None,
    ) -> TaskRecord:
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"unknown task: {task_id}")
        if task.state.terminal and task.state != state:
            raise StorageError(f"cannot transition terminal task {task_id}")
        return self.update_task(
            TaskRecord(
                task_id=task.task_id, request_id=task.request_id, session_id=task.session_id, user_id=task.user_id,
                language=task.language, natural_language_request=task.natural_language_request, state=state,
                application_approval_received=task.application_approval_received,
                action_type=(plan.action_type if plan else task.action_type), plan=(plan if plan else task.plan),
                safe_result=(safe_result if safe_result is not None else task.safe_result), created_at=task.created_at,
                updated_at=task.updated_at, version=task.version,
            ), expected_version=expected_version,
        )

    def record_step(self, task_id: str, step_index: int, command_type: str, idempotency_key: str,
                    state: StepState, *, provider_reference: str = "", details: Mapping[str, Any] | None = None) -> None:
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO task_steps(task_id, step_index, command_type, idempotency_key, state, provider_reference, details_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_id, step_index) DO UPDATE SET state=excluded.state, provider_reference=excluded.provider_reference,
                   details_json=excluded.details_json, updated_at=excluded.updated_at""",
                (task_id, step_index, command_type, idempotency_key, state.value, provider_reference,
                 _dump(redact(details or {})), utc_now_iso()),
            )

    def record_audit(self, event: AuditEvent) -> None:
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO audit_events(task_id, actor_id, action, result, details_json, provider_reference, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event.task_id, event.actor_id, event.action, event.result, _dump(redact(event.details)),
                 event.provider_reference, event.created_at),
            )

    def list_audit(self, task_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM audit_events WHERE task_id=? ORDER BY id", (task_id,)).fetchall()
        return [{**dict(row), "details": _load(row["details_json"], {})} for row in rows]

    def enqueue_event(self, task_id: str, payload: Mapping[str, Any], destination: str, dedupe_key: str) -> bool:
        with self._transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO outbox_events(event_id, task_id, dedupe_key, payload_json, destination, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid4()), task_id, dedupe_key, _dump(redact(payload)), destination, utc_now_iso()),
            )
            return cursor.rowcount == 1

    # Beneficiaries -------------------------------------------------------
    def add_beneficiary(
        self, user_id: str, iban: str, display_name: str, *,
        verification_state: str = "local", provider_reference: str = "",
    ) -> tuple[dict[str, Any], bool]:
        with self._transaction() as connection:
            existing = connection.execute("SELECT * FROM beneficiaries WHERE user_id=? AND iban=?", (user_id, iban)).fetchone()
            if existing:
                if provider_reference and not existing["provider_reference"]:
                    connection.execute(
                        "UPDATE beneficiaries SET verification_state=?,provider_reference=? WHERE beneficiary_id=?",
                        (verification_state, provider_reference, existing["beneficiary_id"]),
                    )
                    existing = connection.execute(
                        "SELECT * FROM beneficiaries WHERE beneficiary_id=?", (existing["beneficiary_id"],)
                    ).fetchone()
                return dict(existing), False
            record = {"beneficiary_id": str(uuid4()), "user_id": user_id, "iban": iban, "display_name": display_name,
                      "verification_state": verification_state, "provider_reference": provider_reference,
                      "created_at": utc_now_iso()}
            connection.execute("INSERT INTO beneficiaries(beneficiary_id,user_id,iban,display_name,verification_state,provider_reference,created_at) VALUES (:beneficiary_id,:user_id,:iban,:display_name,:verification_state,:provider_reference,:created_at)", record)
            return record, True

    def get_beneficiary(
        self, user_id: str, *, beneficiary_id: str | None = None, iban: str | None = None,
    ) -> dict[str, Any] | None:
        if bool(beneficiary_id) == bool(iban):
            raise ValueError("provide exactly one of beneficiary_id or iban")
        field, value = ("beneficiary_id", beneficiary_id) if beneficiary_id else ("iban", iban)
        with self._lock:
            row = self._connection.execute(
                f"SELECT * FROM beneficiaries WHERE user_id=? AND {field}=? AND deleted_at IS NULL",
                (user_id, value),
            ).fetchone()
            return dict(row) if row else None

    def delete_beneficiary(self, user_id: str, *, beneficiary_id: str | None = None, iban: str | None = None) -> bool:
        if bool(beneficiary_id) == bool(iban):
            raise ValueError("provide exactly one of beneficiary_id or iban")
        field, value = ("beneficiary_id", beneficiary_id) if beneficiary_id else ("iban", iban)
        with self._transaction() as connection:
            cursor = connection.execute(f"UPDATE beneficiaries SET deleted_at=? WHERE user_id=? AND {field}=? AND deleted_at IS NULL", (utc_now_iso(), user_id, value))
            return cursor.rowcount == 1

    def list_beneficiaries(self, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM beneficiaries WHERE user_id=? AND deleted_at IS NULL ORDER BY created_at", (user_id,)).fetchall()
            return [dict(row) for row in rows]

    # Qatta ---------------------------------------------------------------
    def create_qatta(self, owner_id: str, total: Money, purpose: str, shares: Mapping[str, int], *, split_mode: str = "equal", due_date: str | None = None) -> str:
        if total.minor_units <= 0 or not shares or any(amount <= 0 for amount in shares.values()):
            raise ValueError("Qatta must have positive total and shares")
        if sum(shares.values()) != total.minor_units:
            raise ValueError("Qatta shares must equal the total exactly")
        qatta_id = str(uuid4())
        with self._transaction() as connection:
            connection.execute("INSERT INTO qattas(qatta_id,owner_id,total_minor,currency,purpose,split_mode,due_date,created_at) VALUES (?,?,?,?,?,?,?,?)", (qatta_id, owner_id, total.minor_units, total.currency, purpose, split_mode, due_date, utc_now_iso()))
            connection.executemany("INSERT INTO qatta_shares(share_id,qatta_id,participant_id,amount_minor) VALUES (?,?,?,?)", [(str(uuid4()), qatta_id, participant, amount) for participant, amount in shares.items()])
        return qatta_id

    def get_qatta(self, qatta_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM qattas WHERE qatta_id=?", (qatta_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            shares = self._connection.execute("SELECT * FROM qatta_shares WHERE qatta_id=? ORDER BY participant_id", (qatta_id,)).fetchall()
            result["shares"] = [dict(share) for share in shares]
            return result

    def settle_qatta_share(self, qatta_id: str, participant_id: str, payment_reference: str) -> bool:
        with self._transaction() as connection:
            cursor = connection.execute("UPDATE qatta_shares SET state='paid', payment_reference=? WHERE qatta_id=? AND participant_id=? AND state='unpaid'", (payment_reference, qatta_id, participant_id))
            if cursor.rowcount == 0:
                return False
            unpaid = connection.execute("SELECT COUNT(*) FROM qatta_shares WHERE qatta_id=? AND state!='paid'", (qatta_id,)).fetchone()[0]
            if unpaid == 0:
                connection.execute("UPDATE qattas SET state='completed' WHERE qatta_id=?", (qatta_id,))
            return True

    # Store ---------------------------------------------------------------
    def upsert_store_item(self, sku: str, name: str, price: Money, stock: int, *, description: str = "", active: bool = True, ui_metadata: Mapping[str, Any] | None = None) -> None:
        if stock < 0 or price.minor_units < 0:
            raise ValueError("stock and price must be non-negative")
        with self._transaction() as connection:
            connection.execute("""INSERT INTO store_items(sku,name,description,price_minor,currency,stock,active,ui_metadata_json,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(sku) DO UPDATE SET name=excluded.name,description=excluded.description,
                price_minor=excluded.price_minor,currency=excluded.currency,stock=excluded.stock,active=excluded.active,
                ui_metadata_json=excluded.ui_metadata_json,updated_at=excluded.updated_at""", (sku, name, description, price.minor_units, price.currency, stock, int(active), _dump(ui_metadata or {}), utc_now_iso()))

    def list_store_items(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM store_items WHERE active=1 AND stock>0 ORDER BY sku").fetchall()
            return [self._store_item(row) for row in rows]

    def reserve_inventory(self, order_id: str, sku: str, quantity: int, expires_at: str) -> bool:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        with self._transaction() as connection:
            # Conditional decrement makes the final unit safe under concurrency.
            cursor = connection.execute("UPDATE store_items SET stock=stock-? WHERE sku=? AND active=1 AND stock>=?", (quantity, sku, quantity))
            if cursor.rowcount != 1:
                return False
            connection.execute("INSERT INTO inventory_reservations(reservation_id,sku,order_id,quantity,state,expires_at,created_at) VALUES (?,?,?,?,?,?,?)", (str(uuid4()), sku, order_id, quantity, "reserved", expires_at, utc_now_iso()))
            return True

    def create_order(self, order_id: str, user_id: str, sku: str, quantity: int) -> dict[str, Any]:
        with self._transaction() as connection:
            item = connection.execute("SELECT * FROM store_items WHERE sku=? AND active=1", (sku,)).fetchone()
            if not item:
                raise KeyError("unknown active store item")
            now = utc_now_iso()
            record = {"order_id": order_id, "user_id": user_id, "sku": sku, "quantity": quantity,
                      "total_minor": item["price_minor"] * quantity, "currency": item["currency"], "state": "pending_payment",
                      "payment_reference": "", "created_at": now, "updated_at": now}
            connection.execute("INSERT INTO orders(order_id,user_id,sku,quantity,total_minor,currency,state,payment_reference,created_at,updated_at) VALUES (:order_id,:user_id,:sku,:quantity,:total_minor,:currency,:state,:payment_reference,:created_at,:updated_at)", record)
            return record

    def finalize_order(self, order_id: str, payment_reference: str, *, paid: bool) -> bool:
        state = "paid" if paid else "failed"
        reservation_state = "consumed" if paid else "released"
        with self._transaction() as connection:
            order = connection.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if not order or order["state"] != "pending_payment":
                return False
            connection.execute("UPDATE orders SET state=?,payment_reference=?,updated_at=? WHERE order_id=?", (state, payment_reference, utc_now_iso(), order_id))
            reservation = connection.execute("SELECT * FROM inventory_reservations WHERE order_id=? AND state='reserved'", (order_id,)).fetchone()
            if reservation:
                connection.execute("UPDATE inventory_reservations SET state=? WHERE reservation_id=?", (reservation_state, reservation["reservation_id"]))
                if not paid:
                    connection.execute("UPDATE store_items SET stock=stock+? WHERE sku=?", (reservation["quantity"], reservation["sku"]))
            return True

    # Gifts ---------------------------------------------------------------
    def create_gift(self, task_id: str, sender_id: str, recipient_id: str, payment_reference: str, *, message: str = "", occasion: str = "", theme: str = "") -> str:
        gift_id = str(uuid4())
        with self._transaction() as connection:
            connection.execute("INSERT INTO gifts(gift_id,task_id,sender_id,recipient_id,payment_reference,message,occasion,theme,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (gift_id, task_id, sender_id, recipient_id, payment_reference, message, occasion, theme, utc_now_iso()))
        return gift_id

    def _task_values(self, task: TaskRecord) -> tuple[Any, ...]:
        return (task.task_id, task.request_id, task.session_id, task.user_id, task.language, task.natural_language_request,
                int(task.application_approval_received), task.state.value, task.action_type.value if task.action_type else None,
                _dump(task.plan.to_dict()) if task.plan else None, _dump(task.safe_result), task.created_at, task.updated_at, task.version)

    def _read_task(self, connection: sqlite3.Connection, task_id: str) -> TaskRecord:
        row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(f"unknown task: {task_id}")
        return self._row_to_task(row)

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> TaskRecord:
        plan_data = _load(row["plan_json"], None)
        return TaskRecord(task_id=row["task_id"], request_id=row["request_id"], session_id=row["session_id"], user_id=row["user_id"], language=row["language"], natural_language_request=row["natural_language_request"], application_approval_received=bool(row["application_approval_received"]), state=TaskState(row["state"]), action_type=ActionType(row["action_type"]) if row["action_type"] else None, plan=ActionPlan.from_dict(plan_data) if plan_data else None, safe_result=_load(row["safe_result_json"], {}), created_at=row["created_at"], updated_at=row["updated_at"], version=row["version"])

    @staticmethod
    def _store_item(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["price"] = Money.from_minor_units(item.pop("price_minor"), item["currency"]).to_dict()
        item["ui_metadata"] = _load(item.pop("ui_metadata_json"), {})
        item["active"] = bool(item["active"])
        return item
