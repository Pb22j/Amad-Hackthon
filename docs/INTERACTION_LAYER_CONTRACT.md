# Interaction Layer ↔ Agentic Layer Contract

## 1. Purpose

This document defines how the user-facing interaction layer integrates with the Amad financial
agentic service. The interaction layer owns authentication and all communication with the user.
The agentic layer owns intent classification, planning, guarded tool execution, durable task state,
clarification and confirmation pauses, and the final structured report.

The integration is asynchronous and event-driven:

1. The interaction layer authenticates the user, durably reserves the request ID for the current
   session, and submits a signed task. This reservation lets an early signed webhook establish the
   task binding before the submit HTTP response arrives.
2. The agentic API immediately returns `202 Accepted` and a durable `task_id`.
3. The agent sends signed webhook events as the task changes state.
4. When input or approval is needed, the interaction layer asks the user and calls the resume API.
5. The final report arrives in a `completed`, `rejected`, or `failed` webhook event.

The agent does not communicate with the user directly. There is intentionally no production
polling/status API in the current contract; the interaction layer must consume webhook events
durably. A temporary signed polling endpoint exists only for the standalone evaluator described in
section 14. It is hidden from OpenAPI and returns `404` in production.

## 2. Trust and Security Responsibilities

### Interaction layer responsibilities

- Authenticate the user before every submit or resume request.
- Derive `user_id`, `tenant_id`, `session_id`, scopes, authentication time, and assurance level from
  trusted session/authentication state—not from user text or model output.
- For realtime voice, derive the submitted financial request from the provider input transcript.
  Bind that transcript to the authenticated session and provider tool-call ID with a short-lived
  server HMAC; never submit a model-reconstructed request argument as the original user message.
- Sign the exact HTTP request bytes with `INTERACTION_SHARED_SECRET`.
- Verify signatures on every agent webhook before parsing or displaying it.
- Preserve the original identity tuple across every resume call.
- Present clarification questions and confirmation details to the same authenticated user/session.
- Never collect credentials in conversation or forward them to a model/tool. The demo confirmation
  form is the sole exception: it accepts the fixed action OTP `1111` over the authenticated backend.
- Generate exact-action authorization tokens only after explicit user approval.
- Treat duplicate webhook delivery as normal and process events idempotently.

### Agentic layer guarantees

- It never trusts identity, permissions, or confirmation values found in natural-language text.
- It scopes tasks, memory, and tool results to the authenticated user and tenant.
- It pauses before configured sensitive financial actions.
- It binds confirmation to the exact user, tenant, task, tool, arguments hash, expiration, and nonce.
- It validates authoritative ownership and receipts before reporting financial success.
- It returns user-safe summaries rather than hidden prompts, chain-of-thought, or raw errors.
- It returns typed interaction context for the understood goal, verified facts, and useful next
  steps, including clear capability guidance for unexpected prompts.

### Unified assistant behavior

The interaction experience presents Nafea as one polite, respectful, helpful assistant. It relies
on agentic events for financial truth and system capability guidance, but must not tell the user it
is consulting another agent, calling a tool, or waiting on a backend. Clarifications, confirmations,
outcomes, and guidance should be expressed naturally in the user's language.

## 3. Configuration Shared Between Services

| Setting | Purpose |
|---|---|
| `AGENTIC_BASE_URL` | Base URL of this service, for example `https://agentic.internal`. |
| `INTERACTION_SHARED_SECRET` | At least 32 random bytes; signs requests in both directions. |
| `CONFIRMATION_SIGNING_KEY` | At least 32 random bytes; signs exact-action approval tokens. |
| `INTERACTION_EVENT_WEBHOOK_URL` | Interaction endpoint to which agent events are delivered. |

Store both secrets in a secret manager. Do not log them, place them in request bodies, or expose them
to a model. Production should use TLS and service-to-service network authentication in addition to
the message signatures described below.

## 4. Interaction-to-Agent Request Signing

