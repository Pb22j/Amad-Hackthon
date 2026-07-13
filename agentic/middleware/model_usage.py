from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from agentic.config.loader import ModelConfig
from agentic.telemetry.metrics import MODEL_ESTIMATED_COST, MODEL_TOKENS


class ModelUsageMiddleware(AgentMiddleware):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__()
        self.config = config

    def after_model(self, state: dict[str, Any], runtime: Any) -> None:
        del runtime
        if not state.get("messages") or not isinstance(state["messages"][-1], AIMessage):
            return None
        usage = state["messages"][-1].usage_metadata or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        MODEL_TOKENS.labels(
            provider=self.config.provider,
            model=self.config.model,
            direction="input",
        ).inc(input_tokens)
        MODEL_TOKENS.labels(
            provider=self.config.provider,
            model=self.config.model,
            direction="output",
        ).inc(output_tokens)
        estimated_cost = (
            input_tokens * self.config.input_cost_per_million
            + output_tokens * self.config.output_cost_per_million
        ) / 1_000_000
        MODEL_ESTIMATED_COST.labels(
            provider=self.config.provider, model=self.config.model
        ).inc(estimated_cost)
        return None
