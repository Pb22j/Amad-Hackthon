"""Build the single natural-language request payload for the agentic layer."""

from __future__ import annotations

import re
from uuid import uuid4

from user_interaction_layer.agentic_client.schemas import (
    AgenticRequest,
    Channel,
    Confirmation,
)
from user_interaction_layer.security.redaction import redact_sensitive_text
from user_interaction_layer.session.models import Session


def build_agentic_request(
    *,
    session: Session,
    user_message: str,
    source_provider: str,
    conversation_context_summary: str = "",
    confirmation_received: bool = False,
    agentic_message: str | None = None,
) -> AgenticRequest:
    cleaned_message = " ".join((agentic_message or user_message).strip().split())
    return AgenticRequest(
        request_id=str(uuid4()),
        session_id=session.session_id,
        user_id=session.user_id,
        channel=Channel.CHAT if session.channel == Channel.CHAT else Channel.VOICE,
        language=session.active_language,
        natural_language_request=cleaned_message,
        original_user_message=user_message,
        source_provider=source_provider,
        confirmation=Confirmation(
            required=requires_confirmation(user_message),
            received=confirmation_received,
        ),
        conversation_context_summary=redact_sensitive_text(conversation_context_summary),
    )


_PROTECTED_EN = re.compile(
    r"\b(transfer|send|pay|wire|buy|purchase|checkout|invest|gift|delete|remove|add (?:a )?beneficiary|beneficiary|open (?:a )?savings|create (?:a )?(?:savings|qatta)|qatta|split|move money|fund (?:a )?savings)\b",
    re.IGNORECASE,
)
_PROTECTED_AR = re.compile(r"(حوّل|حول|تحويل|أرسل|ارسل|إرسال|ارسال|ادفع|دفع|اشتر|اشتري|شراء|استثمر|استثمار|هدية|احذف|حذف|أضف|اضف|إضافة|اضافة|مستفيد|افتح|إنشاء|انشاء|ادخار|قطّة|قطة|قسّم|قسم)")


def requires_confirmation(message: str) -> bool:
    """Return true for customer requests that may create an external mutation."""
    return bool(_PROTECTED_EN.search(message) or _PROTECTED_AR.search(message))
