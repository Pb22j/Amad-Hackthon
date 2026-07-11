"""Application service that wires channels, policy, agentic client, and notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from user_interaction_layer.agentic_client.schemas import AgenticEvent, Language
from user_interaction_layer.notifications.handler import NotificationHandler
from user_interaction_layer.orchestrator import InteractionResult, UserInteractionOrchestrator


@dataclass
class InteractionApplication:
    orchestrator: UserInteractionOrchestrator
    notification_handler: NotificationHandler

    def handle_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.orchestrator.handle_chat_message(
            user_id=_required_string(payload, "user_id"),
            message=_required_string(payload, "message"),
            session_id=_optional_string(payload, "session_id"),
            explicit_language=_optional_string(payload, "language"),
            confirmed=_optional_bool(payload, "confirmed"),
            agentic_message=_optional_string(payload, "planned_request"),
        )
        return _result_payload(result)

    def handle_voice_transcript(self, payload: dict[str, Any]) -> dict[str, Any]:
        language = _optional_string(payload, "language")
        source_provider = _optional_string(payload, "source_provider") or _default_voice_provider(language)
        result = self.orchestrator.handle_voice_transcript(
            user_id=_required_string(payload, "user_id"),
            transcript=_required_string(payload, "transcript"),
            source_provider=source_provider,
            session_id=_optional_string(payload, "session_id"),
            explicit_language=language,
            confirmed=_optional_bool(payload, "confirmed"),
            agentic_message=_optional_string(payload, "planned_request"),
        )
        return _result_payload(result)

    def handle_agentic_notification(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = AgenticEvent.from_payload(payload)
        language = self._language_for_event(event, _optional_string(payload, "language"))
        message = self.notification_handler.handle(event, language)
        return {
            "session_id": event.session_id,
            "task_id": event.task_id,
            "request_id": event.request_id,
            "event_type": event.event_type.value,
            "language": language.value,
            "message_to_user": message,
        }

    def _language_for_event(self, event: AgenticEvent, fallback: str | None) -> Language:
        session = self.orchestrator.session_store.sessions.get(event.session_id)
        if session:
            return session.active_language
        if fallback:
            return Language(fallback)
        return Language.ENGLISH


def _result_payload(result: InteractionResult) -> dict[str, Any]:
    return {
        "session_id": result.session_id,
        "message_to_user": result.message_to_user,
        "decision_type": result.decision_type.value,
        "language": result.language.value,
        "task_id": result.task_id,
        "request_id": result.request_id,
    }


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' is required")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be a string")
    return value or None


def _optional_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"'{key}' must be a boolean")
    return value


def _default_voice_provider(language: str | None) -> str:
    if language == Language.ARABIC.value:
        return "arabic_voice"
    return "personaplex"
