"""OpenRouter chat provider adapter."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.providers.base import ChatProviderResponse


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter cannot return a completion."""


@dataclass
class OpenRouterChatProvider:
    api_key: str
    model: str
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 30.0

    def complete(self, *, messages: list[dict[str, str]], language: Language) -> ChatProviderResponse:
        if not self.api_key:
            raise OpenRouterError("OPENROUTER_API_KEY is missing")
        if not self.model:
            raise OpenRouterError("OpenRouter model is missing")

        payload = {
            "model": self.model,
            "messages": messages,
            "metadata": {"language": language.value},
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OpenRouterError("OpenRouter request failed") from exc
        except json.JSONDecodeError as exc:
            raise OpenRouterError("OpenRouter returned invalid JSON") from exc

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError("OpenRouter response did not include message content") from exc

        return ChatProviderResponse(text=text, model=self.model, metadata={"provider": "openrouter"})

