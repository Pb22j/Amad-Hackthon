"""Validated one-to-one registry of external tools and security metadata."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.tools import BaseTool

from agentic.tools.metadata import ToolMetadata


class ToolRegistry:
    """Reject ambiguous, duplicate, missing, or unused tool metadata."""

    def __init__(self, tools: Sequence[BaseTool], metadata: Sequence[ToolMetadata]) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._metadata = {item.name: item for item in metadata}
        if len(self._tools) != len(tools):
            raise ValueError("duplicate external tool name")
        if len(self._metadata) != len(metadata):
            raise ValueError("duplicate tool metadata name")
        missing_metadata = self._tools.keys() - self._metadata.keys()
        unknown_metadata = self._metadata.keys() - self._tools.keys()
        if missing_metadata or unknown_metadata:
            raise ValueError(
                f"tool/metadata mismatch; missing={sorted(missing_metadata)}, "
                f"unknown={sorted(unknown_metadata)}"
            )

    def entries(self) -> list[tuple[BaseTool, ToolMetadata]]:
        """Return stable tool/metadata pairs ready for guarded wrapping."""

        return [(tool, self._metadata[name]) for name, tool in self._tools.items()]

    def metadata(self, name: str) -> ToolMetadata:
        return self._metadata[name]
