from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from user_interaction_layer.agentic_client.client import MockAgenticClient
from user_interaction_layer.agentic_client.schemas import Channel, Language
from user_interaction_layer.nlu.request_builder import build_agentic_request
from user_interaction_layer.session.models import Session


class AgenticClientContractTests(unittest.TestCase):
    def test_agentic_payload_uses_single_natural_language_request(self) -> None:
        session = Session(
            user_id="user-1",
            channel=Channel.CHAT,
            active_language=Language.ENGLISH,
        )
        request = build_agentic_request(
            session=session,
            user_message="Please summarize my portfolio performance for June.",
            source_provider="openrouter",
            conversation_context_summary="user: My card is 4111111111111111",
        )
        payload = request.to_payload()

        self.assertIn("natural_language_request", payload)
        self.assertEqual(
            payload["natural_language_request"],
            "Please summarize my portfolio performance for June.",
        )
        self.assertNotIn("normalized_intent", payload)
        self.assertNotIn("entities", payload)
        self.assertNotIn("constraints", payload)
        self.assertIn("[REDACTED_NUMBER]", payload["metadata"]["conversation_context_summary"])

    def test_mock_agentic_client_records_single_request(self) -> None:
        session = Session(
            user_id="user-1",
            channel=Channel.CHAT,
            active_language=Language.ENGLISH,
        )
        request = build_agentic_request(
            session=session,
            user_message="Please check my account status.",
            source_provider="openrouter",
        )
        client = MockAgenticClient()

        response = client.submit_request(request)

        self.assertEqual(len(client.submitted_requests), 1)
        self.assertEqual(response.request_id, request.request_id)
        self.assertTrue(response.task_id)

    def test_mutations_carry_exact_confirmation_state_to_agentic(self) -> None:
        session = Session(user_id="user-1", channel=Channel.CHAT, active_language=Language.ENGLISH)
        unconfirmed = build_agentic_request(
            session=session,
            user_message="Transfer 250 SAR from Al Rajhi to SNB",
            source_provider="web",
        )
        self.assertTrue(unconfirmed.confirmation.required)
        self.assertFalse(unconfirmed.confirmation.received)

        confirmed = build_agentic_request(
            session=session,
            user_message="Transfer 250 SAR from Al Rajhi to SNB",
            source_provider="web",
            confirmation_received=True,
        )
        self.assertTrue(confirmed.confirmation.required)
        self.assertTrue(confirmed.confirmation.received)

        read_only = build_agentic_request(
            session=session,
            user_message="Analyze my finances",
            source_provider="web",
        )
        self.assertFalse(read_only.confirmation.required)
        self.assertFalse(read_only.confirmation.received)

    def test_validated_model_plan_is_forwarded_without_replacing_original_message(self) -> None:
        session = Session(user_id="user-1", channel=Channel.CHAT, active_language=Language.ENGLISH)
        request = build_agentic_request(
            session=session,
            user_message="Move two hundred and fifty riyals between my banks",
            source_provider="openai",
            agentic_message='{"intent":"transfer_between_accounts","amount":250}',
            confirmation_received=True,
        )
        self.assertEqual(request.original_user_message, "Move two hundred and fifty riyals between my banks")
        self.assertEqual(request.natural_language_request, '{"intent":"transfer_between_accounts","amount":250}')


if __name__ == "__main__":
    unittest.main()
