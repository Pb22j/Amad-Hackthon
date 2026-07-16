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


def test_empty_provider_is_valid_for_tests_and_development(monkeypatch):
    module = types.ModuleType("agentic.tools")
    module.TOOLS = []
    monkeypatch.setitem(sys.modules, "agentic.tools", module)
    assert load_tool_bundle(None, {}) == ToolBundle((), ())


@pytest.mark.parametrize("export_name", ["TOOLS", "tools", "get_tools", "get_tool_bundle"])
def test_default_tools_package_exports_are_discovered(monkeypatch, export_name):
    item = tool()
    module = types.ModuleType("agentic.tools")
    exported = [item]
    setattr(module, export_name, (lambda: exported) if export_name.startswith("get_") else exported)
    monkeypatch.setitem(sys.modules, "agentic.tools", module)

    bundle = load_tool_bundle(None, {"operation": {"risk": "read"}})

    assert bundle.tools == (item,)
    assert bundle.metadata[0].risk == ToolRisk.READ


def test_default_tools_package_must_have_a_supported_export(monkeypatch):
    monkeypatch.setitem(sys.modules, "agentic.tools", types.ModuleType("agentic.tools"))
    with pytest.raises(RuntimeError, match="must export"):
        load_tool_bundle(None, {})


def test_production_requires_a_non_empty_tool_list(monkeypatch):
    module = types.ModuleType("agentic.tools")
    module.TOOLS = []
    monkeypatch.setitem(sys.modules, "agentic.tools", module)
    with pytest.raises(RuntimeError, match="list is empty"):
        load_tool_bundle(None, {}, require_tools=True)


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
    with pytest.raises(TypeError, match="must return"):
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
