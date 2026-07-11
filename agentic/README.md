# Nafi (نافع) Agentic Financial Service

This service accepts the existing natural-language interaction request at
`POST /agentic/request` and runs the financial MVP through a stateful mock
bank, broker, savings provider, Qatta ledger, reports, gifts, and store.

## Run locally

```bash
python3 -m venv agentic/.venv
agentic/.venv/bin/python -m pip install -r agentic/requirements.txt
cp agentic/.env.example agentic/.env
PYTHONPATH=agentic/src agentic/.venv/bin/python agentic/run_server.py
```

The default service listens at `http://127.0.0.1:8090`. Mock mode does not
load a live profile, construct a bank client, or make any external request.

## Quick request

```bash
curl -X POST http://127.0.0.1:8090/agentic/request \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id":"demo-transfer-1",
    "session_id":"demo-session",
    "user_id":"user-1",
    "channel":"chat",
    "language":"en",
    "natural_language_request":"Transfer 250 SAR from alrajhi-main to snb-secondary",
    "original_user_message":"Transfer 250 SAR from alrajhi-main to snb-secondary",
    "confirmation":{"required":false,"received":true},
    "metadata":{"source_provider":"demo"}
  }'
```

Use `GET /agentic/tasks/{task_id}` to read a completed task in local MVP mode.
`GET /agentic/capabilities` reports which mock/live capabilities are available.

## Run with the interaction layer

Start the interaction service in one terminal and agentic service in another.
The shared notification secret is optional for local smoke tests but should be
set whenever callbacks are enabled.

```bash
# terminal 1
PYTHONPATH=user_interaction/src \
  AGENTIC_BASE_URL=http://127.0.0.1:8090 \
  AGENTIC_NOTIFICATION_SECRET=local-shared-secret \
  user_interaction/.venv/bin/python user_interaction/run_server.py

# terminal 2
PYTHONPATH=agentic/src \
  AGENTIC_NOTIFY_URL=http://127.0.0.1:8088/interaction/agentic-notification \
  AGENTIC_NOTIFY_SECRET=local-shared-secret \
  user_interaction/.venv/bin/python agentic/run_server.py
```

The interaction service returns immediately with its natural acknowledgement;
agentic then sends progress/completion events to the notification endpoint.

## Provider selection and live integration

The checked-in `.env.example` runs the complete seeded demo with no keys:

```dotenv
AGENTIC_PROVIDER_MODE=mock
AGENTIC_BANKING_PROVIDER=mock
AGENTIC_APPROVAL_MODE=auto_mock
```

When contracted sandbox credentials arrive, no transport code change is
required. Copy `.env.example`, select the live provider, and fill the matching
auth section and provider endpoint paths:

```dotenv
AGENTIC_PROVIDER_MODE=live
AGENTIC_BANKING_PROVIDER=saudi_open_banking
AGENTIC_APPROVAL_MODE=explicit
AGENTIC_REQUEST_WEBHOOK_SECRET=replace-with-the-interaction-shared-secret

SAUDI_OPEN_BANKING_BASE_URL=https://provider.example/open-banking/v1
SAUDI_OPEN_BANKING_AUTH_MODE=api_key_bearer_token
SAUDI_OPEN_BANKING_API_KEY=replace-me
SAUDI_OPEN_BANKING_ACCESS_TOKEN=replace-with-a-customer-sandbox-token
```

The live boundary supports API-key, static sandbox bearer-token, OAuth client
credentials, API-key-plus-bearer, and API-key-plus-OAuth profiles. Header names,
API version, AIS/PIS/beneficiary capability flags, mTLS, timeout, and every
resource path are environment-configurable. Base-path prefixes are preserved;
account, payment, and beneficiary identifiers are URL-encoded. Mutation calls
require both an idempotency key and FAPI interaction ID.

`GET /health/ready` validates the selected provider profile without calling a
bank. `GET /agentic/capabilities` distinguishes configured provider transport
from authorization to move real money. Startup fails closed with the exact
missing environment-variable names when live configuration is incomplete.

An API key or conversational confirmation is not bank authorization. Real
customer operations still require the contracted provider's consent/SCA
journey and a customer-bound token. The adapter accepts that token per request,
where it overrides an application token without entering the planner, task
payload, logs, SQLite, or UI.

For a single-user provider sandbox, set either a customer-bound bearer profile
(`SAUDI_OPEN_BANKING_ACCESS_TOKEN`) or the provider's opaque managed-consent
context (`SAUDI_OPEN_BANKING_CUSTOMER_CONTEXT_ID` plus its header name). Live
mutations additionally require the interaction layer to send the exact-action
approval as `confirmation.required=true` and `confirmation.received=true`; that
boolean is persisted with the idempotent request, while credentials are not.

The natural-language executor is wired to live AIS monthly reports/analysis,
own-account PIS transfers, and optional provider beneficiary synchronization.
Provider references and normalized status are retained for reconciliation, but
raw provider bodies and tokens are never returned to the UI or audit details;
live result objects mask account references and IBANs. A non-terminal payment
response is shown as submitted/partial rather than settled. Brokerage, bank-product onboarding,
and app-user/store payees remain fail-closed until their separate verified
partner mappings are configured; they never silently use the mock bank in live
mode.

### Offline provider contract tests

The live client is tested with an in-process HTTP transport, so CI needs no bank
network or credentials. The suite verifies provider selection, conditional auth
requirements, OAuth token caching, base-path routing, API-key/bearer headers,
idempotency and FAPI IDs, capability gating, HTTPS/mTLS validation, safe errors,
and secret-free representations.
