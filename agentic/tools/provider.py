"""Discovery and normalization of the teammate-owned financial tool list.

By default the service imports the :mod:`agentic.tools` package. That
package can expose ``TOOLS``/``tools`` or ``get_tools()``.  Deployments may
override discovery with ``AGENTIC_TOOL_PROVIDER=package.module:function``.
Every accepted shape is normalized into :class:`ToolBundle` before the agent is
built, keeping provider-specific code outside the orchestration layer.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool

from agentic.tools.metadata import ToolMetadata


@dataclass(frozen=True, slots=True)
class ToolBundle:
    """Immutable collection of callable tools and their security metadata."""

    tools: tuple[BaseTool, ...]
    metadata: tuple[ToolMetadata, ...]


def _import_provider(provider_spec: str) -> Any:
    """Import an explicit ``module:attribute`` provider with a safe error."""

    try:
        module_name, attribute_name = provider_spec.split(":", 1)
        return getattr(importlib.import_module(module_name), attribute_name)
    except (ValueError, ImportError, AttributeError) as exc:
        raise RuntimeError(f"cannot load tool provider: {provider_spec}") from exc


def _discover_tools_package() -> Any:
    """Return the conventional :mod:`agentic.tools` export.

    ``TOOLS`` is preferred because it is visually distinct from the package
    name.  Callable factories are also supported when tool construction needs
    dependencies or setup.  An import error *inside* the tools package is not
    swallowed because that would hide a broken financial integration.
    """

    # This package is part of the application, so an import failure is a broken
    # deployment and must propagate instead of being treated as "no tools".
    module = importlib.import_module("agentic.tools")

    for attribute_name in ("get_tool_bundle", "get_tools", "TOOLS", "tools"):
        if hasattr(module, attribute_name):
            return getattr(module, attribute_name)
    raise RuntimeError(
        "agentic.tools must export TOOLS, tools, get_tools(), or get_tool_bundle()"
    )


def _configured_bundle(
    supplied: Any,
    configured_metadata: dict[str, dict[str, Any]],
) -> ToolBundle:
    """Normalize a supported provider return value and validate its contents."""

    # Factories make it possible for the tools team to construct clients lazily.
    if callable(supplied) and not isinstance(supplied, BaseTool):
        supplied = supplied()
    if isinstance(supplied, ToolBundle):
        bundle = supplied
    elif (
        isinstance(supplied, tuple)
        and len(supplied) == 2
        and isinstance(supplied[0], Sequence)
        and isinstance(supplied[1], Sequence)
    ):
        bundle = ToolBundle(tuple(supplied[0]), tuple(supplied[1]))
    elif isinstance(supplied, Sequence) and not isinstance(supplied, (str, bytes)):
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


def load_tool_bundle(
    provider_spec: str | None,
    configured_metadata: dict[str, dict[str, Any]],
    *,
    require_tools: bool = False,
) -> ToolBundle:
    """Load tools from an override provider or :mod:`agentic.tools`.

    Args:
        provider_spec: Optional ``module:attribute`` override. The attribute may
            be a callable or one of the supported bundle/list values.
        configured_metadata: Security metadata keyed by stable tool name.
        require_tools: Fail when discovery produces no tools. Production sets
            this to ``True`` so a misconfigured deployment cannot start with no
            financial functionality.
    """

    supplied = (
        _import_provider(provider_spec)
        if provider_spec
        else _discover_tools_package()
    )
    bundle = _configured_bundle(supplied, configured_metadata)
    if require_tools and not bundle.tools:
        raise RuntimeError("the financial tool list is empty")
    return bundle
