"""In-memory session store for the first implementation pass."""

from __future__ import annotations

from dataclasses import dataclass, field

from user_interaction_layer.agentic_client.schemas import Channel, Language
from user_interaction_layer.session.models import InteractionTurn, PendingTask, Session


@dataclass
class InMemorySessionStore:
    sessions: dict[str, Session] = field(default_factory=dict)
    turns: dict[str, list[InteractionTurn]] = field(default_factory=dict)
    pending_tasks: dict[str, PendingTask] = field(default_factory=dict)

    def create_session(self, user_id: str, channel: Channel, language: Language) -> Session:
        session = Session(user_id=user_id, channel=channel, active_language=language)
        self.sessions[session.session_id] = session
        self.turns[session.session_id] = []
        return session

    def get_or_create_session(
        self,
        user_id: str,
        channel: Channel,
        language: Language,
        session_id: str | None = None,
    ) -> Session:
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
            session.active_language = language
            session.channel = channel
            session.touch()
            return session
        return self.create_session(user_id=user_id, channel=channel, language=language)

    def add_turn(self, turn: InteractionTurn) -> None:
        self.turns.setdefault(turn.session_id, []).append(turn)
        session = self.sessions.get(turn.session_id)
        if session:
            session.touch()

    def get_recent_turns(self, session_id: str, limit: int = 8) -> list[InteractionTurn]:
        return self.turns.get(session_id, [])[-limit:]

    def save_pending_task(self, task: PendingTask) -> None:
        self.pending_tasks[task.task_id] = task

    def get_pending_task(self, task_id: str) -> PendingTask | None:
        return self.pending_tasks.get(task_id)

