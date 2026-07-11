from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from user_interaction_layer.agentic_client.client import MockAgenticClient
from user_interaction_layer.agentic_client.schemas import AgenticEventType
from user_interaction_layer.api.server import build_application_from_env
from user_interaction_layer.application import InteractionApplication
from user_interaction_layer.notifications.handler import NotificationHandler
from user_interaction_layer.orchestrator import create_default_orchestrator


class ApplicationWiringTests(unittest.TestCase):
    def make_app(self) -> tuple[InteractionApplication, MockAgenticClient]:
        client = MockAgenticClient()
        orchestrator = create_default_orchestrator(client)
        app = InteractionApplication(
            orchestrator=orchestrator,
            notification_handler=NotificationHandler(orchestrator.session_store),
        )
        return app, client

    def test_chat_endpoint_handler_dispatches_to_agentic(self) -> None:
        app, client = self.make_app()

        response = app.handle_chat(
            {
                "user_id": "user-1",
                "message": "Please prepare a short overview of my savings account activity this week.",
            }
        )

        self.assertEqual(response["decision_type"], "dispatch")
        self.assertEqual(response["message_to_user"], "I'll check that now.")
        self.assertEqual(len(client.submitted_requests), 1)

    def test_voice_transcript_handler_marks_voice_channel(self) -> None:
        app, client = self.make_app()

        response = app.handle_voice_transcript(
            {
                "user_id": "user-1",
                "transcript": "Please check whether my latest card payment was posted.",
                "language": "en",
                "source_provider": "personaplex",
            }
        )

        self.assertEqual(response["decision_type"], "dispatch")
        self.assertEqual(client.submitted_requests[0].channel.value, "voice")
        self.assertEqual(client.submitted_requests[0].source_provider, "personaplex")

    def test_agentic_notification_renders_user_message(self) -> None:
        app, client = self.make_app()
        chat_response = app.handle_chat(
            {
                "user_id": "user-1",
                "message": "Please check my account activity for the last seven days.",
            }
        )

        notification_response = app.handle_agentic_notification(
            {
                "task_id": chat_response["task_id"],
                "request_id": chat_response["request_id"],
                "session_id": chat_response["session_id"],
                "event_type": AgenticEventType.COMPLETED.value,
                "user_safe_summary": "Done. I prepared the account activity summary.",
                "details": {},
            }
        )

        self.assertEqual(
            notification_response["message_to_user"],
            "Done. I prepared the account activity summary.",
        )
        self.assertEqual(client.submitted_requests[0].natural_language_request.startswith("Please check"), True)

    def test_build_application_from_env_can_force_mock(self) -> None:
        app = build_application_from_env(use_mock_agentic=True)

        response = app.handle_chat(
            {
                "user_id": "user-1",
                "message": "Please review my portfolio allocation for this quarter.",
            }
        )

        self.assertEqual(response["decision_type"], "dispatch")


if __name__ == "__main__":
    unittest.main()

