"""Early validation of capabilities supported by configured model providers."""

from __future__ import annotations


PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "openai": frozenset({"tool_calling", "structured_output", "async", "streaming", "embeddings"}),
    "openrouter": frozenset(
        {"tool_calling", "structured_output", "async", "streaming", "embeddings"}
    ),
    "anthropic": frozenset({"tool_calling", "structured_output", "async", "streaming"}),
    "minimax": frozenset({"tool_calling", "structured_output", "async", "streaming", "embeddings"}),
}


def validate_capabilities(provider: str, required: tuple[str, ...]) -> None:
    supported = PROVIDER_CAPABILITIES.get(provider)
    if supported is None:
        raise ValueError(f"unsupported model provider: {provider}")
    missing = set(required) - supported
    if missing:
        raise ValueError(f"provider {provider!r} lacks required capabilities: {sorted(missing)}")
