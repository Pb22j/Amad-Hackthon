# Minimal Nafi PostgreSQL data model

PostgreSQL 16 is the single system of record for the demo. The customer model is intentionally
small and starts with exactly ten seeded users. Registration can add more users using the same
minimal fields.

## Customer data

| Requested data | Storage |
|---|---|
| Username | `users.username` |
| Arabic and English full names | `users.full_name_ar`, `users.full_name_en` |
| Password | `users.password_hash` as salted scrypt; plaintext is never stored |
| Unique Nafi IBAN | `users.nafi_iban` |
| Spendable Nafi e-wallet balance | `users.nafi_balance` |
| Daily spend limit | `users.daily_spend_limit_sar` |
| One or more banks | one `bank_accounts` row per connected account |
| Read-only linked-bank balance | `bank_accounts.balance_sar` |
| Linked-bank total | computed as the sum of the user's `bank_accounts.balance_sar` values |
| Beneficiaries | `beneficiaries`, linked from owner to another Nafi user resolved by Nafi IBAN |

`users.uuid` and child-table UUIDs are internal relational keys, not registration fields. There
are no email, phone, KYC, Nafath, role, demographic, verification, status, or duplicate platform
profile requirements.

Beneficiary rows store only the owner, resolved beneficiary user, short name, and creation time.
Names and Nafi IBAN are read from the authoritative user row instead of being copied into the
beneficiary record. Transfers resolve directly to the beneficiary's Nafi wallet and never through
a linked bank account.

All financial actions debit or credit `users.nafi_balance`. Linked balances remain visible for
financial overview purposes, but tools cannot spend, receive into, or otherwise mutate them. The
migration performs a one-time copy of the former primary operational balance into `nafi_balance`
so existing customers keep the amount that was spendable before the wallet boundary was added.

The authenticated dashboard funds the wallet through `POST /api/wallet/deposit/request` followed by
`POST /api/wallet/deposit/confirm`. The agentic layer exposes the equivalent guarded
`fund_nafi_wallet` action. In both paths the customer selects an owned linked account, provides an
amount, and approves only after preflight with the demo OTP. The executing transaction locks and
rechecks both balances, debits only the selected bank account, credits `users.nafi_balance`, and
writes paired source/wallet ledger entries under one reference.

## Operational data

The remaining tables are workflow records rather than extra user attributes:

- `transactions`, `qattas`, `qatta_bills`, `fatoorahs`, `investment_assets`, and
  `investment_holdings` support the financial tools.
- `interaction_*` and `voice_turns` support authenticated chat and voice sessions.
- `agent_tasks`, tool executions, audit, encrypted memory, and LangGraph tables support the
  agent runtime, recovery, and diagnostics.

## Recreate and seed

```bash
docker compose down --volumes
docker compose up -d postgres
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_postgres.py
```

The seed command inserts exactly 10 initial users with explicit Nafi wallet balances, 11 linked bank
accounts (one user demonstrates multiple banks), four beneficiary links, and compact operational
demo data. Newly registered users receive a unique Nafi IBAN and a zero-balance Nafi wallet. Every seeded user uses password
`password123`; each database rebuild stores it as a new randomly salted scrypt hash.
