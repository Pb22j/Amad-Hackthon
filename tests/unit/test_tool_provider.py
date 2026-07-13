import sys
import types

import pytest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from agentic.tools.metadata import ToolMetadata, ToolRisk
from agentic.tools.provider import ToolBundle, load_tool_bundle


class Args(BaseModel):
    value: str


async def operation(value: str):
    return value


def tool():
    return StructuredTool.from_function(
        coroutine=operation, name="operation", description="operation", args_schema=Args
    )


def install_provider(monkeypatch, result):
    module = types.ModuleType("test_tool_provider_module")
    module.provide = lambda: result
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return f"{module.__name__}:provide"


def test_empty_provider_is_valid_for_tests_and_development():
    assert load_tool_bundle(None, {}) == ToolBundle((), ())


def test_provider_can_return_bundle(monkeypatch):
    item = tool()
    metadata = ToolMetadata(name="operation", risk=ToolRisk.READ)
    spec = install_provider(monkeypatch, ToolBundle((item,), (metadata,)))
    assert load_tool_bundle(spec, {}).metadata == (metadata,)


def test_provider_can_return_tuple(monkeypatch):
    item = tool()
    metadata = ToolMetadata(name="operation", risk=ToolRisk.READ)
    spec = install_provider(monkeypatch, ([item], [metadata]))
    assert load_tool_bundle(spec, {}).tools == (item,)


def test_provider_can_use_configured_metadata(monkeypatch):
    item = tool()
    spec = install_provider(monkeypatch, [item])
    bundle = load_tool_bundle(
        spec,
        {
            "operation": {
                "risk": "read",
                "required_scopes": ["financial:read"],
            }
        },
    )
    assert bundle.metadata[0].required_scopes == frozenset({"financial:read"})


def test_invalid_provider_is_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="cannot load"):
        load_tool_bundle("missing.module:provider", {})
    spec = install_provider(monkeypatch, object())
    with pytest.raises(TypeError, match="must return"):
        load_tool_bundle(spec, {})


def test_provider_rejects_non_callable_and_invalid_contents(monkeypatch):
    module = types.ModuleType("invalid_tool_provider_module")
    module.not_callable = 1
    monkeypatch.setitem(sys.modules, module.__name__, module)
    with pytest.raises(TypeError, match="callable"):
        load_tool_bundle(f"{module.__name__}:not_callable", {})
    spec = install_provider(monkeypatch, [object()])
    with pytest.raises((TypeError, AttributeError)):
        load_tool_bundle(spec, {})
    spec = install_provider(monkeypatch, ToolBundle((tool(),), (object(),)))
    with pytest.raises(TypeError, match="invalid metadata"):
        load_tool_bundle(spec, {})
    spec = install_provider(monkeypatch, ToolBundle((object(),), ()))
    with pytest.raises(TypeError, match="non-LangChain"):
        load_tool_bundle(spec, {})
