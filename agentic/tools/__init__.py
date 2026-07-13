"""Financial tool integration package.

Teammate-owned functionality is exposed through ``TOOLS``. The agent discovers
this list at startup and applies the guarded boundary to every item. Keeping an
empty tuple is convenient for local graph tests; production rejects it.
"""

from agentic.tools.dummy import DUMMY_TOOLS
from agentic.tools.guard import AgentRuntimeContext, GuardedToolFactory
from agentic.tools.metadata import ToolMetadata, ToolResult

TOOLS = DUMMY_TOOLS

__all__ = ["TOOLS", "AgentRuntimeContext", "GuardedToolFactory", "ToolMetadata", "ToolResult"]