All calls to `/agentic/request`, `/agentic/tasks/{task_id}/resume`, and `/agentic/memory` must include:

```http
Content-Type: application/json
X-Interaction-Timestamp: <Unix timestamp in seconds>
X-Interaction-Signature: <lowercase hexadecimal HMAC-SHA256>
```

The signature input is the timestamp, one ASCII period, and the **exact request body bytes**:

```text
signature = hex(HMAC-SHA256(
    key = INTERACTION_SHARED_SECRET,
    message = timestamp_utf8 + "." + raw_body_bytes
))
```

Do not parse and reserialize the body after signing it. The agent rejects missing/invalid signatures
and timestamps more than 300 seconds from its clock. Synchronize both services with NTP.

Python example:

```python
import hashlib
import hmac
import time

timestamp = str(int(time.time()))
signature = hmac.new(
    INTERACTION_SHARED_SECRET.encode(),
    timestamp.encode() + b"." + body,
    hashlib.sha256,
).hexdigest()
```

## 5. Submit a Task

```http
POST /agentic/request
```

Request body:

```json
{
  "request_id": "9fd7514c-3730-49bb-8bf0-210a4d93a2ce",
  "session_id": "e374ab75-0137-4b5e-9d72-aa42d76dac24",
  "user_id": "user-123",
  "tenant_id": "tenant-456",
  "language": "en",
  "natural_language_request": "Transfer 250 SAR to my savings beneficiary",
  "original_user_message": "Transfer 250 SAR to my savings beneficiary",
  "authorization": {
    "scopes": ["financial:read", "financial:write"],
    "authenticated_at": "2026-07-13T12:00:00Z",
    "assurance_level": "high"
  },
  "metadata": {
    "created_at": "2026-07-13T12:00:01Z",
    "conversation_context_summary": "The user selected their savings beneficiary.",
    "source_provider": "mobile-app"
  }
}
```

Field rules:

| Field | Rule |
|---|---|
| `request_id` | New UUID generated by the interaction layer. Reuse only to retry the same logical request. |
| `session_id` | UUID of the authenticated interaction session. |
| `user_id` | Stable authenticated user identifier; never taken from message text. |
| `tenant_id` | Stable authenticated tenant identifier. |
| `language` | `en` or `ar`. |
| `natural_language_request` | Normalized request sent to the agent; 1–20,000 characters. |
| `original_user_message` | Original user text for provenance; 1–20,000 characters. |
| `authorization.scopes` | Non-empty scopes granted by the authorization service. |
| `authenticated_at` | Time of the authentication used for this task. |
| `assurance_level` | Organization-defined value such as `standard` or `high`. |
| `conversation_context_summary` | Optional, untrusted, maximum 10,000 characters; never place secrets here. |

Unknown JSON fields are rejected. The interaction layer should not retry with a new `request_id` if
the HTTP response is lost: retry the same signed body and request ID so task creation remains
idempotent within the tenant.

Successful response (`202 Accepted`):

```json
{
  "request_id": "9fd7514c-3730-49bb-8bf0-210a4d93a2ce",
  "task_id": "119cbb63-9304-4e94-8602-11e258092543",
  "status": "accepted",
  "user_safe_message": "The financial task was accepted."
}
```

Persist a `request_id` ↔ `session_id` reservation before submission. Atomically bind its `task_id`
from either the first valid signed webhook or the `202` response, and reject conflicting bindings.
The `202` response means accepted for processing, not financially completed.

## 6. Agent-to-Interaction Webhook

The agent sends `POST` requests to `INTERACTION_EVENT_WEBHOOK_URL` with:

```http
Content-Type: application/json
X-Agentic-Timestamp: <Unix timestamp in seconds>
X-Agentic-Signature: <lowercase hexadecimal HMAC-SHA256>
```

The webhook signature uses the same construction as request signing:

