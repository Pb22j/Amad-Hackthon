"""Trusted session state and cryptographic contract for the interaction layer."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentEvent(StrictModel):
    task_id: str
    request_id: str
    session_id: str
    event_type: str
    user_safe_summary: str = Field(max_length=1000)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InteractionSession:
    session_id: str
    user_id: str
    tenant_id: str
    language: str
    scopes: tuple[str, ...]
    authenticated_at: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class TaskBinding:
    task_id: str
    request_id: str
    session_id: str
    status: str
    pending_event: dict[str, Any] | None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def sign_message(secret: str, body: bytes, *, timestamp: int | None = None) -> tuple[str, str]:
    value = str(timestamp if timestamp is not None else int(time.time()))
    signature = hmac.new(
        secret.encode("utf-8"), value.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()
    return value, signature


def verify_message(
    secret: str,
    body: bytes,
    *,
    timestamp: str,
    signature: str,
    max_age_seconds: int = 300,
    now: int | None = None,
) -> None:
    if not timestamp or not signature:
        raise PermissionError("signed message required")
    try:
        issued_at = int(timestamp)
    except ValueError as exc:
        raise PermissionError("invalid signature timestamp") from exc
    current = int(time.time()) if now is None else now
    if abs(current - issued_at) > max_age_seconds:
        raise PermissionError("signature timestamp is stale")
    expected_timestamp, expected = sign_message(secret, body, timestamp=issued_at)
    if expected_timestamp != timestamp or not hmac.compare_digest(expected, signature):
        raise PermissionError("invalid signature")


def issue_confirmation_token(
    secret: str,
    *,
    session: InteractionSession,
    task_id: str,
    tool_name: str,
    arguments_hash: str,
    ttl_seconds: int = 300,
) -> str:
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("confirmation signing key must contain at least 32 bytes")
    if len(arguments_hash) != 64 or any(ch not in "0123456789abcdef" for ch in arguments_hash):
        raise ValueError("invalid confirmation arguments hash")
    now = datetime.now(timezone.utc)
    claims = {
        "task_id": task_id,
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "tool_name": tool_name,
        "arguments_hash": arguments_hash,
        "nonce": secrets.token_urlsafe(24),
        "issuer": "interaction-layer",
        "confirmation_method": "explicit_voice",
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=min(ttl_seconds, 300))).isoformat().replace(
            "+00:00", "Z"
        ),
    }
    encoded = _encode(
        json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    signature = _encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


class InteractionStore:
    """Small durable store for session identity, task correlation, and webhook dedupe."""

    def __init__(
        self,
        path: str,
        *,
        encryption_key: str = "test-interaction-memory-key-32bytes",
        max_user_turns: int = 12,
        max_assistant_turns: int = 6,
        max_memory_text_characters: int = 2000,
    ) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._cipher = AESGCM(hashlib.sha256(encryption_key.encode("utf-8")).digest())
        self.max_user_turns = max_user_turns
        self.max_assistant_turns = max_assistant_turns
        self.max_memory_text_characters = max_memory_text_characters
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False) if path == ":memory:" else None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = self._memory_connection or sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _close(self, connection: sqlite3.Connection) -> None:
        if connection is not self._memory_connection:
            connection.close()

    def _initialize(self) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS interaction_sessions (
                        session_id TEXT PRIMARY KEY,
                        token_hash TEXT NOT NULL UNIQUE,
                        user_id TEXT NOT NULL,
                        tenant_id TEXT NOT NULL,
                        language TEXT NOT NULL,
                        scopes_json TEXT NOT NULL,
                        authenticated_at TEXT NOT NULL,
                        expires_at REAL NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS interaction_tasks (
                        task_id TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL UNIQUE,
                        session_id TEXT NOT NULL REFERENCES interaction_sessions(session_id),
                        status TEXT NOT NULL,
                        pending_event_json TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_interaction_tasks_session
                        ON interaction_tasks(session_id, updated_at);
                    CREATE TABLE IF NOT EXISTS interaction_events (
                        event_hash TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL REFERENCES interaction_tasks(task_id),
                        session_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_interaction_events_session
                        ON interaction_events(session_id, created_at);
                    CREATE TABLE IF NOT EXISTS voice_turns (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES interaction_sessions(session_id),
                        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                        encrypted_text BLOB NOT NULL,
                        provenance TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_voice_turns_session
                        ON voice_turns(session_id, role, created_at);
                    """
                )
                connection.commit()
            finally:
                self._close(connection)

    def create_session(
        self,
        *,
        user_id: str,
        tenant_id: str,
        language: str,
        scopes: tuple[str, ...],
        ttl_seconds: int,
    ) -> tuple[InteractionSession, str]:
        now = datetime.now(timezone.utc)
        session_id = str(uuid4())
        token = secrets.token_urlsafe(32)
        record = InteractionSession(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            language=language,
            scopes=tuple(sorted(set(scopes))),
            authenticated_at=now.isoformat().replace("+00:00", "Z"),
            expires_at=time.time() + ttl_seconds,
        )
        with self._lock:
            connection = self._connect()
            try:
                expired_sessions = connection.execute(
                    "SELECT session_id FROM interaction_sessions WHERE expires_at <= ?",
                    (time.time(),),
                ).fetchall()
                for expired in expired_sessions:
                    expired_id = expired["session_id"]
                    connection.execute(
                        "DELETE FROM voice_turns WHERE session_id = ?", (expired_id,)
                    )
                    connection.execute(
                        "DELETE FROM interaction_events WHERE session_id = ?", (expired_id,)
                    )
                    connection.execute(
                        "DELETE FROM interaction_tasks WHERE session_id = ?", (expired_id,)
                    )
                    connection.execute(
                        "DELETE FROM interaction_sessions WHERE session_id = ?", (expired_id,)
                    )
                connection.execute(
                    """
                    INSERT INTO interaction_sessions
                    (session_id, token_hash, user_id, tenant_id, language, scopes_json,
                     authenticated_at, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.session_id,
                        _token_hash(token),
                        record.user_id,
                        record.tenant_id,
                        record.language,
                        json.dumps(record.scopes),
                        record.authenticated_at,
                        record.expires_at,
                        time.time(),
                    ),
                )
                connection.commit()
            finally:
                self._close(connection)
        return record, token

    def get_session(self, token: str | None) -> InteractionSession | None:
        if not token:
            return None
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT * FROM interaction_sessions WHERE token_hash = ? AND expires_at > ?",
                    (_token_hash(token), time.time()),
                ).fetchone()
            finally:
                self._close(connection)
        if row is None:
            return None
        return InteractionSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            language=row["language"],
            scopes=tuple(json.loads(row["scopes_json"])),
            authenticated_at=row["authenticated_at"],
            expires_at=row["expires_at"],
        )

    def record_task(self, *, session_id: str, request_id: str, task_id: str) -> None:
        now = time.time()
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    INSERT INTO interaction_tasks
                    (task_id, request_id, session_id, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'accepted', ?, ?)
                    """,
                    (task_id, request_id, session_id, now, now),
                )
                connection.commit()
            finally:
                self._close(connection)

    def get_task(self, *, task_id: str, session_id: str) -> TaskBinding | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT * FROM interaction_tasks WHERE task_id = ? AND session_id = ?",
                    (task_id, session_id),
                ).fetchone()
            finally:
                self._close(connection)
        if row is None:
            return None
        return TaskBinding(
            task_id=row["task_id"],
            request_id=row["request_id"],
            session_id=row["session_id"],
            status=row["status"],
            pending_event=(json.loads(row["pending_event_json"]) if row["pending_event_json"] else None),
        )

    def get_task_by_request(self, *, request_id: str, session_id: str) -> TaskBinding | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT task_id FROM interaction_tasks WHERE request_id = ? AND session_id = ?",
                    (request_id, session_id),
                ).fetchone()
            finally:
                self._close(connection)
        if row is None:
            return None
        return self.get_task(task_id=row["task_id"], session_id=session_id)

    def get_active_task(self, *, session_id: str) -> TaskBinding | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    """
                    SELECT task_id FROM interaction_tasks
                    WHERE session_id = ?
                      AND status NOT IN ('completed', 'partially_completed', 'rejected', 'failed')
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
            finally:
                self._close(connection)
        if row is None:
            return None
        return self.get_task(task_id=row["task_id"], session_id=session_id)

    def record_event(self, event: AgentEvent) -> bool:
        payload = event.model_dump_json()
        event_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        pending = (
            event.model_dump(mode="json")
            if event.event_type in {"input_needed", "confirmation_needed"}
            else None
        )
        with self._lock:
            connection = self._connect()
            try:
                task = connection.execute(
                    "SELECT request_id, session_id FROM interaction_tasks WHERE task_id = ?",
                    (event.task_id,),
                ).fetchone()
                if task is None:
                    raise LookupError("unknown task")
                if task["request_id"] != event.request_id or task["session_id"] != event.session_id:
                    raise PermissionError("event identity does not match submitted task")
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO interaction_events
                    (event_hash, task_id, session_id, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_hash,
                        event.task_id,
                        event.session_id,
                        event.event_type,
                        payload,
                        event.created_at.timestamp(),
                    ),
                ).rowcount
                if inserted:
                    connection.execute(
                        """
                        UPDATE interaction_tasks
                        SET status = ?, pending_event_json = ?, updated_at = ?
                        WHERE task_id = ?
                        """,
                        (
                            event.event_type,
                            json.dumps(pending, separators=(",", ":")) if pending else None,
                            time.time(),
                            event.task_id,
                        ),
                    )
                    connection.execute(
                        """
                        DELETE FROM interaction_events
                        WHERE session_id = ? AND event_hash NOT IN (
                            SELECT event_hash FROM interaction_events
                            WHERE session_id = ? ORDER BY created_at DESC LIMIT 200
                        )
                        """,
                        (event.session_id, event.session_id),
                    )
                connection.commit()
                return bool(inserted)
            finally:
                self._close(connection)

    def clear_pending(self, *, task_id: str, session_id: str) -> None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    UPDATE interaction_tasks SET pending_event_json = NULL, updated_at = ?
                    WHERE task_id = ? AND session_id = ?
                    """,
                    (time.time(), task_id, session_id),
                )
                connection.commit()
            finally:
                self._close(connection)

    def recent_events(self, *, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    """
                    SELECT payload_json FROM interaction_events
                    WHERE session_id = ? ORDER BY created_at DESC LIMIT ?
                    """,
                    (session_id, min(limit, 100)),
                ).fetchall()
            finally:
                self._close(connection)
        return [json.loads(row["payload_json"]) for row in reversed(rows)]

    @staticmethod
    def _memory_text_is_safe(text: str) -> bool:
        forbidden = re.compile(
            r"\b(password|passcode|pin|otp|cvv|secret|api[_ -]?key|access[_ -]?token|"
            r"ignore (?:all |the )?(?:previous|prior)|system prompt|developer message|"
            r"you are now|act as)\b",
            re.IGNORECASE,
        )
        return (
            not forbidden.search(text)
            and not re.search(r"\d{8,}", text)
            and not re.search(r"\b1111\b", text)
        )

    def _encrypt_turn(self, *, session_id: str, role: str, text: str) -> bytes:
        nonce = os.urandom(12)
        aad = f"{session_id}:{role}".encode("utf-8")
        return nonce + self._cipher.encrypt(nonce, text.encode("utf-8"), aad)

    def _decrypt_turn(self, *, session_id: str, role: str, payload: bytes) -> str | None:
        try:
            nonce, ciphertext = payload[:12], payload[12:]
            aad = f"{session_id}:{role}".encode("utf-8")
            return self._cipher.decrypt(nonce, ciphertext, aad).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, ValueError):
            return None

    def record_voice_turn(
        self,
        *,
        session_id: str,
        role: str,
        text: str,
        provenance: str,
    ) -> bool:
        """Persist a bounded encrypted transcript without promoting it to fact."""

        if role not in {"user", "assistant"}:
            raise ValueError("unsupported voice turn role")
        normalized = " ".join(text.split()).strip()
        if (
            not normalized
            or len(normalized) > self.max_memory_text_characters
            or not self._memory_text_is_safe(normalized)
        ):
            return False
        encrypted = self._encrypt_turn(session_id=session_id, role=role, text=normalized)
        keep = self.max_user_turns if role == "user" else self.max_assistant_turns
        with self._lock:
            connection = self._connect()
            try:
                exists = connection.execute(
                    "SELECT 1 FROM interaction_sessions WHERE session_id = ? AND expires_at > ?",
                    (session_id, time.time()),
                ).fetchone()
                if exists is None:
                    raise LookupError("unknown or expired interaction session")
                connection.execute(
                    """
                    INSERT INTO voice_turns
                    (id, session_id, role, encrypted_text, provenance, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid4()), session_id, role, encrypted, provenance, time.time()),
                )
                connection.execute(
                    """
                    DELETE FROM voice_turns
                    WHERE session_id = ? AND role = ? AND id NOT IN (
                        SELECT id FROM voice_turns
                        WHERE session_id = ? AND role = ?
                        ORDER BY created_at DESC LIMIT ?
                    )
                    """,
                    (session_id, role, session_id, role, keep),
                )
                connection.commit()
            finally:
                self._close(connection)
        return True

    def grounded_voice_context(self, *, session_id: str, limit: int = 8) -> dict[str, Any]:
        """Return evidence labels; assistant text is intentionally never recalled as truth."""

        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    """
                    SELECT role, encrypted_text FROM voice_turns
                    WHERE session_id = ? AND role = 'user'
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (session_id, min(limit, self.max_user_turns)),
                ).fetchall()
            finally:
                self._close(connection)
        statements = []
        for row in reversed(rows):
            text = self._decrypt_turn(
                session_id=session_id, role=row["role"], payload=row["encrypted_text"]
            )
            if text is not None:
                statements.append(text)
        verified_events = [
            {
                "event_type": event.get("event_type"),
                "summary": event.get("user_safe_summary"),
            }
            for event in self.recent_events(session_id=session_id, limit=5)
            if event.get("event_type") in {"completed", "rejected", "failed"}
        ]
        return {
            "explicit_user_statements_untrusted": statements,
            "signed_agentic_outcomes": verified_events,
        }
