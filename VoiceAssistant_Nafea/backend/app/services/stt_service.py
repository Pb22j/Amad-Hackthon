import abc
import io
import httpx
from openai import OpenAI
from app.config import settings
from app.utils.logger import logger, log_duration

class STTException(Exception):
    pass

class STTService(abc.ABC):
    @abc.abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """Transcribe audio bytes into text."""
        pass

class OpenAIWhisperService(STTService):
    def __init__(self, api_key: str = settings.OPENAI_API_KEY):
        if not api_key:
            logger.warning("OpenAI API Key is missing. Whisper service might fail.")
        # Setup client with configurable SSL verification
        http_client = httpx.Client(verify=settings.SSL_VERIFY)
        self.client = OpenAI(api_key=api_key, http_client=http_client)

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        # Determine extension from mime_type
        ext = "webm"
        if "wav" in mime_type:
            ext = "wav"
        elif "mpeg" in mime_type or "mp3" in mime_type:
            ext = "mp3"

        # Create virtual file using BytesIO with named attribute
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = f"audio.{ext}"

        try:
            with log_duration(f"OpenAI Whisper Transcribe ({ext})"):
                # Run the synchronous API call in a thread pool to avoid blocking the event loop
                import asyncio
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                )
                return response.text
        except Exception as e:
            logger.error(f"OpenAI Whisper transcription failed: {e}")
            raise STTException(f"OpenAI Whisper failed: {str(e)}")

class DeepgramSTTService(STTService):
    def __init__(self, api_key: str = settings.DEEPGRAM_API_KEY):
        self.api_key = api_key
        if not api_key:
            logger.warning("Deepgram API Key is missing. Deepgram service will fail.")

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        if not self.api_key:
            raise STTException("Deepgram API key is not configured.")

        # Prepare request headers and query parameters
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": mime_type
        }
        params = {
            "model": "nova-2",
            "smart_format": "true"
        }

        try:
            with log_duration("Deepgram Transcribe (nova-2)"):
                async with httpx.AsyncClient(verify=settings.SSL_VERIFY) as client:
                    response = await client.post(
                        "https://api.deepgram.com/v1/listen",
                        headers=headers,
                        params=params,
                        content=audio_bytes,
                        timeout=30.0
                    )
                    
                    if response.status_code != 200:
                        raise STTException(f"Deepgram returned status {response.status_code}: {response.text}")
                    
                    result = response.json()
                    transcript = result.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
                    return transcript
        except Exception as e:
            logger.error(f"Deepgram transcription failed: {e}")
            raise STTException(f"Deepgram failed: {str(e)}")

def get_stt_service() -> STTService:
    provider = settings.STT_PROVIDER.lower()
    if provider == "openai":
        return OpenAIWhisperService()
    elif provider == "deepgram":
        return DeepgramSTTService()
    else:
        raise ValueError(f"Unknown STT Provider: {provider}")
