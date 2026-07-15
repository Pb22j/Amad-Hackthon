# Codebase Guide

This guide explains how the financial agent is assembled, how a request moves through it, and
where to make common changes. The implementation deliberately separates model reasoning from
security decisions: the model chooses among available capabilities, while deterministic Python
code owns identity, authorization, confirmation, isolation, persistence, and reporting rules.

## Package map

| Path | Responsibility |
|---|---|
| `main.py` | ASGI entry point; exports the FastAPI application. |
| `agentic/api/` | Signed HTTP boundary and request/response schemas. |
| `agentic/agent/graph.py` | Deterministic outer LangGraph and bounded inner LangChain agent. |
| `agentic/agent/service.py` | Task lifecycle, persistence, pause/resume, memory, events, and reports. |
| `agentic/tools/provider.py` | Discovers and normalizes the teammate-owned list of tools. |
| `agentic/tools/registry.py` | Verifies one-to-one matching between tools and security metadata. |
| `agentic/tools/guard.py` | Wraps every tool with authorization, confirmation, audit, and validation. |
| `agentic/policy/` | Request screening, intent risk, output policy, and injection signals. |
| `agentic/memory/` | Curated-memory extraction, allowlisting, retrieval, and deletion. |
| `agentic/persistence/` | SQLAlchemy models, repositories, encryption types, and LangGraph storage. |
| `agentic/config/` | Strict YAML configuration for models, limits, policies, service, and tools. |
| `agentic/telemetry/` | Safe events, redacted logs, and Prometheus metrics. |
| `agentic/evals/` | Deterministic security datasets and mutation-test release gate. |
| `tests/` | Unit, integration, end-to-end, security, PostgreSQL, and live-model tests. |

## Request lifecycle

1. The interaction layer sends an authenticated `AgenticRequest` to `POST /agentic/request`.
2. The API verifies the HMAC signature. Identity, tenant, session, and scopes come from this signed
   envelope; they are never inferred from natural language.
3. `AgentService.submit()` enforces request and concurrency limits, redacts prohibited secrets,
   creates an idempotent task row, and returns an acceptance response. Reusing a request ID is
   accepted only when the complete logical request fingerprint and identity tuple match.
4. The service loads only memory matching the authenticated tenant and user.
5. The outer graph screens prohibited requests and uses a structured-output model to classify
   intent and risk.
6. Unknown or low-confidence requests route to a tool-free support responder. It receives the
   runtime capability catalog as untrusted context and returns clear guidance without inventing
   data or exposing internal architecture. A deterministic localized fallback remains available if
   that response model fails.
7. The bounded inner agent sees only tools registered for this deployment. LangChain middleware
   enforces model-call, tool-call, clarification, and per-tool limits.
8. Every external tool has already been replaced with a guarded wrapper. The wrapper checks trusted
   scopes, exact confirmation, idempotency, ownership, receipts, output size, and safe retries.
9. Missing information or confirmation produces a LangGraph interrupt. The service persists the
   state transition and outbound event in one transaction. A background outbox worker retries
   signed webhook delivery in task order until the interaction layer acknowledges it.
10. `POST /agentic/tasks/{task_id}/resume` verifies the same task/user/tenant/session relationship and
   resumes with a clarification answer or the exact authorization token plus dedicated demo OTP.
11. The final `AgentReport` is validated against authoritative tool executions before it is stored
    and emitted. It includes typed `interaction_context` containing the understood goal, safe key
    facts, and suggested next steps. A financial action cannot be reported as completed without its
    receipt.

## Tool integration

`agentic/tools` now exports PostgreSQL-backed demo tools for accounts, transactions, beneficiaries,
transfers, reports, financial analysis, gifts, bills, Qatta, and investments. The guard binds the
authenticated user and tenant with a request-scoped context, including across database worker threads.
The older in-memory provider remains available through an explicit `AGENTIC_TOOL_PROVIDER` override.

An Open Banking provider can replace the default without changing orchestration:

```python
# agentic/tools/__init__.py
from .accounts import get_balance
from .transfers import transfer_funds

TOOLS = [get_balance, transfer_funds]
```

Each item must be a LangChain `BaseTool` with a stable unique name, a useful description, and a
strict Pydantic argument schema. The description tells the model when to use the capability; the
argument schema limits what the model can propose.

Security metadata belongs at the agent boundary and must be defined in
`agentic/config/tools.yaml` when the package exports only a list:

```yaml
tools:
  get_balance:
    risk: sensitive_read
    intents: [account_information]
    required_scopes: [financial:read]
    requires_owner_metadata: true
    max_calls_per_task: 3
  transfer_funds:
    risk: financial_action
    intents: [money_transfer]
    required_scopes: [financial:write]
    requires_confirmation: true
    requires_receipt: true
    requires_owner_metadata: true
    idempotent: true
    max_calls_per_task: 2
```

