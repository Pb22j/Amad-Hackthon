"""Authentication against the minimal ten-user Nafi demo database."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from uuid import uuid4

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: str
    tenant_id: str = "evaluation-tenant"
    language: str = "ar"
    verified: bool = True


class RegistrationConflict(Exception):
    pass


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify the salted scrypt hashes stored in ``users.password_hash``."""

    try:
        algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
    except (TypeError, ValueError, OverflowError):
        return False


class AuthenticationStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

    def authenticate(self, *, identifier: str, password: str) -> AuthenticatedUser | None:
        username = identifier.strip()
        if not username or not password:
            return None
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                "SELECT username::text AS username, password_hash FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return AuthenticatedUser(user_id=row["username"])

    def register(
        self,
        *,
        username: str,
        full_name_ar: str,
        full_name_en: str,
        password: str,
    ) -> AuthenticatedUser:
        """Create a user and their initial Nafi account using only minimal fields."""

        normalized_username = username.strip()
        user_uuid = str(uuid4())
        account_uuid = str(uuid4())
        # UUID-derived digits make collisions practically impossible; the unique
        # database constraints remain the final authority.
        digits = f"{uuid4().int % 10**20:020d}"
        nafi_iban = f"SA99{digits}"
        try:
            with psycopg.connect(self.database_url) as connection:
                connection.execute(
                    """INSERT INTO users
                       (uuid,username,full_name_ar,full_name_en,password_hash,nafi_iban)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (user_uuid, normalized_username, full_name_ar.strip(), full_name_en.strip(),
                     hash_password(password), nafi_iban),
                )
                connection.execute(
                    """INSERT INTO bank_accounts
                       (uuid,user_uuid,bank_name_ar,bank_name_en,account_number,
                        account_type,balance_sar,is_primary)
                       VALUES (%s,%s,'نافي','Nafi',%s,'Nafi Account',0,true)""",
                    (account_uuid, user_uuid, nafi_iban),
                )
        except UniqueViolation as error:
            if "username" in (error.diag.constraint_name or ""):
                raise RegistrationConflict(normalized_username) from error
            raise
        return AuthenticatedUser(user_id=normalized_username)
