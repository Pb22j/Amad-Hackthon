# Deployment

## Required services

- Python 3.12 or 3.13.
- PostgreSQL 16.
- An interaction-layer webhook endpoint.
- A configured LLM provider and a non-empty `agentic.tools` list (or provider override).

## Database setup

Run application and LangGraph migrations separately:

```bash
alembic upgrade head
amad-agent setup-langgraph
alembic check
```

Application migrations intentionally ignore LangGraph-owned `checkpoints`, `checkpoint_blobs`,
`checkpoint_writes`, `store`, and migration tables. Never add those tables to an Alembic revision.

Use distinct runtime, migration, audit-reader, and backup database roles in production. Grant the
runtime role only the DML and sequence permissions it needs. Encrypt database storage and backups.

## Required production configuration

- `DATABASE_URL`
- `LANGGRAPH_DATABASE_URL`
- `CONFIRMATION_SIGNING_KEY` with at least 32 random bytes
- `CHECKPOINT_ENCRYPTION_KEY` with exactly 16, 24, or 32 random bytes
- `APP_DATA_ENCRYPTION_KEY` with at least 32 random bytes, separate from checkpoint encryption
- `INTERACTION_SHARED_SECRET` with at least 32 random bytes
- `INTERACTION_EVENT_WEBHOOK_URL`
- `AGENTIC_TOOL_PROVIDER` only when tools are not exported by `agentic.tools`
- The API key for every configured model provider

Production startup rejects missing checkpoint encryption, webhook, or tool-provider configuration.
Rotate signing keys using a planned dual-key window; do not invalidate active confirmations without
notifying the interaction layer.

Model roles, providers, fallbacks, and cost estimates are configured in `agentic/config/llm.yaml`.
Limits, financial-action policies, service settings, and tool metadata live in the neighboring YAML
files and are strictly validated at startup.

## Verification

```bash
pytest --cov=agentic --cov-branch --cov-fail-under=95
TEST_POSTGRES_URL="$LANGGRAPH_DATABASE_URL" pytest tests/postgres
ruff check .
pip check
amad-agent eval-security
mutmut run
mutmut results
python -m agentic.evals.mutation_gate --minimum 0.70
docker compose config --quiet
```

The PostgreSQL suite verifies encrypted checkpoint interruption/resumption, store isolation, and
concurrent request/tool idempotency. The normal suite uses deterministic fake models; real-provider
compatibility should run as a protected nightly job with the relevant API keys.

## Rollback

Application migrations include a downgrade for development verification. Production rollback
should normally deploy the previous compatible application while retaining data. Do not downgrade
or delete LangGraph tables during incident recovery. Restore backups into an isolated database and
run integrity checks before switching traffic.
