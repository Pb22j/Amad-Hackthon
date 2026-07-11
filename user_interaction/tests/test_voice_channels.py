from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from user_interaction_layer.agentic_client.client import MockAgenticClient
from user_interaction_layer.channels.voice_arabic import ArabicVoiceChannel
from user_interaction_layer.channels.voice_personaplex import EnglishVoiceChannel
from user_interaction_layer.orchestrator import create_default_orchestrator
from user_interaction_layer.providers.arabic_voice import ArabicVoiceProvider
from user_interaction_layer.providers.personaplex import PersonaPlexVoiceProvider


class VoiceChannelTests(unittest.TestCase):
    def test_english_voice_final_transcript_routes_to_agentic(self) -> None:
        client = MockAgenticClient()
        orchestrator = create_default_orchestrator(client)
        channel = EnglishVoiceChannel(
            provider=PersonaPlexVoiceProvider(api_key="key", agent_id="agent"),
            orchestrator=orchestrator,
        )

        reply = channel.handle_final_transcript(
            user_id="user-1",
            transcript="Please check my card payment status from yesterday.",
        )

        self.assertEqual(reply.content, "I'll check that now.")
        self.assertEqual(client.submitted_requests[0].source_provider, "personaplex")
        self.assertEqual(client.submitted_requests[0].channel.value, "voice")

    def test_arabic_voice_final_transcript_routes_to_agentic(self) -> None:
        client = MockAgenticClient()
        orchestrator = create_default_orchestrator(client)
        channel = ArabicVoiceChannel(
            provider=ArabicVoiceProvider(provider_name="cheap-arabic-provider", api_key="key"),
            orchestrator=orchestrator,
        )

        reply = channel.handle_final_transcript(
            user_id="user-1",
            transcript="راجع حالة دفع البطاقة من أمس من فضلك",
        )

        self.assertEqual(reply.content, "تمام، سأتحقق من ذلك الآن.")
        self.assertEqual(client.submitted_requests[0].source_provider, "arabic_voice")
        self.assertEqual(client.submitted_requests[0].channel.value, "voice")


if __name__ == "__main__":
    unittest.main()

