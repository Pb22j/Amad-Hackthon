from langchain_core.messages import AIMessage

from agentic.middleware.model_usage import ModelUsageMiddleware


def test_model_usage_middleware_handles_usage_and_empty_state(app_config):
    config = app_config.llm.models["primary"].model_copy(
        update={"input_cost_per_million": 1, "output_cost_per_million": 2}
    )
    middleware = ModelUsageMiddleware(config)
    assert middleware.after_model({"messages": []}, None) is None
    message = AIMessage(
        content="done",
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )
    assert middleware.after_model({"messages": [message]}, None) is None
