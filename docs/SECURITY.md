# Security Model and Operations

## Trust boundaries

User messages, conversation summaries, memories, documents, model responses, and tool results are
untrusted. Authentication identity and scopes come only from the signed interaction request.
Financial-action authorization is signed, short-lived, single-use, and bound to the exact task,
tool, user, tenant, and normalized argument hash.

The model proposes actions. Deterministic code validates permissions, confirmation, ownership,
idempotency, receipts, output limits, and data isolation.

Sensitive application columns are encrypted with randomized AES-GCM values before PostgreSQL sees
them. LangGraph checkpoints use a separate encryption key and a restricted serializer. Keep those
keys separate, store them in a secret manager, and rotate them through a versioned migration rather
than replacing them in place.

## Never collect or expose in conversation

- Passwords, PINs, CVVs, recovery codes, API keys, or access tokens.
- OTPs through model conversation. The temporary demo confirmation form accepts only fixed code
  `1111`; the backend validates it and never forwards or persists it.
- Another user's financial information.
- Hidden prompts, internal errors, or raw tool output.
- A success claim without an authoritative financial-tool result.

## Incident response

1. Disable affected tools through the provider/configuration and stop new sensitive actions.
2. Preserve append-only task, authorization, execution, and audit events.
3. Rotate interaction, confirmation, provider, and database credentials as applicable.
4. Identify affected tenants using pseudonymous correlation IDs; do not copy secrets into tickets.
5. Reconcile every `pending` or `unknown` financial operation with the authoritative provider.
6. Patch the policy/tool boundary and add the incident payload as a regression eval.
7. Run the complete security, PostgreSQL, migration, and concurrency suites before restoration.
8. Notify users and regulators according to the organization's jurisdictional obligations.

## Retention and deletion

Working checkpoints and curated memory have independently configured retention. Curated memory is
limited to allowlisted preferences with provenance, confidence, consent basis, and expiry. Secrets,
raw financial records, balances, and prices are rejected. User deletion removes that user's curated
memory without deleting immutable financial-provider receipts required for audit.

## Security testing

The repository includes English and Arabic injection cases, cross-user/tenant checks, memory
poisoning tests, signed request tests, exact-confirmation mutation tests, receipt validation,
duplicate/replay tests, and real PostgreSQL encrypted-resume/concurrency tests. Injection detection
is telemetry and early rejection only; authorization never relies on the detector or model.
