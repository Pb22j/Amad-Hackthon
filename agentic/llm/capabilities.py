"""Early validation of capabilities supported by configured model providers."""

from __future__ import annotations


PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "openai": frozenset({"tool_calling", "structured_output", "async", "streaming", "embeddings"}),
    "minimax": frozenset({"tool_calling", "structured_output", "async", "streaming"}),
    "anthropic": frozenset({"tool_calling", "structured_output", "async", "streaming"}),
}


def validate_capabilities(provider: str, required: tuple[str, ...]) -> None:
    supported = PROVIDER_CAPABILITIES.get(provider)
    if supported is None:
        raise ValueError(f"unsupported model provider: {provider}")
    missing = set(required) - supported
    if missing:
        raise ValueError(f"provider {provider!r} lacks required capabilities: {sorted(missing)}")
