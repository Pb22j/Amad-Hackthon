"""Server-side banking-user authentication with legacy hash migration."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: str
    tenant_id: str
    language: str
    verified: bool = False


class RegistrationConflict(Exception):
    """A public registration identifier is already assigned."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(field)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        if encoded.startswith("scrypt$"):
            _, n, r, p, salt_hex, expected_hex = encoded.split("$", 5)
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n),
                r=int(r),
                p=int(p),
            )
            return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
        if len(encoded) == 64:
            actual_hex = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(actual_hex, encoded.lower())
    except (TypeError, ValueError, OverflowError):
        return False
    return False


class AuthenticationStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

    def authenticate(self, *, identifier: str, password: str) -> AuthenticatedUser | None:
        normalized = identifier.strip()
        if not normalized or not password:
            return None
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            row = connection.execute(
                """
                SELECT username::text AS username, tenant_id, preferred_language,
                       hashedpassword, status, kyc_status
                FROM users
                WHERE username = %s OR email = %s
                LIMIT 1
                """,
                (normalized, normalized),
            ).fetchone()
            if row is None or row["status"] != "active":
                return None
            if not verify_password(password, row["hashedpassword"]):
                return None
            if not row["hashedpassword"].startswith("scrypt$"):
                connection.execute(
                    """
                    UPDATE users SET hashedpassword = %s, last_login_at = %s
                    WHERE username = %s
                    """,
                    (hash_password(password), datetime.now(timezone.utc), row["username"]),
                )
            else:
                connection.execute(
                    "UPDATE users SET last_login_at = %s WHERE username = %s",
                    (datetime.now(timezone.utc), row["username"]),
                )
            connection.commit()
        return AuthenticatedUser(
            user_id=row["username"],
            tenant_id=row["tenant_id"],
            language=row["preferred_language"] if row["preferred_language"] in {"ar", "en"} else "ar",
            verified=row["kyc_status"] == "verified",
        )

    def register(
        self,
        *,
        full_name: str,
        username: str,
        email: str,
        phone_e164: str,
        password: str,
        language: str,
        tenant_id: str,
    ) -> AuthenticatedUser:
        """Create an active zero-balance banking profile atomically."""

        normalized_username = username.strip()
        normalized_email = email.strip().lower()
        normalized_phone = phone_e164.strip()
        normalized_name = " ".join(full_name.split())
        now = datetime.now(timezone.utc)
        user_uuid = str(uuid4())
        account_number = f"SA99{uuid4().int % 10**20:020d}"

        try:
            with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
                duplicate = connection.execute(
                    """
                    SELECT
                      CASE
                        WHEN username = %s THEN 'username'
                        WHEN email = %s THEN 'email'
                        WHEN phone_e164 = %s THEN 'phone'
                      END AS field
                    FROM users
                    WHERE username = %s OR email = %s OR phone_e164 = %s
                    LIMIT 1
                    """,
                    (
                        normalized_username,
                        normalized_email,
                        normalized_phone,
                        normalized_username,
                        normalized_email,
                        normalized_phone,
                    ),
                ).fetchone()
                if duplicate is not None:
                    raise RegistrationConflict(duplicate["field"])

                connection.execute(
                    """
                    INSERT INTO users (
                      uuid, tenant_id, username, source_username, full_name_ar,
                      full_name_en, email, phone_e164, preferred_language,
                      bank_name_ar, account_number, account_type_ar, currency_code,
                      balance_sar, available_balance_sar, daily_spend_limit_sar,
                      hashedpassword, status, nafath_linked, kyc_status, kyc_tier,
                      risk_rating, createdat, updatedat
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      'محفظة نافع', %s, 'محفظة رقمية', 'SAR',
                      0, 0, 5000, %s, 'active', 'No', 'pending', 1,
                      'low', %s, %s
                    )
                    """,
                    (
                        user_uuid,
                        tenant_id,
                        normalized_username,
                        normalized_username,
                        normalized_name,
                        normalized_name,
                        normalized_email,
                        normalized_phone,
                        language,
                        account_number,
                        hash_password(password),
                        now,
                        now,
                    ),
                )
                connection.commit()
        except UniqueViolation as error:
            constraint = error.diag.constraint_name or ""
            if "username" in constraint:
                raise RegistrationConflict("username") from error
            if "email" in constraint:
                raise RegistrationConflict("email") from error
            if "phone" in constraint:
                raise RegistrationConflict("phone") from error
            raise

        return AuthenticatedUser(
            user_id=normalized_username,
            tenant_id=tenant_id,
            language=language,
            verified=False,
        )