```text
expected = hex(HMAC-SHA256(
    key = INTERACTION_SHARED_SECRET,
    message = x_agentic_timestamp_utf8 + "." + raw_body_bytes
))
```

Verify the signature with a constant-time comparison **before parsing or using the body**. Reject
stale timestamps (recommended maximum age: 300 seconds). Return any `2xx` response only after the
event has been durably recorded. The agent stores events in a transactional outbox and retries
failed delivery in task order, so duplicate delivery is expected; persist a body hash for
deduplication.

Common event envelope:

```json
{
  "task_id": "119cbb63-9304-4e94-8602-11e258092543",
  "request_id": "9fd7514c-3730-49bb-8bf0-210a4d93a2ce",
  "session_id": "e374ab75-0137-4b5e-9d72-aa42d76dac24",
  "event_type": "completed",
  "user_safe_summary": "The transfer was completed.",
  "details": {},
  "created_at": "2026-07-13T12:00:05Z"
}
```

Event types:

| Event | Required interaction behavior |
|---|---|
| `accepted` | Optionally tell the user processing has started. Do not claim completion. |
| `progress` | Optionally display the safe summary. |
| `input_needed` | Ask the supplied question and resume with the answer. |
| `confirmation_needed` | Display the exact safe action details and require explicit approval. |
| `completed` | Present `details.report` naturally; use `interaction_context` to preserve goal/facts/next steps and reconcile receipt IDs when present. |
| `rejected` | Present the safe rejection summary; do not expose internal policy details. |
| `failed` | Present the safe failure summary and a support correlation using `task_id`. |

Before acting on any event, verify that its `task_id`, `request_id`, and `session_id` match the
mapping stored from task submission. Reject event types outside the enumerated schema above. Never
route an event based on a user ID inside `details`.

## 7. Clarification Flow

An `input_needed` event has details shaped like:

```json
{
  "kind": "clarification",
  "clarification_id": "ba134951-b4c2-5f4c-93c5-1ed091ba1cea",
  "question": "Which beneficiary should receive the transfer?",
  "reason_code": "missing_destination",
  "expected_answer": {
    "type": "string",
    "field": "destination",
    "label": "Beneficiary",
    "description": "Select the beneficiary who should receive the transfer.",
    "enum": ["Savings", "Family"]
  },
  "expires_in_seconds": 900
}
```

Rules:

- Display `question` as the agent-authored question and render `expected_answer` as a dedicated
  missing-information card. Supported scalar types are `string`, `number`, `integer`, and
  `boolean`; `enum` supplies two to twenty fixed choices. Optional `label`, `description`,
  `minimum`, `maximum`, `minLength`, and `maxLength` provide bounded presentation metadata.
- Submit the card through the authenticated interaction resume endpoint. The browser must never
  call the agentic service directly; “direct to the active request” means the interaction backend
  preserves identity, validates the value, and forwards it to the matching clarification.
- Never satisfy a clarification from old conversation state without asking when the event requires it.
- Reject or escalate if the question asks for a password, PIN, OTP, CVV, token, or other credential.
- Resume before the stated expiration.
- Treat the answer as untrusted user data; validate and normalize it against `expected_answer`
  before forwarding it, and do not add identity or scope fields based on it. Voice answers arrive
  as text and may be safely coerced to the declared number, integer, or boolean type.

Resume request:

```http
POST /agentic/tasks/{task_id}/resume
```

```json
{
  "request_id": "9fd7514c-3730-49bb-8bf0-210a4d93a2ce",
  "session_id": "e374ab75-0137-4b5e-9d72-aa42d76dac24",
  "user_id": "user-123",
  "tenant_id": "tenant-456",
  "clarification_id": "ba134951-b4c2-5f4c-93c5-1ed091ba1cea",
  "answer": "My savings beneficiary"
}
```

Sign this request exactly as described in section 4. A successful resume returns an empty
`202 Accepted` response. The task may emit another clarification, a confirmation, or a terminal
event afterward.

