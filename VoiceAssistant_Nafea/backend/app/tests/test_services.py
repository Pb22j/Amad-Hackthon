import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.stt_service import OpenAIWhisperService, DeepgramSTTService, STTException
from app.services.llm_service import OpenAIConversationalService, GeminiConversationalService
from app.services.tts_service import OpenAITTSService, ElevenLabsTTSService

# ----------------- STT Service Tests -----------------

@pytest.mark.asyncio
@patch("app.services.stt_service.OpenAI")
async def test_openai_whisper_success(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.audio.transcriptions.create.return_value = MagicMock(text="transcribed text")

    service = OpenAIWhisperService(api_key="fake-key")
    result = await service.transcribe(b"fakebytes", mime_type="audio/webm")
    
    assert result == "transcribed text"

@pytest.mark.asyncio
@patch("app.services.stt_service.OpenAI")
async def test_openai_whisper_error(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.audio.transcriptions.create.side_effect = Exception("API Error")

    service = OpenAIWhisperService(api_key="fake-key")
    with pytest.raises(STTException):
        await service.transcribe(b"fakebytes")

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_deepgram_stt_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {"transcript": "deepgram transcribed text"}
                    ]
                }
            ]
        }
    }
    mock_post.return_value = mock_response

    service = DeepgramSTTService(api_key="fake-key")
    result = await service.transcribe(b"fakebytes")
    assert result == "deepgram transcribed text"

# ----------------- LLM Service Tests -----------------

@pytest.mark.asyncio
@patch("app.services.llm_service.OpenAI")
async def test_openai_llm_success(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="llm response text"))]
    )

    service = OpenAIConversationalService(api_key="fake-key")
    result = await service.generate_response("hello")
    assert result == "llm response text"

@pytest.mark.asyncio
@patch("app.services.llm_service.genai.Client")
async def test_gemini_llm_success(mock_client_class):
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        return_value=MagicMock(text="gemini response text")
    )
    mock_client_class.return_value = mock_client

    service = GeminiConversationalService(api_key="fake-key")
    result = await service.generate_response("hello")
    assert result == "gemini response text"

# ----------------- TTS Service Tests -----------------

@pytest.mark.asyncio
@patch("app.services.tts_service.OpenAI")
async def test_openai_tts_success(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.audio.speech.create.return_value = MagicMock(content=b"synthesizedaudiobytes")

    service = OpenAITTSService(api_key="fake-key")
    result = await service.synthesize("hello")
    assert result == b"synthesizedaudiobytes"

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_elevenlabs_tts_success(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"elevenlabsaudiobytes"
    mock_post.return_value = mock_response

    service = ElevenLabsTTSService(api_key="fake-key")
    result = await service.synthesize("hello", voice_id="Rachel")
    assert result == b"elevenlabsaudiobytes"
