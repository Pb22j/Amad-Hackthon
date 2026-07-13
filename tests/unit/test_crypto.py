import pytest

from agentic.security.crypto import decrypt_bytes, encrypt_bytes


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
