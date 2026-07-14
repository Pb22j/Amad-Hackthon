import abc
import asyncio
import httpx
from openai import OpenAI
from app.config import settings
from app.utils.logger import logger, log_duration

class TTSException(Exception):
    pass

class TTSService(abc.ABC):
    @abc.abstractmethod
    async def synthesize(self, text: str, voice_id: str = settings.TTS_VOICE_ID) -> bytes:
        """Synthesize text into speech (returns audio bytes)."""
        pass

class OpenAITTSService(TTSService):
    def __init__(self, api_key: str = settings.OPENAI_API_KEY, model: str = settings.TTS_MODEL_ID):
        if not api_key:
            logger.warning("OpenAI API Key is missing. OpenAI TTS service might fail.")
        # Setup client with configurable SSL verification
        http_client = httpx.Client(verify=settings.SSL_VERIFY)
        self.client = OpenAI(api_key=api_key, http_client=http_client)
        self.model = model

    async def synthesize(self, text: str, voice_id: str = settings.TTS_VOICE_ID) -> bytes:
        # Map or validate voice_id for OpenAI: alloy, echo, fable, onyx, nova, shimmer
        voice = voice_id if voice_id in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] else "alloy"
        
        try:
            with log_duration(f"OpenAI TTS Synthesize ({voice})"):
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.audio.speech.create(
                        model=self.model,
                        voice=voice,
                        input=text,
                        response_format="mp3"
                    )
                )
                # response.content returns the binary audio
                return response.content
        except Exception as e:
            logger.error(f"OpenAI TTS synthesis failed: {e}")
            raise TTSException(f"OpenAI TTS failed: {str(e)}")

class ElevenLabsTTSService(TTSService):
    def __init__(self, api_key: str = settings.ELEVENLABS_API_KEY):
        self.api_key = api_key
        if not api_key:
            logger.warning("ElevenLabs API Key is missing. ElevenLabs service will fail.")

    async def synthesize(self, text: str, voice_id: str = settings.TTS_VOICE_ID) -> bytes:
        if not self.api_key:
            raise TTSException("ElevenLabs API key is not configured.")

        # Default fallback to Rachel voice ID if voice_id is standard OpenAI name
        vid = voice_id
        if vid in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]:
            vid = "21m00Tcm4TlvDq8ikWAM"  # Rachel (default voice ID)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        # Using standard settings for ElevenLabs
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        try:
            with log_duration(f"ElevenLabs TTS Synthesize ({vid})"):
                async with httpx.AsyncClient(verify=settings.SSL_VERIFY) as client:
                    response = await client.post(
                        url,
                        json=data,
                        headers=headers,
                        timeout=30.0
                    )
                    
                    if response.status_code != 200:
                        raise TTSException(f"ElevenLabs returned status {response.status_code}: {response.text}")
                    
                    return response.content
        except Exception as e:
            logger.error(f"ElevenLabs TTS synthesis failed: {e}")
            raise TTSException(f"ElevenLabs failed: {str(e)}")

def get_tts_service() -> TTSService:
    provider = settings.TTS_PROVIDER.lower()
    if provider == "openai":
        return OpenAITTSService()
    elif provider == "elevenlabs":
        return ElevenLabsTTSService()
    else:
        raise ValueError(f"Unknown TTS Provider: {provider}")
