# Codebase architecture

The integration branch contains one active web application and two active Python services. Older
frontend implementations are kept under `legacy/` for reference but are excluded from the active
Next.js build.

## Active tree

```text
.
├── app/                         Next.js App Router pages
├── components/                  Active Nafi UI and chat components
├── lib/                         Active browser API, i18n, and dashboard data
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
        │ session/task HTTP, event WebSocket, realtime voice WebSocket
        ▼
Interaction service (:8001) ───── signed agent requests/webhooks ─────▶ Agentic service (:9000)
        │                                                               │
        └────────────── PostgreSQL shared system of record ◀────────────┘
```

The browser never receives provider keys, interaction secrets, user IDs, tenant IDs, or scopes.
The interaction service owns browser sessions, task correlation, confirmation tokens, webhook
verification, and event delivery. The agentic service owns policy, model orchestration, guarded
tools, durable workflow state, and signed outbox delivery.

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
