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

After the database setup above, start the complete development stack from the repository root:

```bash
npm ci
npm run dev
```

This launches the agentic service on `9000`, the interaction/voice service on `8001`, and Next.js
on `3000`, and stops the stack if any required service exits. For frontend-only work while the
Python services are already running, use `npm run dev:web`.

Open `http://localhost:3000`. The browser creates an HttpOnly demo session, receives correlated
task events over `/api/ws`, and uses the backend `/api/realtime` proxy for live voice. Next.js reads
only `.env.local`; update its `NEXT_PUBLIC_NAFEA_API_URL` before a hosted build. The dashboard reads
the authenticated customer's current accounts, portfolio, transactions, bills, and beneficiaries
from the interaction service's read-only `/api/dashboard` projection over the shared PostgreSQL
database.

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

## Security screening evaluation

`amad-agent eval-security` runs a 100-scenario bilingual adversarial dataset
(`agentic/evals/datasets/security.jsonl`) against `PolicyEngine.screen_request`. It is
deterministic, needs no model provider, and covers ten categories across Arabic and English:
benign reads and actions, benign text containing trigger words, prompt injection, credential
extraction, cross-user access, obfuscated injection, authority manipulation, tool-argument
injection, and bulk exfiltration.

Cases are labelled with the outcome the policy is *intended* to produce, not the outcome the
current detector produces, so the dataset is free to disagree with the implementation. A case
the detector cannot yet satisfy carries a `known_gap` reason and, where the attempt is stopped
by a deeper layer, a `mitigation` note. The run reports gaps but only fails on an
*undocumented* mismatch — or on a `known_gap` case that starts passing, which means the marker
is stale and should be deleted.

```bash
.venv/bin/amad-agent eval-security --json      # full machine-readable report
.venv/bin/amad-agent eval-security --dataset holdout  # strict fresh cases; no gap exemptions
.venv/bin/amad-agent eval-security --dataset challenge # second disjoint challenge set
.venv/bin/python scripts/build_eval_report.py  # render outputs/security-eval-report.html
```

The holdout dataset contains 100 prompts that do not occur in the baseline: exactly five
English and five Arabic cases in each category. It has no `known_gap` markers, so use it as
the acceptance target for detector fixes; any mismatch exits non-zero.

The report page is generated from a live run, so its figures cannot drift from the suite's.

## Financial functionality evaluation

The functionality evaluator is independent of security screening. It runs 100 bilingual
workflows against the real agent graph and an in-memory dummy financial ledger, then scores
observable behavior from persisted task state, interaction events, and tool executions. Its
checks cover outcome, intent, risk, exact tool sequence, arguments, clarification, confirmation,
and receipts.

The matrix contains 50 English and 50 Arabic cases: account and transaction reads, portfolio
reads, transfers, bill payments, beneficiary creation, investment purchases, insufficient-share
sales, withdrawals that exceed available cash, and requests that require clarification. It pins
every agent role to MiniMax (MiniMax-M2.7-highspeed by default) and uses PostgreSQL, but no
external bank or broker.

```bash
# Load provider and database settings first.
set -a
source .env.backend
set +a

# One-case smoke test, then the complete 100-case evaluation.
.venv/bin/python scripts/run_functionality_eval.py --limit 1
.venv/bin/python scripts/run_functionality_eval.py
# Optionally select another MiniMax model id.
.venv/bin/python scripts/run_functionality_eval.py --model MiniMax-M2.7
```

The complete machine-readable result is written to
`outputs/functionality-eval-report.json`. Every case is reset to the same dummy ledger state,
and cases run sequentially so one financial action cannot affect another.

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
