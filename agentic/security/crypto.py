from __future__ import annotations

import hashlib
import json
import os
import secrets
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


VERSION = b"\x01"
NONCE_SIZE = 12


def _key() -> bytes:
    value = os.getenv("APP_DATA_ENCRYPTION_KEY")
    if value is None or len(value.encode("utf-8")) < 32:
        raise RuntimeError("APP_DATA_ENCRYPTION_KEY must contain at least 32 bytes")
    return hashlib.sha256(value.encode("utf-8")).digest()


def encrypt_bytes(plaintext: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_SIZE)
    return VERSION + nonce + AESGCM(_key()).encrypt(nonce, plaintext, VERSION)


def decrypt_bytes(ciphertext: bytes) -> bytes:
    if not ciphertext.startswith(VERSION) or len(ciphertext) <= 1 + NONCE_SIZE:
        raise ValueError("unsupported or malformed encrypted value")
    nonce = ciphertext[1 : 1 + NONCE_SIZE]
    return AESGCM(_key()).decrypt(nonce, ciphertext[1 + NONCE_SIZE :], VERSION)


class EncryptedJSON(TypeDecorator[dict[str, Any]]):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:
        del dialect
        if value is None:
            return None
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
        return encrypt_bytes(serialized)

    def process_result_value(self, value: bytes | None, dialect: Any) -> Any:
        del dialect
        if value is None:
            return None
        return json.loads(decrypt_bytes(bytes(value)))


class EncryptedText(TypeDecorator[str]):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> bytes | None:
        del dialect
        return encrypt_bytes(value.encode("utf-8")) if value is not None else None

    def process_result_value(self, value: bytes | None, dialect: Any) -> str | None:
        del dialect
        return decrypt_bytes(bytes(value)).decode("utf-8") if value is not None else None

