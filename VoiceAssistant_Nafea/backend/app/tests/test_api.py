import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

# Import app to test
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_config_endpoint():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "stt_provider" in data
    assert "llm_provider" in data
    assert "tts_provider" in data

@patch("app.main.get_stt_service")
@patch("app.main.get_llm_service")
@patch("app.main.get_tts_service")
@patch("app.main.audio_cache")
def test_voice_chat_endpoint_success(mock_cache, mock_get_tts, mock_get_llm, mock_get_stt):
    # Set up mocks
    mock_stt = MagicMock()
    mock_stt.transcribe = AsyncMock(return_value="Hello assistant")
    mock_get_stt.return_value = mock_stt

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value="Hello user, how are you?")
    mock_get_llm.return_value = mock_llm

    mock_tts = MagicMock()
    mock_tts.synthesize = AsyncMock(return_value=b"testaudiobytes")
    mock_get_tts.return_value = mock_tts

    # Mock Cache returning None (cache miss)
    mock_cache.get.return_value = None

    # Dummy file
    files = {"file": ("audio.webm", b"dummy_audio_bytes", "audio/webm")}
    
    response = client.post("/api/voice-chat", files=files)
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_transcript"] == "Hello assistant"
    assert data["agent_text"] == "Hello user, how are you?"
    assert data["audio_base64"] == "dGVzdGF1ZGlvYnl0ZXM="  # base64 for b"testaudiobytes"
    assert data["audio_mime_type"] == "audio/mp3"
    
    # Assert cache set was called
    mock_cache.set.assert_called_once_with(
        provider="openai",  # default TTS provider in config settings
        voice_id="alloy",   # default TTS voice in config settings
        text="Hello user, how are you?",
        audio_bytes=b"testaudiobytes"
    )

@patch("app.main.get_stt_service")
def test_voice_chat_empty_transcript(mock_get_stt):
    mock_stt = MagicMock()
    mock_stt.transcribe = AsyncMock(return_value="")  # Empty transcription
    mock_get_stt.return_value = mock_stt

    files = {"file": ("audio.webm", b"dummy_audio_bytes", "audio/webm")}
    response = client.post("/api/voice-chat", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["user_transcript"] == ""
    assert "try speaking again" in data["agent_text"]
    assert data["audio_base64"] == ""

