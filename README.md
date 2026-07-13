# Amad Financial Agent

Secure LangChain/LangGraph agentic layer for authenticated financial requests.

The implementation plan is in [AGENTIC_IMPLEMENTATION_PLAN.md](AGENTIC_IMPLEMENTATION_PLAN.md).
For a guided tour of the packages, request lifecycle, trust boundaries, and extension points, see
[docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md).
The integration contract for the user-facing service is in
[docs/INTERACTION_LAYER_CONTRACT.md](docs/INTERACTION_LAYER_CONTRACT.md).

## Local setup

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

Set the environment variables in `.env`, start PostgreSQL, run both database setup commands,
and then start the API:

```bash
docker compose up -d postgres
DATABASE_URL="$DATABASE_URL" .venv/bin/alembic upgrade head
.venv/bin/amad-agent setup-langgraph
.venv/bin/uvicorn main:app --reload --env-file .env
```

Run retention cleanup from a scheduled job:

```bash
.venv/bin/amad-agent cleanup-retention
```

The interaction endpoints are:

- `POST /agentic/request`
- `POST /agentic/tasks/{task_id}/resume`
- `DELETE /agentic/memory`
- `GET /health`
- `GET /metrics/`

Requests must be signed by the interaction layer unless disabled in development configuration.
Model providers, role-specific models, fallbacks, and estimated token prices are editable in
`agentic/config/llm.yaml`; operational limits and financial policies are kept in the other YAML
files in that directory.

For one-query sandbox evaluation before the interaction layer is available, start the API and use
the standalone HTTP client:

```python
from evaluation.task import run_agent

report = run_agent("Show my current checking account balance.")
```

Copy `evaluation/task.py` and `evaluation/.env.example` into any separate folder, rename the latter
to `.env`, and use the same interaction and confirmation secrets as the running API. The file uses
only Python's standard library and imports no agent code. It can also run directly as
`python task.py "Show my balance"`. A signed status-polling endpoint supports this client only in
non-production environments. Sandbox confirmations are auto-signed; missing required information
returns `needs_input` instead of inventing a value.

## Tool integration

The repository currently exports deterministic in-memory sandbox tools from
`agentic/tools/dummy.py`. They never contact a financial provider and reset when the process
restarts. Their result ownership defaults to `evaluation-user` / `evaluation-tenant`; local signed
requests must use those identities or set `DUMMY_TOOL_USER_ID` and `DUMMY_TOOL_TENANT_ID`.

When the teammates' tools are ready, replace the sandbox list in
`agentic/tools/__init__.py` and the agent will discover it without changing orchestration code:

```python
TOOLS = [get_balance, transfer_funds, buy_investment]
```

Supported exports are `TOOLS`, `tools`, `get_tools()`, and `get_tool_bundle()`. To load a different
package, configure an explicit provider:

```text
AGENTIC_TOOL_PROVIDER=your_package.tools:get_financial_tools
```

The export may return a `ToolBundle`, `(tools, metadata)`, or a sequence of LangChain tools whose
security metadata is defined in `agentic/config/tools.yaml`. Production startup fails when the tool
list is missing or empty.

See [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md) for the required schemas and result envelope.

## Tests

```bash
.venv/bin/pytest --cov=agentic --cov-branch --cov-fail-under=95
.venv/bin/ruff check .
.venv/bin/amad-agent eval-security
```

PostgreSQL integration tests are enabled with:

```bash
TEST_POSTGRES_URL=postgresql://localhost:5432/amad .venv/bin/pytest tests/postgres
```

With PostgreSQL running and a real provider key configured in `.env`, run the opt-in provider and
end-to-end dummy-tool evaluations with:

```bash
set -a
source .env
set +a
RUN_REAL_MODEL_TESTS=1 .venv/bin/pytest tests/real_model/test_provider_compatibility.py
RUN_LIVE_AGENT_TESTS=1 .venv/bin/pytest tests/real_model/test_live_dummy_workflows.py
```

The live workflow suite exercises reads, every dummy financial action, Arabic input, signed
clarification and exact confirmation, cross-user rejection, authoritative receipts, and the signed
FastAPI background-processing boundary. It consumes real model-provider credits.

Deployment and security procedures are documented in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
and [docs/SECURITY.md](docs/SECURITY.md).
