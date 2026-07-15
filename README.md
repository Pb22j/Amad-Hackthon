# Amad Financial Agent

Secure LangChain/LangGraph agentic layer for authenticated financial requests.

The implementation plan is in [AGENTIC_IMPLEMENTATION_PLAN.md](AGENTIC_IMPLEMENTATION_PLAN.md).
For a guided tour of the packages, request lifecycle, trust boundaries, and extension points, see
[docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md).
The integration contract for the user-facing service is in
[docs/INTERACTION_LAYER_CONTRACT.md](docs/INTERACTION_LAYER_CONTRACT.md).
The active/legacy boundaries and service ownership are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Local setup

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.backend.example .env.backend
cp .env.frontend.example .env.local
```

Fill `.env.backend` once for both Python services and `.env.local` once for the Next.js frontend.
Then start PostgreSQL, migrate and seed it from the bundled CSV demo data, initialize LangGraph,
and start the agentic API:

```bash
docker compose up -d postgres
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_postgres.py
.venv/bin/amad-agent setup-langgraph
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 9000
```

## Integrated web app

The merged Next.js frontend lives at the repository root. It connects to the Nafea interaction
service on port `8001`, which in turn calls the agentic API on port `9000`. Both Python services
load the same root `.env.backend`, so shared secrets, identity, and database URLs cannot drift.

After the database setup above, run the three processes in separate terminals:

```bash
# Agentic service
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 9000

# Authenticated interaction/voice service
cd VoiceAssistant_Nafea/backend
PYTHONPATH=. ../../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# Next.js frontend (from the repository root)
npm ci
npm run dev
```

Open `http://localhost:3000`. The browser creates an HttpOnly demo session, receives correlated
task events over `/api/ws`, and uses the backend `/api/realtime` proxy for live voice. Next.js reads
only `.env.local`; update its `NEXT_PUBLIC_NAFEA_API_URL` before a hosted build.

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

The evaluator uses `AGENTIC_BASE_URL`, `INTERACTION_SHARED_SECRET`, and
`CONFIRMATION_SIGNING_KEY` from the shared `.env.backend` environment. The file uses only Python's
standard library and imports no agent code. Load the shared file before running it directly:

```bash
set -a && source .env.backend && set +a
python evaluation/task.py "Show my balance"
```

A signed status-polling endpoint supports this client only in
non-production environments. Sandbox confirmations are auto-signed and use demo OTP `1111`; missing required information
returns `needs_input` instead of inventing a value.

## Tool integration

The default package exports PostgreSQL-backed demo banking tools for balances, transaction search,
beneficiaries, transfers, reports, Qatta, gifts, bill payments, financial analysis, and investment
portfolio/trades. Guarded calls inject user and tenant identity from the authenticated task; the
model cannot select identity. Direct local tool calls can use the `BANK_TOOL_*` fallback variables.

The deterministic in-memory tools in `agentic/tools/dummy.py` remain available for isolated tests:

```text
AGENTIC_TOOL_PROVIDER=agentic.tools.dummy:DUMMY_TOOLS
```

Supported exports are `TOOLS`, `tools`, `get_tools()`, and `get_tool_bundle()`. To load a different
package, configure an explicit provider:

```text
AGENTIC_TOOL_PROVIDER=your_package.tools:get_financial_tools
```

Every configured write or financial action requires exact signed confirmation plus the fixed demo
OTP `1111`; OTP input is accepted only by the confirmation endpoint and never enters model context.

The export may return a `ToolBundle`, `(tools, metadata)`, or a sequence of LangChain tools whose
security metadata is defined in `agentic/config/tools.yaml`. Production startup fails when the tool
list is missing or empty.

See [docs/TOOL_CONTRACT.md](docs/TOOL_CONTRACT.md) for the required schemas and result envelope.
The unified customer, banking, interaction, and agent data model is documented in
[docs/DATA_MODEL.md](docs/DATA_MODEL.md).

## Tests

```bash
.venv/bin/pytest --cov=agentic --cov-branch --cov-fail-under=95
.venv/bin/ruff check .
.venv/bin/amad-agent eval-security
```

PostgreSQL integration tests are enabled with:

```bash
TEST_POSTGRES_URL=postgresql://amad:development-only-password@localhost:55432/amad \
  .venv/bin/pytest tests/postgres
```

With PostgreSQL running and real provider keys configured in `.env.backend`, run the opt-in provider and
end-to-end dummy-tool evaluations with:

```bash
set -a
source .env.backend
set +a
RUN_REAL_MODEL_TESTS=1 .venv/bin/pytest tests/real_model/test_provider_compatibility.py
RUN_LIVE_AGENT_TESTS=1 .venv/bin/pytest tests/real_model/test_live_dummy_workflows.py
```

The live workflow suite exercises reads, every dummy financial action, Arabic input, signed
clarification and exact confirmation, cross-user rejection, authoritative receipts, and the signed
FastAPI background-processing boundary. It consumes real model-provider credits.

Deployment and security procedures are documented in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
and [docs/SECURITY.md](docs/SECURITY.md).