## 8. Exact Financial-Action Confirmation

A `confirmation_needed` event has details shaped like:

```json
{
  "kind": "confirmation",
  "tool_name": "transfer_funds",
  "arguments": {
    "destination": "Savings",
    "amount": "250.00",
    "currency": "SAR"
  },
  "arguments_hash": "64-lowercase-hexadecimal-characters",
  "expires_in_seconds": 300
}
```

The interaction layer must:

1. Match the event to the stored task and currently authenticated session.
2. Render a human-readable confirmation from the safe `tool_name` and `arguments` allowlist.
3. Require an explicit approve/reject action; silence or a generic earlier consent is not approval.
4. Require the dedicated demo OTP (`1111`) in the confirmation form. Never ask for it by voice/chat.
5. On approval, create a short-lived, single-use token bound to the event's `arguments_hash`.
6. On rejection, do not create a token. Resume with the original identity tuple and
   `"confirmation_rejected": true`; the agent transitions the task to `rejected` without invoking
   the financial tool.

Do not allow the client application to construct the token. Token creation belongs on the trusted
interaction backend holding `CONFIRMATION_SIGNING_KEY`.

### Token format

The token is:

```text
base64url_no_padding(claims_json_utf8) + "." +
base64url_no_padding(HMAC-SHA256(CONFIRMATION_SIGNING_KEY, encoded_claims_ascii))
```

Required claims:

```json
{
  "task_id": "119cbb63-9304-4e94-8602-11e258092543",
  "user_id": "user-123",
  "tenant_id": "tenant-456",
  "tool_name": "transfer_funds",
  "arguments_hash": "the exact hash from the confirmation event",
  "nonce": "a unique cryptographically random value",
  "issuer": "interaction-layer",
  "confirmation_method": "explicit",
  "issued_at": "2026-07-13T12:01:00Z",
  "expires_at": "2026-07-13T12:06:00Z"
}
```

Use a maximum lifetime of 300 seconds. The nonce must never be reused. The agent verifies every
claim and consumes the nonce transactionally, preventing replay. If the tool arguments change after
approval, the token will not authorize the new action.

Resume request after approval:

```json
{
  "request_id": "9fd7514c-3730-49bb-8bf0-210a4d93a2ce",
  "session_id": "e374ab75-0137-4b5e-9d72-aa42d76dac24",
  "user_id": "user-123",
  "tenant_id": "tenant-456",
  "authorization_token": "<signed exact-action token>",
  "otp_code": "1111"
}
```

The resume body must contain either the clarification pair (`clarification_id` and `answer`) or
the confirmation pair (`authorization_token` and `otp_code`), never both modes. The OTP is validated
with constant-time comparison and is not persisted in task, graph, tool, or audit state.

## 9. Final Report

A `completed` event contains:

```json
{
  "event_type": "completed",
  "user_safe_summary": "The transfer was completed.",
  "details": {
    "report": {
      "status": "completed",
      "summary": "Transferred 250.00 SAR to Savings.",
      "actions": [],
      "result": {},
      "warnings": [],
      "receipt_ids": ["receipt-provider-123"],
      "needs_follow_up": false
    }
  }
}
```

Supported report statuses are `completed`, `partially_completed`, `rejected`, and `failed`.
Present `summary`, relevant warnings, follow-up state, and receipt IDs. Do not claim that the action
completed based on the original `202` response, a `confirmation_needed` event, or an `operation_id`.
Only the terminal report is the agent's user-safe outcome, and the agent includes receipt IDs only
after matching them to authoritative completed tool executions.

## 10. Delete Curated Memory

```http
DELETE /agentic/memory
```

Signed request body:

```json
{
  "request_id": "6ab7e819-47a6-4026-8918-3e72ca9e64b4",
  "session_id": "e374ab75-0137-4b5e-9d72-aa42d76dac24",
  "user_id": "user-123",
  "tenant_id": "tenant-456"
}
```