The package may instead export `tools`, `get_tools()`, or `get_tool_bundle()`. A `ToolBundle` carries
both the list and `ToolMetadata`. `AGENTIC_TOOL_PROVIDER=package.module:attribute` overrides default
discovery for deployments that keep tools in another package.

Startup rejects duplicate names, missing metadata, extra metadata, non-LangChain values, tools
without Pydantic schemas, and empty production tool lists. These checks ensure the model's available
functionalities are exactly the tools supplied by the tool team—there is no hard-coded capability
list in the agent.

Intent metadata additionally filters the tools attached to each model call. Broad authenticated
scopes do not justify unrelated data access: for example, a portfolio request cannot call the
balance tool when only `get_portfolio` declares the classified investment-research intent.

See `docs/TOOL_CONTRACT.md` for the required result envelope. In particular, results that contain
user data must identify their user and tenant, and completed financial actions must supply a receipt
when their metadata requires one.

## Security invariants

- Natural-language text cannot grant identity or permissions.
- Prompt-injection detection is defense-in-depth telemetry, not the authorization boundary.
- Tool and memory content is untrusted even when it came from an internal system.
- Another user's or tenant's result is rejected before it reaches the model.
- Exact confirmation binds user, tenant, task, tool name, normalized arguments, expiry, and nonce.
- Every financial action also requires the dedicated OTP; the fixed `1111` value is demo-only and
  never enters model, graph, tool, memory, or audit context.
- A consumed confirmation cannot be replayed and cannot authorize modified arguments.
- Financial writes are not blindly retried; idempotency keys prevent duplicate execution.
- Completed configured actions require authoritative receipts.
- Sensitive application columns and LangGraph checkpoints use separate encryption keys.
- Logs, stored tool arguments, and user-visible reports are redacted and size-limited.

## Configuration

- `llm.yaml`: role-specific providers, model names, fallbacks, timeouts, and cost estimates.
- `agent.yaml`: service environment, database pool, tool-provider override, and API behavior.
- `limits.yaml`: task budgets, retries, retention, report size, and rate limits.
- `policies.yaml`: prohibited intents, memory allowlists, and confirmation/receipt rules.
- `tools.yaml`: per-tool security metadata when the tools package exports a plain list.

All files are parsed into frozen Pydantic models with unknown fields forbidden. Production also
requires checkpoint encryption and an interaction-event webhook. Secret values come from the
environment and are excluded from the configuration hash and logs.

## Persistence and memory

Application tables track tasks, events, clarification requests, exact authorizations, executions,
curated memories, audit decisions, and evaluation runs. Alembic owns these tables. LangGraph owns
its checkpoint and store tables, which Alembic intentionally ignores.

Working memory is the encrypted task checkpoint. Curated memory is not a raw transcript: the
extractor proposes small candidates, deterministic policy rejects secrets/instructions/unsupported
types, and the service stores provenance, confidence, consent, expiry, and verification state.
Every query includes the exact tenant, user, and interaction session. Compaction never asks a model
to rewrite facts: it removes expired data and lower-ranked unverified overflow while preserving all
verified items. `DELETE /agentic/memory` removes only the authenticated session's curated memory.

## Models

`ModelFactory` is the only place that knows provider SDK details. Code asks for semantic roles such
as `primary`, `intent_classifier`, or `memory_extractor`. Changing a provider or model normally
requires only `llm.yaml`. Required capability checks fail early when a provider cannot satisfy a
role. Configured primary fallbacks are installed as LangChain middleware.

## Testing changes

Run the normal release gate:

```bash
pytest --cov=agentic --cov-branch --cov-fail-under=95
ruff check .
amad-agent eval-security
```

When PostgreSQL is available, also run migrations, LangGraph setup, schema-drift detection, and
`tests/postgres`. Changes to confirmation, identity, redaction, or output policy must pass the
mutation gate. New tool categories should add contract tests, one end-to-end happy path, ownership
and scope failures, confirmation mutation/replay cases when relevant, and malformed-result cases.

## Common extension points

- Add functionality: export another tool from `agentic/tools/` and add matching security metadata.
- Change models: edit `agentic/config/llm.yaml`; orchestration code should not import provider SDKs.
- Change limits: edit `limits.yaml` and add boundary tests.
- Add remembered data: extend the memory allowlist and tests before changing extraction prompts.
- Add a task state: update the enum, repository transition table, service handling, events, and tests.
- Add a financial action: require explicit scopes, exact confirmation where appropriate,
  idempotency, an authoritative receipt, and end-to-end reconciliation tests.
