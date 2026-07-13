from __future__ import annotations

import pytest

from agentic.memory.extraction import LLMMemoryExtractor, MemoryCandidate, MemoryCandidateBatch


class ExtractionRunnable:
    def __init__(self, result):
        self.result = result

    async def ainvoke(self, _):
        return self.result


class ExtractionModel:
    def __init__(self, result):
        self.result = result

    def with_structured_output(self, _):
        return ExtractionRunnable(self.result)


@pytest.mark.asyncio
async def test_memory_extractor_requires_exact_direct_quote():
    model = ExtractionModel(
        MemoryCandidateBatch(
            candidates=[
                MemoryCandidate(
                    memory_type="reporting_currency",
                    value={"currency": "SAR"},
                    direct_quote="Use SAR for all reports",
                    confidence=1,
                ),
                MemoryCandidate(
                    memory_type="report_format",
                    value={"format": "short"},
                    direct_quote="hallucinated quote",
                    confidence=0.9,
                ),
            ]
        )
    )
    candidates = await LLMMemoryExtractor(model).extract("Use SAR for all reports")
    assert [item.memory_type for item in candidates] == ["reporting_currency"]
