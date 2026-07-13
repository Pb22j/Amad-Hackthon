from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from agentic.security.confirmation import ConfirmationSigner, arguments_hash
from agentic.security.identity import AuthContext
from agentic.security.redaction import redact, redact_text
from agentic.security.signing import InteractionSignatureVerifier


@pytest.fixture
def auth() -> AuthContext:
    return AuthContext("user-1", "tenant-1", "session-1", frozenset({"financial:write"}))


def test_confirmation_is_bound_to_exact_arguments(auth):
    signer = ConfirmationSigner("k" * 32)
    token = signer.issue(
        auth=auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments={"amount": "100.00", "currency": "SAR", "destination": "b1"},
    )
    claims = signer.verify(
        token,
        auth=auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments={"destination": "b1", "currency": "SAR", "amount": "100.00"},
    )
    assert claims.arguments_hash == arguments_hash(
        {"amount": "100.00", "currency": "SAR", "destination": "b1"}
    )


def test_confirmation_hash_is_stable_across_decimal_json_boundary(auth):
    signer = ConfirmationSigner("k" * 32)
    token = signer.issue(
        auth=auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments={"amount": "25.00", "destination": "Savings"},
    )

    claims = signer.verify(
        token,
        auth=auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments={"amount": Decimal("25.00"), "destination": "Savings"},
    )

    assert claims.arguments_hash == arguments_hash(
        {"amount": Decimal("25.00"), "destination": "Savings"}
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [("amount", "1000.00"), ("currency", "USD"), ("destination", "attacker")],
)
def test_confirmation_rejects_material_argument_changes(auth, field, value):
    signer = ConfirmationSigner("k" * 32)
    original = {"amount": "100.00", "currency": "SAR", "destination": "b1"}
    token = signer.issue(
        auth=auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments=original,
    )
    changed = original | {field: value}
    with pytest.raises(PermissionError, match="exact action"):
        signer.verify(
            token,
            auth=auth,
            task_id="task-1",
            tool_name="transfer_funds",
            arguments=changed,
        )


def test_confirmation_rejects_expired_token(auth):
    signer = ConfirmationSigner("k" * 32)
    token = signer.issue(
        auth=auth,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments={"amount": 1},
        ttl_seconds=1,
    )
    with pytest.raises(ValueError, match="expired"):
        signer.verify(
            token,
            auth=auth,
            task_id="task-1",
            tool_name="transfer_funds",
            arguments={"amount": 1},
            now=datetime.now(timezone.utc) + timedelta(seconds=2),
        )


def test_confirmation_rejects_tampering(auth):
    signer = ConfirmationSigner("k" * 32)
    token = signer.issue(
        auth=auth, task_id="task", tool_name="tool", arguments={"amount": 1}
    )
    with pytest.raises(ValueError, match="signature"):
        signer.verify(
            token[:-1] + ("A" if token[-1] != "A" else "B"),
            auth=auth,
            task_id="task",
            tool_name="tool",
            arguments={"amount": 1},
        )


def test_interaction_signature_validates_body_and_expiry():
    verifier = InteractionSignatureVerifier("s" * 32, max_age_seconds=300)
    timestamp, signature = verifier.sign(b'{"safe":true}')
    verifier.verify(b'{"safe":true}', timestamp, signature)
    with pytest.raises(PermissionError, match="invalid request signature"):
        verifier.verify(b'{"safe":false}', timestamp, signature)


def test_interaction_signature_rejects_bad_timestamp_and_expiry():
    verifier = InteractionSignatureVerifier("s" * 32, max_age_seconds=1)
    with pytest.raises(PermissionError, match="invalid request timestamp"):
        verifier.verify(b"x", "not-a-number", "bad")
    timestamp, signature = verifier.sign(b"x", timestamp=1)
    with pytest.raises(PermissionError, match="expired"):
        verifier.verify(b"x", timestamp, signature)


def test_signers_reject_short_keys():
    with pytest.raises(ValueError, match="at least 32"):
        ConfirmationSigner("short")
    with pytest.raises(ValueError, match="at least 32"):
        InteractionSignatureVerifier("short")


def test_confirmation_rejects_malformed_and_future_tokens(auth):
    signer = ConfirmationSigner("k" * 32)
    with pytest.raises(ValueError, match="malformed"):
        signer.verify(
            "not-a-token",
            auth=auth,
            task_id="task",
            tool_name="tool",
            arguments={},
        )
    token = signer.issue(
        auth=auth, task_id="task", tool_name="tool", arguments={}
    )
    with pytest.raises(ValueError, match="issue time"):
        signer.verify(
            token,
            auth=auth,
            task_id="task",
            tool_name="tool",
            arguments={},
            now=datetime.now(timezone.utc) - timedelta(minutes=2),
        )


def test_auth_context_enforces_scopes_and_identity(auth):
    auth.require_scopes(frozenset({"financial:write"}))
    with pytest.raises(PermissionError, match="missing required scopes"):
        auth.require_scopes(frozenset({"admin"}))
    assert auth.matches(user_id="user-1", tenant_id="tenant-1", session_id="session-1")
    assert not auth.matches(user_id="user-2", tenant_id="tenant-1")


def test_redaction_removes_secret_fields_cards_and_bearer_tokens():
    value = redact(
        {
            "password": "hidden",
            "nested": {"api_key": "sk-secret", "note": "card 4111 1111 1111 1111"},
            "auth": "Bearer abc.def.ghi",
        }
    )
    assert value["password"] == "[REDACTED]"
    assert value["nested"]["api_key"] == "[REDACTED]"
    assert "4111" not in value["nested"]["note"]
    assert "abc.def" not in value["auth"]
    assert "sk-abcdefghijklmnop" not in redact_text("sk-abcdefghijklmnop")
