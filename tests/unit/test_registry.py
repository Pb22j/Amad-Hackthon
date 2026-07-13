import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from agentic.tools.guard import GuardedToolFactory
from agentic.tools.metadata import ToolMetadata, ToolRisk
from agentic.tools.registry import ToolRegistry


class Args(BaseModel):
    value: str


async def operation(value: str):
    return value


def make_tool(name="operation"):
    return StructuredTool.from_function(
        coroutine=operation, name=name, description="operation", args_schema=Args
    )


def test_registry_rejects_missing_and_unknown_metadata():
    with pytest.raises(ValueError, match="mismatch"):
        ToolRegistry([make_tool()], [])
    with pytest.raises(ValueError, match="mismatch"):
        ToolRegistry([], [ToolMetadata(name="operation", risk=ToolRisk.READ)])


def test_registry_rejects_duplicate_tools_and_metadata():
    tool = make_tool()
    metadata = ToolMetadata(name="operation", risk=ToolRisk.READ)
    with pytest.raises(ValueError, match="duplicate external"):
        ToolRegistry([tool, tool], [metadata])
    with pytest.raises(ValueError, match="duplicate tool metadata"):
        ToolRegistry([tool], [metadata, metadata])


def test_registry_exposes_metadata_and_entries():
    metadata = ToolMetadata(name="operation", risk=ToolRisk.READ)
    registry = ToolRegistry([make_tool()], [metadata])
    assert registry.entries()[0][1] == metadata
    assert registry.metadata("operation") == metadata


def test_guard_rejects_metadata_name_mismatch_and_missing_schema():
    factory = GuardedToolFactory()
    with pytest.raises(ValueError, match="must match"):
        factory.wrap(make_tool(), ToolMetadata(name="other", risk=ToolRisk.READ))
    tool = make_tool()
    tool.args_schema = None
    with pytest.raises(ValueError, match="must declare"):
        factory.wrap(tool, ToolMetadata(name="operation", risk=ToolRisk.READ))
    tool = make_tool()
    tool.args_schema = {"type": "object"}
    with pytest.raises(ValueError, match="Pydantic"):
        factory.wrap(tool, ToolMetadata(name="operation", risk=ToolRisk.READ))
