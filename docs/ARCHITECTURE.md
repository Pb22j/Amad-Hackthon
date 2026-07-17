# Codebase architecture

The integration branch contains one active web application and two active Python services. Older
frontend implementations are kept under `legacy/` for reference but are excluded from the active
Next.js build.

## Active tree

```text
.
├── app/                         Next.js App Router pages
├── components/                  Active Nafi UI and chat components
├── lib/                         Browser API/session client, i18n, and dashboard types
├── public/                      Active logos and realtime audio worklets
├── agentic/                     Guarded financial agent service (port 9000)
│   ├── agent/                   Task orchestration and workflow state
│   ├── api/                     Agent HTTP API and schemas
│   ├── config/                  YAML policy/model config and env loader
│   ├── migrations/              Agent/database migrations
│   ├── persistence/             SQLAlchemy repositories and stores
│   ├── security/                Signing, identity, confirmation, redaction
│   └── tools/                   Guarded financial tool providers
├── VoiceAssistant_Nafea/backend/ Interaction, voice, session, and webhook API (port 8001)
│   └── app/                     FastAPI application and interaction tests
├── scripts/                     Database seed and local operational commands
├── tests/                       Agent unit, integration, PostgreSQL, security, and live suites
└── docs/                        Contracts, data model, deployment, and architecture
```

## Runtime flow

```text
Next.js browser (:3000)
        │ session/task/dashboard HTTP, event WebSocket, realtime voice WebSocket
        ▼
Interaction service (:8001) ───── signed agent requests/webhooks ─────▶ Agentic service (:9000)
        │                                                               │
        └────────────── PostgreSQL shared system of record ◀────────────┘
```

The browser never receives provider keys, interaction secrets, user IDs, tenant IDs, or scopes.
The interaction service owns browser sessions, task correlation, confirmation tokens, webhook
verification, event delivery, and the read-only session-scoped dashboard projection. The agentic
service owns policy, model orchestration, guarded tools, durable workflow state, and signed outbox
delivery.

## Financial-advisor sub-agent

Personalized decision-support requests are routed to a dedicated `financial_advisor_subagent`
inside the agentic graph. It receives the authenticated user's read capabilities across balances,
cash flow, transactions, spending analysis, bills, qatta commitments, beneficiaries, and
investments, even when those capabilities normally belong to different read intents. This allows
the advisor to build the relevant financial picture instead of reasoning from a single account
figure.

The boundary is deterministic rather than prompt-only:

- `policies.yaml` permits only `read` and `sensitive_read` risk classes, and the configuration
  schema uses literal values so deployments cannot add a write class.
- Tools that require confirmation or an authoritative action receipt are also excluded.
- Advisory requests combined with an execution request stay on the advisory route. The advisor may
  describe an optional next request, but it cannot transfer, pay, fund, trade, add, cancel, or
  withdraw anything.
- The output policy rejects advisory reports containing executed actions, receipts, or a partial
  execution claim. Successful reports are marked `advisory_only=true` and `action_taken=false`.

The regular financial action agent and its exact-confirmation/OTP controls remain unchanged for a
later, separately classified action request initiated by the user.

## Archived tree

```text
legacy/
├── nafi-finance-ui/     superseded duplicate dashboard-card prototype
└── vite-voice-ui/       superseded Vite voice client
```

Do not import from `legacy/` in active code. The root `package.json`, `next.config.ts`, and
`tsconfig.json` describe the active Next.js application. The root `pyproject.toml` and `agentic/`
package describe the active agentic service; the interaction service retains its
`VoiceAssistant_Nafea/backend` path for its existing deployment and test contract.

Both Python services load the repository-root `.env.backend`. The browser loads only `.env.local`.
See [README.md](../README.md) for the startup sequence.
