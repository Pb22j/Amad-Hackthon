from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from user_interaction_layer.agentic_client.client import MockAgenticClient
from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.orchestrator import create_default_orchestrator
from user_interaction_layer.voice.models import AudioInput
from user_interaction_layer.voice.providers import MockVoiceAudioProvider
from user_interaction_layer.voice.service import VoiceInteractionService


class VoiceServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_audio_turn_transcribes_dispatches_and_synthesizes(self) -> None:
        client = MockAgenticClient()
        orchestrator = create_default_orchestrator(client)
        service = VoiceInteractionService(
            orchestrator=orchestrator,
            audio_provider=MockVoiceAudioProvider(),
        )

        result = await service.handle_audio_turn(
            user_id="user-1",
            audio=AudioInput(data=b"Please check my latest account activity."),
            language=Language.ENGLISH,
            source_provider="personaplex",
        )

        self.assertEqual(result.transcript, "Please check my latest account activity.")
        self.assertEqual(result.message_to_user, "I'll check that now.")
        self.assertTrue(result.audio.startswith(b"RIFF"))
        self.assertEqual(result.audio_mime_type, "audio/wav")
        self.assertEqual(client.submitted_requests[0].channel.value, "voice")

    async def test_arabic_text_turn_uses_arabic_acknowledgement(self) -> None:
        client = MockAgenticClient()
        orchestrator = create_default_orchestrator(client)
        service = VoiceInteractionService(
            orchestrator=orchestrator,
            audio_provider=MockVoiceAudioProvider(),
        )

        result = await service.handle_text_turn(
            user_id="user-1",
            transcript="راجع حالة حسابي لهذا الأسبوع من فضلك",
            language=Language.ARABIC,
            source_provider="openai",
        )

        self.assertEqual(result.message_to_user, "تمام، سأتحقق من ذلك الآن.")
        self.assertEqual(result.language, Language.ARABIC)
        self.assertEqual(client.submitted_requests[0].source_provider, "openai")


if __name__ == "__main__":
    unittest.main()
