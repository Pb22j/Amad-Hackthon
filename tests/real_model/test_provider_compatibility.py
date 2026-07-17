import os

import pytest

from agentic.llm.factory import ModelFactory


@pytest.mark.real_model
@pytest.mark.asyncio
async def test_configured_primary_model_supports_structured_output_and_async(app_config):
    if os.getenv("RUN_REAL_MODEL_TESTS") != "1":
        pytest.skip("RUN_REAL_MODEL_TESTS=1 is required")
    model = ModelFactory(app_config.llm).create("primary")
    from pydantic import BaseModel

    class Probe(BaseModel):
        ok: bool

    result = await model.with_structured_output(Probe, method="function_calling").ainvoke(
        "Return ok=true as structured output."
    )
    assert result.ok is True
