# Amad Financial Agent

Secure LangChain/LangGraph agentic layer for authenticated financial requests.

The implementation plan is in [AGENTIC_IMPLEMENTATION_PLAN.md](AGENTIC_IMPLEMENTATION_PLAN.md).

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

## Tool integration

The financial tools remain in the teammates' package. Configure their provider without changing
the agent code:

```text
AGENTIC_TOOL_PROVIDER=your_package.tools:get_financial_tools
```

The callable may return a `ToolBundle`, `(tools, metadata)`, or a sequence of LangChain tools whose
security metadata is defined in `agentic/config/tools.yaml`. Production startup fails when no tool
provider is configured.

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

Deployment and security procedures are documented in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
and [docs/SECURITY.md](docs/SECURITY.md).
