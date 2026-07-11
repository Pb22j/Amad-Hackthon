from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from user_interaction_layer.agentic_client.client import MockAgenticClient
from user_interaction_layer.application import InteractionApplication
from user_interaction_layer.api.fastapi_app import create_fastapi_app
from user_interaction_layer.notifications.handler import NotificationHandler
from user_interaction_layer.orchestrator import create_default_orchestrator
from user_interaction_layer.voice.providers import MockVoiceAudioProvider


class FastAPIVoiceTests(unittest.TestCase):
    def make_client(self) -> TestClient:
        agentic_client = MockAgenticClient()
        orchestrator = create_default_orchestrator(agentic_client)
        interaction_app = InteractionApplication(
            orchestrator=orchestrator,
            notification_handler=NotificationHandler(orchestrator.session_store),
        )
        app = create_fastapi_app(
            interaction_app=interaction_app,
            voice_provider=MockVoiceAudioProvider(),
        )
        return TestClient(app)

    def test_voice_websocket_text_turn_returns_audio(self) -> None:
        client = self.make_client()

        with client.websocket_connect("/interaction/voice/ws?user_id=user-1&language=en") as ws:
            self.assertEqual(ws.receive_json()["type"], "ready")
            ws.send_json(
                {
                    "type": "text",
                    "text": "Please check my account balance and recent activity.",
                }
            )
            turn = ws.receive_json()
            audio_start = ws.receive_json()
            audio = ws.receive_bytes()
            audio_end = ws.receive_json()

        self.assertEqual(turn["type"], "voice_turn")
        self.assertEqual(turn["message_to_user"], "I'll check that now.")
        self.assertEqual(audio_start["type"], "audio_start")
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertEqual(turn["audio_mime_type"], "audio/wav")
        self.assertEqual(audio_end["type"], "audio_end")

    def test_voice_websocket_audio_commit_returns_arabic_audio(self) -> None:
        client = self.make_client()

        with client.websocket_connect("/interaction/voice/ws?user_id=user-1&language=ar") as ws:
            self.assertEqual(ws.receive_json()["type"], "ready")
            ws.send_bytes("راجع حالة حسابي لهذا الأسبوع من فضلك".encode("utf-8"))
            self.assertEqual(ws.receive_json()["type"], "audio_buffered")
            ws.send_json({"type": "commit"})
            turn = ws.receive_json()
            ws.receive_json()
            audio = ws.receive_bytes()
            ws.receive_json()

        self.assertEqual(turn["language"], "ar")
        self.assertEqual(turn["message_to_user"], "تمام، سأتحقق من ذلك الآن.")
        self.assertTrue(audio.startswith(b"RIFF"))
        self.assertEqual(turn["audio_format"], "wav")

    def test_health_describes_runnable_mock_capabilities_without_secrets(self) -> None:
        client = self.make_client()

        response = client.get("/health")
        payload = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "nafi-interaction")
        self.assertEqual(payload["providers"]["voice"], "mock")
        self.assertTrue(payload["capabilities"]["voice_websocket"])
        self.assertNotIn("api_key", str(payload).lower())


if __name__ == "__main__":
    unittest.main()
