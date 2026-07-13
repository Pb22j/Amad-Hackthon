from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agentic.policy.injection_signals import detect_injection_signals
from agentic.security.redaction import redact_text


class MemoryPolicyError(ValueError):
    pass


class MemoryPolicy:
    def __init__(self, *, allowed_types: frozenset[str], forbidden_key_fragments: frozenset[str]):
        self.allowed_types = allowed_types
        self.forbidden_key_fragments = frozenset(item.lower() for item in forbidden_key_fragments)

    def validate(self, memory_type: str, value: dict[str, Any]) -> None:
        if memory_type not in self.allowed_types:
            raise MemoryPolicyError(f"memory type is not allowed: {memory_type}")
        self._validate_value(value)

    def _validate_value(self, value: Any, path: str = "value") -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).lower()
                if any(fragment in normalized for fragment in self.forbidden_key_fragments):
                    raise MemoryPolicyError(f"sensitive memory key is forbidden: {path}.{key}")
                self._validate_value(item, f"{path}.{key}")
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for index, item in enumerate(value):
                self._validate_value(item, f"{path}[{index}]")
        elif isinstance(value, str):
            if redact_text(value) != value:
                raise MemoryPolicyError(f"sensitive memory value is forbidden: {path}")
            if detect_injection_signals(value).detected:
                raise MemoryPolicyError(f"instruction-like memory value is forbidden: {path}")
