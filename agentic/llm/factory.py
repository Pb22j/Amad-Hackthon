"""Provider-neutral construction of role-specific LangChain chat models."""

from __future__ import annotations

import os
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from agentic.config.loader import LLMConfig, ModelConfig
from agentic.llm.capabilities import validate_capabilities


class ModelFactory:
    """Create and cache models by semantic role from ``llm.yaml``."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._cache: dict[str, BaseChatModel] = {}

    def create(self, role: str) -> BaseChatModel:
        """Build one configured role after validating provider capabilities."""

        if role in self._cache:
            return self._cache[role]
        try:
            item = self.config.models[role]
        except KeyError as exc:
            raise KeyError(f"unknown model role: {role}") from exc
        validate_capabilities(item.provider, item.required_capabilities)
        model = self._build(item)
        self._cache[role] = model
        return model

    def create_fallbacks(self, role: str) -> list[BaseChatModel]:
        """Build the ordered fallback models configured for a primary role."""

        try:
            fallback_roles = self.config.models[role].fallback_roles
        except KeyError as exc:
            raise KeyError(f"unknown model role: {role}") from exc
        if role in fallback_roles:
            raise ValueError("a model role cannot fall back to itself")
        return [self.create(fallback_role) for fallback_role in fallback_roles]

    def _build(self, item: ModelConfig) -> BaseChatModel:
        common: dict[str, Any] = {
            "temperature": item.temperature,
            "timeout": item.timeout_seconds,
            "max_retries": item.max_retries,
        }
        if item.provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY is required for an OpenRouter model")
            return init_chat_model(
                item.model,
                model_provider="openai",
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                **common,
            )
        if item.provider == "openai":
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY is required for an OpenAI model")
            return init_chat_model(item.model, model_provider="openai", **common)
        if item.provider == "anthropic":
            if not os.getenv("ANTHROPIC_API_KEY"):
                raise RuntimeError("ANTHROPIC_API_KEY is required for an Anthropic model")
            return init_chat_model(item.model, model_provider="anthropic", **common)
        raise ValueError(f"unsupported model provider: {item.provider}")
