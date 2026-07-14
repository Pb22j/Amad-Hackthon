from datetime import datetime, timezone

import pytest

from VoiceAssistant_Nafea.backend.app.interaction import (
    InteractionSession,
    issue_confirmation_token,
)
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext


def test_voice_confirmation_token_is_agentic_signer_compatible():
    key = "k" * 32
    session = InteractionSession(
        session_id="session-1",
        user_id="user-1",
        tenant_id="tenant-1",
        language="en",
        scopes=("financial:write",),
        authenticated_at=datetime.now(timezone.utc).isoformat(),
        expires_at=9999999999,
    )
    arguments = {"destination": "Savings", "amount": "10.00", "currency": "SAR"}
    from agentic.security.confirmation import arguments_hash

    token = issue_confirmation_token(
        key,
        session=session,
        task_id="task-1",
        tool_name="transfer_funds",
        arguments_hash=arguments_hash(arguments),
    )
    claims = ConfirmationSigner(key).verify(
        token,
        auth=AuthContext("user-1", "tenant-1", "session-1", frozenset()),
        task_id="task-1",
        tool_name="transfer_funds",
        arguments=arguments,
    )
    assert claims.confirmation_method == "explicit_voice"
    with pytest.raises(PermissionError, match="exact action"):
        ConfirmationSigner(key).verify(
            token,
            auth=AuthContext("user-1", "tenant-1", "session-1", frozenset()),
            task_id="task-1",
            tool_name="transfer_funds",
            arguments=arguments | {"amount": "11.00"},
        )
