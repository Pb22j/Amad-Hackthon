"""Notification transport placeholders."""

from __future__ import annotations

from user_interaction_layer.agentic_client.schemas import AgenticEvent


def parse_agentic_notification(payload: dict[str, object]) -> AgenticEvent:
    return AgenticEvent.from_payload(dict(payload))

