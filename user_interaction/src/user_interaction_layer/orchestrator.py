"""High-level orchestration for user interaction flows."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.client import AgenticClient, AgenticClientError
from user_interaction_layer.agentic_client.schemas import (
    AgenticEvent,
    AgenticEventType,
    Channel,
    Language,
)
from user_interaction_layer.nlu.language_detection import detect_language
from user_interaction_layer.nlu.request_builder import build_agentic_request
from user_interaction_layer.notifications.renderer import render_agentic_event
from user_interaction_layer.policy.interaction_policy import DecisionType, InteractionPolicy
from user_interaction_layer.session.models import InteractionTurn, PendingTask
from user_interaction_layer.session.store import InMemorySessionStore


@dataclass(frozen=True)
class InteractionResult:
    session_id: str
    message_to_user: str
    decision_type: DecisionType
    language: Language
    task_id: str = ""
    request_id: str = ""


@dataclass
class UserInteractionOrchestrator:
    agentic_client: AgenticClient
    session_store: InMemorySessionStore
    policy: InteractionPolicy

    def handle_chat_message(
        self,
        *,
        user_id: str,
        message: str,
        session_id: str | None = None,
        explicit_language: str | Language | None = None,
        confirmed: bool = False,
        agentic_message: str | None = None,
    ) -> InteractionResult:
        return self._handle_user_message(
            user_id=user_id,
            message=message,
            channel=Channel.CHAT,
            source_provider="openrouter",
            session_id=session_id,
            explicit_language=explicit_language,
            confirmed=confirmed,
            agentic_message=agentic_message,
        )

    def handle_voice_transcript(
        self,
        *,
        user_id: str,
        transcript: str,
        source_provider: str,
        session_id: str | None = None,
        explicit_language: str | Language | None = None,
        confirmed: bool = False,
        agentic_message: str | None = None,
    ) -> InteractionResult:
        return self._handle_user_message(
            user_id=user_id,
            message=transcript,
            channel=Channel.VOICE,
            source_provider=source_provider,
            session_id=session_id,
            explicit_language=explicit_language,
            confirmed=confirmed,
            agentic_message=agentic_message,
        )

    def _handle_user_message(
        self,
        *,
        user_id: str,
        message: str,
        channel: Channel,
        source_provider: str,
        session_id: str | None = None,
        explicit_language: str | Language | None = None,
        confirmed: bool = False,
        agentic_message: str | None = None,
    ) -> InteractionResult:
        language = detect_language(message, explicit_language)
        session = self.session_store.get_or_create_session(
            user_id=user_id,
            channel=channel,
            language=language,
            session_id=session_id,
        )
        self.session_store.add_turn(
            InteractionTurn(
                session_id=session.session_id,
                role="user",
                channel=channel,
                language=language,
                content=message,
                provider_metadata={"provider": source_provider},
            )
        )

        conversation_summary = self._conversation_context_summary(session.session_id)
        decision = self.policy.evaluate(
            message,
            language,
            conversation_context_summary=conversation_summary,
        )
        if decision.decision_type in {DecisionType.CLARIFY, DecisionType.REFUSE}:
            self._record_assistant_turn(session.session_id, channel, language, decision.user_message)
            return InteractionResult(
                session_id=session.session_id,
                message_to_user=decision.user_message,
                decision_type=decision.decision_type,
                language=language,
            )

        agentic_request = build_agentic_request(
            session=session,
            user_message=message,
            source_provider=source_provider,
            conversation_context_summary=conversation_summary,
            confirmation_received=confirmed,
            agentic_message=agentic_message,
        )

        try:
            agentic_response = self.agentic_client.submit_request(agentic_request)
        except AgenticClientError:
            message_to_user = self._agentic_unavailable_message(language)
            self._record_assistant_turn(session.session_id, channel, language, message_to_user)
            return InteractionResult(
                session_id=session.session_id,
                message_to_user=message_to_user,
                decision_type=DecisionType.REFUSE,
                language=language,
                request_id=agentic_request.request_id,
            )

        task = PendingTask(
            task_id=agentic_response.task_id,
            request_id=agentic_response.request_id,
            session_id=session.session_id,
            status=agentic_response.status.value,
            last_user_message=message,
            last_user_safe_summary=agentic_response.user_safe_message,
        )
        self.session_store.save_pending_task(task)

        accepted_event = AgenticEvent(
            task_id=agentic_response.task_id,
            request_id=agentic_response.request_id,
            session_id=session.session_id,
            event_type=AgenticEventType.ACCEPTED,
            user_safe_summary=agentic_response.user_safe_message,
        )
        message_to_user = render_agentic_event(accepted_event, language)
        self._record_assistant_turn(session.session_id, channel, language, message_to_user)
        return InteractionResult(
            session_id=session.session_id,
            message_to_user=message_to_user,
            decision_type=DecisionType.DISPATCH,
            language=language,
            task_id=agentic_response.task_id,
            request_id=agentic_response.request_id,
        )

    def _record_assistant_turn(
        self,
        session_id: str,
        channel: Channel,
        language: Language,
        message: str,
    ) -> None:
        self.session_store.add_turn(
            InteractionTurn(
                session_id=session_id,
                role="assistant",
                channel=channel,
                language=language,
                content=message,
                provider_metadata={"component": "interaction_policy"},
            )
        )

    def _conversation_context_summary(self, session_id: str) -> str:
        turns = self.session_store.get_recent_turns(session_id, limit=6)
        visible_turns = [turn for turn in turns if turn.role in {"user", "assistant"}]
        return "\n".join(f"{turn.role}: {turn.content}" for turn in visible_turns[:-1])

    def _agentic_unavailable_message(self, language: Language) -> str:
        if language == Language.ARABIC:
            return "لا أستطيع إكمال الطلب الآن. يمكننا المحاولة مرة أخرى بعد قليل."
        return "I cannot complete that right now. We can try again in a moment."


def create_default_orchestrator(
    agentic_client: AgenticClient,
    policy: InteractionPolicy | None = None,
) -> UserInteractionOrchestrator:
    return UserInteractionOrchestrator(
        agentic_client=agentic_client,
        session_store=InMemorySessionStore(),
        policy=policy or InteractionPolicy(),
    )
