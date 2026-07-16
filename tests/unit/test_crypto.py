import pytest
from decimal import Decimal
from uuid import UUID

from agentic.security.crypto import EncryptedJSON, decrypt_bytes, encrypt_bytes


def test_application_encryption_round_trip_and_random_nonce():
    plaintext = b"sensitive financial data"
    first = encrypt_bytes(plaintext)
    second = encrypt_bytes(plaintext)
    assert first != second
    assert plaintext not in first
    assert decrypt_bytes(first) == plaintext
    assert decrypt_bytes(second) == plaintext


def test_application_encryption_detects_tampering():
    encrypted = encrypt_bytes(b"sensitive")
    with pytest.raises(Exception):
        decrypt_bytes(encrypted[:-1] + bytes([encrypted[-1] ^ 1]))
    with pytest.raises(ValueError, match="malformed"):
        decrypt_bytes(b"plaintext")


def test_encrypted_json_canonicalizes_validated_boundary_types():
    encrypted_type = EncryptedJSON()
    ciphertext = encrypted_type.process_bind_param(
        {
            "amount": Decimal("25.00"),
            "request_id": UUID("00000000-0000-0000-0000-000000000001"),
        },
        None,
    )

    assert encrypted_type.process_result_value(ciphertext, None) == {
        "amount": "25.00",
        "request_id": "00000000-0000-0000-0000-000000000001",
    }
