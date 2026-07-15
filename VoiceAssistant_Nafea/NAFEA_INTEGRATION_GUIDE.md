# Nafea voice interaction layer

Nafea is the authenticated user-facing boundary for the financial agent. The browser never receives
provider API keys, interaction secrets, confirmation keys, user IDs, tenant IDs, or scopes.

## Run locally

Backend requirements: Python 3.10+.

```bash
cd VoiceAssistant_Nafea/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# From the repository root, copy .env.backend.example to .env.backend once.
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The integrated frontend is the Next.js app at the repository root. Frontend requirements: Node.js
20.19+ or 22.12+.

```bash
cd ../..
npm ci
# Copy .env.frontend.example to .env.local once.
npm run dev
```

The frontend runs at `http://localhost:3000`. Because it supports static export, it uses the
build-time `NEXT_PUBLIC_NAFEA_API_URL` instead of a Next.js server proxy. The legacy Vite client
under `legacy/vite-voice-ui` remains only as a reference implementation.

## Required shared configuration

- `AGENTIC_BASE_URL` is the agent service origin, without `/agentic` appended.
- `INTERACTION_SHARED_SECRET` must match both services and signs exact request/webhook bytes.
- `CONFIRMATION_SIGNING_KEY` must match both services and is separate from the interaction secret.
- `DEMO_CONFIRMATION_OTP=1111` must match both services for this demo only.
- `GEMINI_API_KEY` stays only on the backend; `/api/realtime` proxies the provider WebSocket.
- `FRONTEND_ORIGINS` is an explicit comma-separated allowlist.
- Both Python services load the repository-root `.env.backend`; do not create a second backend env.
- Next.js loads only the repository-root `.env.local`.
- Keep `SSL_VERIFY=true`. Production configuration rejects disabled verification.

The demo bootstrap endpoint derives identity and scopes from server configuration and issues an
opaque HttpOnly session cookie. Set `ALLOW_DEMO_SESSION_BOOTSTRAP=false` in production and replace
that endpoint with the platform's real authenticated identity adapter. Production startup rejects
demo bootstrap.

## Agentic communication

1. The interaction session supplies the stable request/session/user/tenant tuple and scopes.
2. `/api/submit-task` signs and submits the exact agent request and durably records its task mapping.
3. `/api/webhook` validates signature freshness before parsing, correlates the full identity tuple,
   deduplicates the event, persists it, and routes it only to WebSockets for the matching session.
4. `input_needed` resumes with the persisted clarification ID and full original identity.
5. `confirmation_needed` displays exact arguments. Approval requires the dedicated on-screen demo
   OTP (`1111`) and creates a short-lived single-use token bound to the tool and arguments hash.
   The agent independently verifies both factors; rejection terminates the task without a tool call.
6. Only signed terminal events may be communicated as financial outcomes.

Interaction task/event state is stored in PostgreSQL. It is bounded, session-scoped, correlated by
foreign keys, and shared safely across interaction-service replicas.

## Voice memory and grounding

- Provider input/output transcription is enabled so the trusted backend, not the browser, observes
  conversation turns.
- Transcript text is encrypted at rest and scoped to the exact interaction session.
- Credential-like, long-number, and instruction-injection text is refused admission.
- Compaction is deterministic: it retains a bounded number of recent turns and never asks a model to
  summarize or rewrite them.
- Only explicit user statements are recalled, labeled as untrusted. Assistant responses are retained
  briefly for audit continuity but are never recalled as facts.
- Signed terminal agentic events are the only remembered financial outcomes. Balances, transactions,
  and account status must always be refreshed through the agentic tools.

## Verification

```bash
cd VoiceAssistant_Nafea/backend && PYTHONPATH=. .venv/bin/pytest -q app/tests
cd ../.. && npm run build && npm audit
```