Response:

```json
{"deleted": 3}
```

The interaction layer must authenticate the same user and tenant before invoking deletion.

## 11. HTTP Status Handling

| Status | Meaning and required behavior |
|---|---|
| `200` | Successful health or memory deletion. |
| `202` | Task accepted or resume accepted; wait for webhook events. |
| `401` | Missing, expired, or invalid request signature; do not retry unchanged indefinitely. |
| `403` | Authenticated identity/scope is not allowed. |
| `404` | Task not found for the supplied identity; return a generic user message. |
| `409` | Invalid resume state, mismatched confirmation, or task not waiting for that input. |
| `422` | Invalid schema or request data; fix the caller payload. |
| `429` | Rate/concurrency limit; retry with bounded exponential backoff and jitter. |
| `5xx` | Temporary service/delivery failure; retry only idempotent submission using the same request ID. |

Never expose raw response details from `5xx` failures to the user. Log `request_id` and `task_id` as
correlation identifiers, but do not log request bodies, authorization tokens, or financial details.

## 12. State Machine and UX Rules

The durable internal states are:

```text
received → validating → running
running → waiting_for_input → running
running → waiting_for_confirmation → running
running → completed | partially_completed | rejected | failed
any nonterminal state → expired
```

Response deadlines must be recoverable from PostgreSQL when the interaction process starts. A
process-local timer may provide prompt cancellation, but it must not be the only timeout record.

The interaction layer should maintain one visible task card/message and update it from events rather
than creating a new user-visible request for every event. A task can pause more than once. Never
assume that a successful clarification or confirmation means the task is terminal.

## 13. Integration Acceptance Checklist

- [ ] Requests and resumes use the exact raw-body HMAC and pass signature-negative tests.
- [ ] Webhooks are verified before JSON parsing and acknowledged only after durable storage.
- [ ] Duplicate submissions reuse `request_id`; duplicate webhook events are idempotent.
- [ ] Identity and scopes come exclusively from authenticated backend state.
- [ ] Voice submissions use the signed provider transcript, not model-reconstructed request text.
- [ ] Active response deadlines are restored after an interaction-service restart.
- [ ] English and Arabic requests preserve the requested `language`.
- [ ] Clarification questions are displayed and answers resume the same task/session.
- [ ] Credential-like clarification questions are blocked/escalated.
- [ ] Confirmation displays the exact safe action and uses the event `arguments_hash`.
- [ ] Confirmation tokens are backend-generated, short-lived, unique, and never logged.
- [ ] Rejected confirmation never triggers a tool execution.
- [ ] Completion is shown only after a terminal event, with receipts when supplied.
- [ ] Cross-user, cross-tenant, mismatched-session, stale-signature, replay, and modified-argument
      tests all fail closed.
- [ ] Timeout/retry logic never creates a new request ID for the same logical submission.
- [ ] Secrets and sensitive financial data are absent from logs, analytics, and error messages.

The agent OpenAPI document is available at `/docs` in development. Generated clients may use it for
schema types, but the signing, event, confirmation, idempotency, and security requirements in this
contract remain mandatory.

## 14. Temporary Standalone Evaluator

`evaluation/task.py` is a dependency-free HTTP client for testing before the interaction layer is
available. It may be copied into an unrelated folder and exposes one function:

```python
from task import run_agent

report = run_agent("Show my checking account balance")
```

The client submits the normal signed request and polls
`POST /agentic/tasks/{task_id}/status` with the same signed identity envelope. That endpoint returns
only the durable status, safe pending action, and final report. It never returns checkpoints,
prompts, model traces, or raw tool output, is omitted from OpenAPI, and is disabled when
`service.environment` is `production`.

The evaluator can auto-sign a confirmation so dummy financial actions can finish without the real
interaction layer. This is an evaluation convenience, not a production confirmation flow. It does
not invent clarification answers: incomplete requests return a `needs_input` report.
