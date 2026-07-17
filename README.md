# Amad — Secure Agentic Financial Assistant

> A bilingual (Arabic / English) LangChain + LangGraph agent for authenticated
> banking workflows — built for the Amad Hackathon, hardened with a 100-case
> adversarial security suite and a 100-case functional evaluation.

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic-1f6feb.svg)](https://langchain-ai.github.io/langgraph/)
[![Next.js](https://img.shields.io/badge/Next.js-frontend-black.svg)](https://nextjs.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Eval pass rate](https://img.shields.io/badge/security%20eval-100%2F100-success.svg)](#security-evaluation)
[![Tests](https://img.shields.io/badge/coverage-%E2%89%A595%25-success.svg)](#tests)

---

## ✨ What is this?

**Amad** is a secure, agentic banking layer that lets an authenticated user talk
to their bank in natural language — Arabic or English — and actually get things
done: read balances, search transactions, pay bills, transfer to beneficiaries,
buy investments, all the way through a signed, OTP-confirmed execution.

It is not a chatbot. It is a **policy-gated agent**: every read is scoped to the
authenticated customer, every write requires an out-of-band signed
confirmation plus the fixed demo OTP `1111`, and every prompt is screened by a
deterministic policy engine before the model ever sees it.

The stack ships with a Next.js dashboard, a voice-ready interaction service
(Nafea), a FastAPI agentic service, a Postgres-backed demo bank, and two
hundred evaluation cases (security + functionality) that run locally.

---

## 🚀 Why it's interesting

- **🛡️ Hardened by default.** A 100-scenario bilingual adversarial suite
  (prompt injection, credential extraction, cross-user access, obfuscated
  injection, authority manipulation, tool-argument injection, bulk
  exfiltration) runs in CI and must pass before changes land.
- **🌍 Truly bilingual.** Every model role, every evaluation, every UI string
  is exercised in both Arabic and English. MiniMax-M2.7-highspeed is the
  default; provider and per-role models are editable in `agentic/config/llm.yaml`.
- **🔐 Signed boundary, not vibes.** Requests cross the interaction → agent
  boundary only when signed with `INTERACTION_SHARED_SECRET` and
  `CONFIRMATION_SIGNING_KEY`. The model never sees the OTP.
- **🧰 Pluggable tool layer.** Default tools cover balances, transaction
  search, beneficiaries, transfers, bill pay, Qatta, gifts, reports,
  financial analysis, and investment portfolio/trades — all backed by the
  shared PostgreSQL demo bank. Swap in your own package via
  `AGENTIC_TOOL_PROVIDER`.
- **🎙️ Voice-aware.** A real-time `/api/realtime` proxy streams the same
  agent to the browser for live voice sessions.

---

## 📸 Screenshots

<table>
  <tr>
    <td width="50%"><img src="Docs/Pics/mainPage.jpg.jpg" alt="Amad main dashboard" /></td>
    <td width="50%"><img src="Docs/Pics/AskNafi.jpg.jpg" alt="Ask Nafi — chat / voice" /></td>
  </tr>
  <tr>
    <td align="center"><sub><b>Authenticated dashboard</b></sub></td>
    <td align="center"><sub><b>Bilingual chat &amp; voice</b></sub></td>
  </tr>
  <tr>
    <td><img src="Docs/Pics/transactionPage.jpg.jpg" alt="Transactions" /></td>
    <td><img src="Docs/Pics/investmentpage.jpg.jpg" alt="Investment portfolio" /></td>
  </tr>
  <tr>
    <td align="center"><sub><b>Transaction history &amp; search</b></sub></td>
    <td align="center"><sub><b>Investment portfolio</b></sub></td>
  </tr>
  <tr>
    <td><img src="Docs/Pics/investmentPage2.jpg.jpg" alt="Investment detail" /></td>
    <td><img src="Docs/Pics/TestNafi.jpg" alt="Nafi interaction" /></td>
  </tr>
  <tr>
    <td align="center"><sub><b>Trade flow</b></sub></td>
    <td align="center"><sub><b>Nafi interaction service</b></sub></td>
  </tr>
  <tr>
    <td><img src="Docs/Pics/TestNafi2.jpg" alt="Nafi view" /></td>
    <td><img src="Docs/Pics/TestNafi3.jpg" alt="Nafi view" /></td>
  </tr>
  <tr>
    <td align="center"><sub><b>Nafi — alternate view</b></sub></td>
    <td align="center"><sub><b>Nafi — alternate view</b></sub></td>
  </tr>
</table>

---

## 🏗️ Architecture

```mermaid
flowchart LR
    Browser[Next.js UI<br/>:3000]
    WS[/WebSocket<br/>task events/]
    Voice[/Realtime proxy<br/>voice stream/]

    Browser <-->|HTTP / WS| Frontend[Next.js BFF]
    Frontend --> Nafea[Nafea Interaction Service<br/>:8001]
    Nafea <-->|signed requests| Agent[Amad Agentic API<br/>FastAPI · :9000]
    Agent <-->|tool calls| Tools[(PostgreSQL<br/>demo bank)]
    Agent <-->|provider| LLM[MiniMax / openAI-compatible]
    Frontend -.live voice.-> Nafea
    Browser -.WS.-> Agent
```

| Service             | Port | Role                                                       |
|---------------------|------|------------------------------------------------------------|
| Next.js frontend    | 3000 | Dashboard, voice UI, HttpOnly session                      |
| Nafea interaction   | 8001 | Voice + signed request layer, dashboard projection         |
| Amad agentic API    | 9000 | LangGraph agent, tool execution, signed confirmations      |
| PostgreSQL          | 55432| Shared demo bank, identity, audit, sessions                |

---

## ⚡ Quick start

You need **Python 3.13**, **Node.js ≥ 20**, and **Docker**.

```bash
# 1. Clone & install
git clone https://github.com/Pb22j/Amad-Hackthon.git
cd Amad-Hackthon
python3.13 -m venv .venv
.venv/bin/pip install -e '.[dev]'
npm ci

# 2. Configure env (one-time)
cp .env.backend.example .env.backend
cp .env.frontend.example .env.local

# 3. Bring up the full stack
docker compose up -d postgres
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_postgres.py
.venv/bin/amad-agent setup-langgraph
npm run dev
```

Open **http://localhost:3000** — the agentic service is on `:9000`, Nafea on
`:8001`, and the stack auto-stops if any required service exits.

> **Demo OTP is `1111`.** Confirmations are auto-signed in the sandbox.

### Try it from the CLI

```bash
set -a && source .env.backend && set +a
python evaluation/task.py "Show my current checking account balance."
```

---

## 🧪 Evaluation

Two independent suites ship with the repo. Both are deterministic and run
locally with no external bank.

### Functionality (`scripts/run_functionality_eval.py`)

100 bilingual workflows against the real agent graph + an in-memory dummy
ledger. Scores outcome, intent, risk, exact tool sequence, arguments,
clarification, confirmation, and receipts.

```bash
set -a && source .env.backend && set +a
.venv/bin/python scripts/run_functionality_eval.py --limit 1   # smoke test
.venv/bin/python scripts/run_functionality_eval.py            # full run
```

The full report is written to `outputs/functionality-eval-report.json`.

---

## 🔒 Security model (in 30 seconds)

| Layer                | Guarantee                                                                 |
|----------------------|---------------------------------------------------------------------------|
| Request signing      | Interaction → agent boundary requires HMAC + `CONFIRMATION_SIGNING_KEY`.  |
| Policy screening     | `PolicyEngine.screen_request` runs *before* the model on every request.   |
| Identity injection   | Tools receive `user` and `tenant` from the auth context, not the model.  |
| Signed confirmation  | All writes and financial actions require exact signed confirmation + OTP. |
| OTP isolation        | OTP only accepted by the confirmation endpoint; never enters model ctx.  |
| Retention cleanup    | `amad-agent cleanup-retention` runs from a scheduled job.                 |

See [`docs/SECURITY.md`](docs/SECURITY.md) and
[`docs/TOOL_CONTRACT.md`](docs/TOOL_CONTRACT.md) for the full contract.

---

## 🧱 Tech stack

- **Agent** — Python 3.13, LangChain, LangGraph, FastAPI, Pydantic, Alembic
- **Frontend** — Next.js, TypeScript, WebSockets, voice via `/api/realtime`
- **Data** — PostgreSQL 16 (Docker), seeded from bundled CSV demo data
- **Models** — MiniMax-M2.7-highspeed (default), MiniMax-M2.7, configurable
  per role in `agentic/config/llm.yaml`
- **Quality** — `pytest` with ≥ 95% branch coverage, `ruff`, two evaluation
  suites (security + functionality)

---

## 🧭 Where to look

| Doc                                            | What's in it                                                |
|------------------------------------------------|-------------------------------------------------------------|
| [`AGENTIC_IMPLEMENTATION_PLAN.md`](AGENTIC_IMPLEMENTATION_PLAN.md) | Why it was built this way, and the roadmap.   |
| [`docs/CODEBASE_GUIDE.md`](docs/CODEBASE_GUIDE.md)                 | Package tour, request lifecycle, extension points. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)                     | Active/legacy boundaries, service ownership.    |
| [`docs/INTERACTION_LAYER_CONTRACT.md`](docs/INTERACTION_LAYER_CONTRACT.md) | Signed request/response contract.        |
| [`docs/TOOL_CONTRACT.md`](docs/TOOL_CONTRACT.md)                   | Tool schema and result envelope.                |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)                         | Customer, banking, interaction, agent data.     |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)                         | Production deployment procedure.                |
| [`docs/SECURITY.md`](docs/SECURITY.md)                             | Threat model, signing keys, retention.          |

---

## 🧪 Tests

```bash
.venv/bin/pytest --cov=agentic --cov-branch --cov-fail-under=95
.venv/bin/ruff check .
.venv/bin/amad-agent eval-security
```

PostgreSQL integration tests (auto-spun up):

```bash
TEST_POSTGRES_URL=postgresql://amad:development-only-password@localhost:55432/amad \
  .venv/bin/pytest tests/postgres
```

Opt-in real-model suites (consume provider credits):

```bash
set -a && source .env.backend && set +a
RUN_REAL_MODEL_TESTS=1   .venv/bin/pytest tests/real_model/test_provider_compatibility.py
RUN_LIVE_AGENT_TESTS=1   .venv/bin/pytest tests/real_model/test_live_dummy_workflows.py
```

---

## 🤝 Contributing

Issues and PRs are welcome. Before opening a PR:

1. Run the test suite + `ruff` + `amad-agent eval-security`.
2. Run the full functionality eval and attach the JSON report.
3. Update the matching `docs/` page if you change a contract.

---

## 📄 License

No license file is committed yet. Until one is added, all rights are reserved
by the authors. If you'd like the project under a specific open-source
license (MIT / Apache-2.0 are common defaults for hackathon work), drop one
in and ping the maintainers.

---

<p align="center">
  Built with 🛡️ for the <b>Amad Hackathon</b> · powered by <b>MiniMax</b> · secured by <b>LangGraph</b>
</p>
