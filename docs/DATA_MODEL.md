# Unified PostgreSQL data model

PostgreSQL 16 is the system of record for customer identity, banking tools, the voice interaction
boundary, agent workflow state, LangGraph checkpoints, audit, memory, and evaluation results.
All services, development harnesses, and tests require PostgreSQL.

## Data domains

| Domain | Tables | Primary consumers |
|---|---|---|
| Application identity | `platform_users` | authentication/bootstrap services |
| Banking customers | `users`, `beneficiaries` | balance, beneficiary, transfer, gift tools |
| Ledger and reporting | `transactions` | transaction search, monthly reports, financial analysis, daily-limit enforcement |
| Shared expenses and bills | `qattas`, `qatta_bills`, `fatoorahs` | Qatta and SADAD-style bill tools |
| Investments | `investment_assets`, `investment_holdings` | portfolio, buy, and sell tools |
| Interaction boundary | `interaction_sessions`, `interaction_requests`, `interaction_tasks`, `interaction_events`, `voice_turns` | voice service authentication, idempotency, webhook correlation, bounded encrypted recall |
| Agent runtime | `agent_tasks`, `task_events`, `event_outbox`, `clarification_requests`, `action_authorizations`, `tool_executions` | guarded agent workflow and reliable event delivery |
| Memory, audit, evaluation | `memory_items`, `audit_events`, `eval_runs` | session-scoped memory, security evidence, regression evaluation |
| LangGraph-owned | `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `store`, and migration tables | resumable graphs and namespaced store |

## Important design decisions

- Currency uses `NUMERIC`, never floating point. Quantities use `NUMERIC(24,8)`.
- UUIDs, `DATE`, timezone-aware timestamps, `JSONB`, and `BYTEA` replace untyped source text,
  epoch, JSON text, and blob fields.
- Banking login names, IBANs, emails, phones, references, request fingerprints, and idempotency
  boundaries are constrained or indexed according to their lookup semantics.
- `tenant_id` and source lineage live with every banking customer. Authentication identity is
  injected from trusted request context and is never accepted from model tool arguments.
- Voice turns remain AES-GCM ciphertext. Agent requests, memory, tool arguments/results, and audit
  details retain the application's encrypted SQLAlchemy types.
- Foreign keys use cascade only for session-owned interaction records and beneficiary/Qatta child
  records. Ledger rows are retained as financial history.

## Legacy import and enrichment

`scripts/seed_postgres.py` loads all 1,000 basic-user CSV rows and all 1,001 advanced banking-user
CSV rows in one transaction.
It also creates realistic beneficiaries, three months of transaction history for active accounts,
demo bills, market assets, and holdings needed by the tools.

The five duplicated legacy banking usernames are not discarded. Their original value is stored in
`source_username`; later occurrences receive a stable account-derived login suffix. New fields are
deterministically derived from source identity and account state: unique demo contact details,
locale/timezone/currency, available balance, KYC tier/status, risk rating, and plausible login
timestamps. Plaintext passwords from `basic_users` are converted to scrypt hashes during import.

Run:

```bash
docker compose up -d postgres
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_postgres.py
```

Both commands load `DATABASE_URL` from the repository-root `.env.backend`.

The import uses stable UUIDv5 identifiers and conflict-safe inserts, so rerunning it updates source
records without duplicating generated rows.
