import abc
import asyncio
from openai import OpenAI
from google import genai
from google.genai import types
from app.config import settings
from app.utils.logger import logger, log_duration

class LLMException(Exception):
    pass

class LLMService(abc.ABC):
    @abc.abstractmethod
    async def generate_response(self, prompt: str, system_prompt: str = settings.LLM_SYSTEM_PROMPT) -> str:
        """Generate response based on a prompt and optionally system instructions."""
        pass

class OpenAIConversationalService(LLMService):
    def __init__(self, api_key: str = settings.OPENAI_API_KEY, model: str = settings.LLM_MODEL):
        if not api_key:
            logger.warning("OpenAI API Key is missing. OpenAI LLM service might fail.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    async def generate_response(self, prompt: str, system_prompt: str = settings.LLM_SYSTEM_PROMPT) -> str:
        try:
            with log_duration(f"OpenAI LLM Response ({self.model})"):
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=150,
                        temperature=0.7
                    )
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI LLM response generation failed: {e}")
            raise LLMException(f"OpenAI LLM failed: {str(e)}")

class GeminiConversationalService(LLMService):
    # Ordered fallback list of models to try if primary hits rate limits
    FALLBACK_MODELS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
    ]

    def __init__(self, api_key: str = settings.GEMINI_API_KEY, model: str = "gemini-2.5-flash"):
        if not api_key:
            logger.warning("Gemini API Key is missing. Gemini LLM service will fail.")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model

    async def _try_generate(self, model_name: str, prompt: str, system_prompt: str) -> str:
        response = await self.client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=150,
                temperature=0.7
            ),
        )
        return response.text.strip()

    async def generate_response(self, prompt: str, system_prompt: str = settings.LLM_SYSTEM_PROMPT) -> str:
        # Build ordered list: configured model first, then fallbacks (deduplicated)
        models_to_try = [self.model_name]
        for m in self.FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error = None

        for model_name in models_to_try:
            try:
                with log_duration(f"Gemini LLM Response ({model_name})"):
                    result = await self._try_generate(model_name, prompt, system_prompt)
                    return result
            except Exception as e:
                error_str = str(e)
                last_error = e
                if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                    logger.warning(f"Rate limit hit on model '{model_name}', trying next fallback...")
                    continue
                else:
                    # Non-rate-limit error, don't retry with other models
                    logger.error(f"Gemini LLM response generation failed on '{model_name}': {e}")
                    raise LLMException(f"Gemini LLM failed: {error_str}")

        # All models exhausted
        logger.error(f"All Gemini model fallbacks exhausted. Last error: {last_error}")
        raise LLMException("Gemini LLM failed: All models rate-limited. Please wait and try again.")

class MinimaxConversationalService(LLMService):
    def __init__(self, api_key: str = settings.MINIMAX_API_KEY, model: str = settings.LLM_MODEL):
        if not api_key:
            logger.warning("MiniMax API Key is missing. MiniMax LLM service might fail.")
        self.client = OpenAI(api_key=api_key, base_url="https://api.minimax.io/v1")
        self.model = model

    async def generate_response(self, prompt: str, system_prompt: str = settings.LLM_SYSTEM_PROMPT) -> str:
        try:
            with log_duration(f"MiniMax LLM Response ({self.model})"):
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=150,
                        temperature=0.7
                    )
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"MiniMax LLM response generation failed: {e}")
            raise LLMException(f"MiniMax LLM failed: {str(e)}")

def get_llm_service() -> LLMService:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":
        return OpenAIConversationalService()
    elif provider == "minimax":
        return MinimaxConversationalService()
    elif provider == "gemini":
        # Check model name fallback if set to OpenAI model in settings
        model_name = settings.LLM_MODEL
        if "gpt" in model_name:
            model_name = "gemini-2.5-flash"
        return GeminiConversationalService(model=model_name)
    elif provider == "nvidia":
        return NvidiaConversationalService()
    else:
        raise ValueError(f"Unknown LLM Provider: {provider}")


class NvidiaConversationalService(LLMService):
    """Uses NVIDIA's OpenAI-compatible API at integrate.api.nvidia.com."""

    NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

    def __init__(self, api_key: str = settings.NVIDIA_API_KEY, model: str = settings.LLM_MODEL):
        if not api_key:
            logger.warning("NVIDIA API Key is missing. NVIDIA LLM service will fail.")
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.NVIDIA_BASE_URL
        )
        self.model = model

    async def generate_response(self, prompt: str, system_prompt: str = settings.LLM_SYSTEM_PROMPT) -> str:
        try:
            with log_duration(f"NVIDIA LLM Response ({self.model})"):
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=150,
                        temperature=0.7
                    )
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"NVIDIA LLM response generation failed: {e}")
            raise LLMException(f"NVIDIA LLM failed: {str(e)}")
