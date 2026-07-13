from prometheus_client import Counter, Histogram


TASKS = Counter(
    "amad_agent_tasks_total",
    "Financial agent tasks by outcome",
    labelnames=("outcome", "language"),
)
TOOL_CALLS = Counter(
    "amad_agent_tool_calls_total",
    "Guarded tool calls by tool and outcome",
    labelnames=("tool", "outcome"),
)
SECURITY_DECISIONS = Counter(
    "amad_agent_security_decisions_total",
    "Security policy decisions",
    labelnames=("decision", "reason"),
)
TASK_DURATION = Histogram(
    "amad_agent_task_duration_seconds",
    "Agent task runtime in seconds",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 180),
)
TOOL_DURATION = Histogram(
    "amad_agent_tool_duration_seconds",
    "Guarded tool runtime in seconds",
    labelnames=("tool",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
MODEL_TOKENS = Counter(
    "amad_agent_model_tokens_total",
    "Model tokens by provider, model, and direction",
    labelnames=("provider", "model", "direction"),
)
MODEL_ESTIMATED_COST = Counter(
    "amad_agent_model_estimated_cost_total",
    "Estimated model cost in configured billing currency",
    labelnames=("provider", "model"),
)
