"""Chat channel adapter."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.channels.base import ChannelMessage, ChannelReply
from user_interaction_layer.orchestrator import UserInteractionOrchestrator


@dataclass
class ChatChannel:
    orchestrator: UserInteractionOrchestrator

    def handle(self, message: ChannelMessage) -> ChannelReply:
        result = self.orchestrator.handle_chat_message(
            user_id=message.user_id,
            message=message.content,
            session_id=message.session_id,
            explicit_language=message.language,
        )
        return ChannelReply(
            session_id=result.session_id,
            content=result.message_to_user,
            language=result.language,
        )

