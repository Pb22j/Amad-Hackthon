"""Handle agentic notifications and update session task state."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import AgenticEvent, Language
from user_interaction_layer.notifications.renderer import render_agentic_event
from user_interaction_layer.session.store import InMemorySessionStore


@dataclass
class NotificationHandler:
    session_store: InMemorySessionStore

    def handle(self, event: AgenticEvent, language: Language) -> str:
        task = self.session_store.get_pending_task(event.task_id)
        if task:
            task.update(event.event_type.value, event.user_safe_summary)
        return render_agentic_event(event, language)

