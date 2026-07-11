from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from user_interaction_layer.agentic_client.schemas import AgenticEvent, AgenticEventType, Language
from user_interaction_layer.notifications.renderer import render_agentic_event


class NotificationTests(unittest.TestCase):
    def test_completed_notification_redacts_financial_numbers(self) -> None:
        event = AgenticEvent(
            task_id="task-1",
            request_id="request-1",
            session_id="session-1",
            event_type=AgenticEventType.COMPLETED,
            user_safe_summary="Updated card 4111111111111111 successfully.",
        )

        message = render_agentic_event(event, Language.ENGLISH)

        self.assertIn("[REDACTED_NUMBER]", message)
        self.assertNotIn("4111111111111111", message)

    def test_failed_notification_hides_stack_traces(self) -> None:
        event = AgenticEvent(
            task_id="task-1",
            request_id="request-1",
            session_id="session-1",
            event_type=AgenticEventType.FAILED,
            user_safe_summary="Traceback: api_key leaked",
        )

        message = render_agentic_event(event, Language.ENGLISH)

        self.assertEqual(message, "I could not finish that yet. We can try again or review the details.")


if __name__ == "__main__":
    unittest.main()

