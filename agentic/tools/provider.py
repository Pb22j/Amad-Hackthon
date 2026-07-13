from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool

from agentic.tools.metadata import ToolMetadata


@dataclass(frozen=True, slots=True)
class ToolBundle:
    tools: tuple[BaseTool, ...]
    metadata: tuple[ToolMetadata, ...]


def load_tool_bundle(
    provider_spec: str | None,
    configured_metadata: dict[str, dict[str, Any]],
) -> ToolBundle:
    if not provider_spec:
        return ToolBundle((), ())
    try:
        module_name, attribute_name = provider_spec.split(":", 1)
        provider = getattr(importlib.import_module(module_name), attribute_name)
    except (ValueError, ImportError, AttributeError) as exc:
        raise RuntimeError(f"cannot load tool provider: {provider_spec}") from exc
    if not callable(provider):
        raise TypeError("tool provider must be callable")
    supplied = provider()
    if isinstance(supplied, ToolBundle):
        bundle = supplied
    elif (
        isinstance(supplied, tuple)
        and len(supplied) == 2
        and isinstance(supplied[0], Sequence)
        and isinstance(supplied[1], Sequence)
    ):
        bundle = ToolBundle(tuple(supplied[0]), tuple(supplied[1]))
    elif isinstance(supplied, Sequence):
        tools = tuple(supplied)
        metadata = tuple(
            ToolMetadata(name=tool.name, **configured_metadata.get(tool.name, {}))
            for tool in tools
        )
        bundle = ToolBundle(tools, metadata)
    else:
        raise TypeError("tool provider must return ToolBundle, (tools, metadata), or tools")
    if not all(isinstance(tool, BaseTool) for tool in bundle.tools):
        raise TypeError("tool provider returned a non-LangChain tool")
    if not all(isinstance(item, ToolMetadata) for item in bundle.metadata):
        raise TypeError("tool provider returned invalid metadata")
    return bundle
