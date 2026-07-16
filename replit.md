# Nafi (Amad Financial Agent) — nafi_v0.3.0

## Overview
Secure LangChain/LangGraph financial agent with a Next.js frontend:
- **Agentic API** (FastAPI, port 9000): `main.py` → `agentic/` — LangGraph financial agent, uses OpenRouter models.
- **Interaction API** (FastAPI, port 8000): `VoiceAssistant_Nafea/backend` — auth, voice, bridge to agentic layer. (Upstream default was 8001; moved to 8000 for Replit port support.)
- **Web** (Next.js 15, port 5000): app router frontend at repo root, static-export style (no server rewrites); browser calls the Interaction API directly.
- **PostgreSQL**: Replit built-in database (replaces the Docker compose Postgres). Migrated with Alembic and seeded via `scripts/seed_postgres.py`.

## How to run on Replit
Three workflows are configured and auto-start:
- `Agentic API` — uvicorn on 9000 (DATABASE_URL is rewritten to `postgresql+psycopg://` from PG* vars in the workflow command).
- `Interaction API` — uvicorn on 8000 (externally exposed at `https://<dev-domain>:8000`).
- `Start application` — `next dev -p 5000` (preview).

Configuration:
- `.env.backend` — shared Python config (generated from `.env.backend.example`, gitignored). DB URLs point at the Replit database; internal signing/encryption keys were randomly generated.
- `.env.local` — `NEXT_PUBLIC_NAFEA_API_URL=https://<REPLIT_DEV_DOMAIN>:8000` (must be regenerated if the dev domain changes).
- Secrets: `OPENROUTER_API_KEY` (agentic LLM), `OPENAI_API_KEY` (voice STT/LLM/TTS). `GEMINI_API_KEY` optional for realtime voice.

## Demo login
Seeded users (password `password123`): `admin`, `evaluation-user`, `waleed`, `mohammed`, `noura`, `latifa`, `saud`, `faisal`, `sara`, `khalid`. Demo OTP for confirmations: `1111`.

## Setup already done
- Python 3.12 + Node 20 installed; `pip install -e '.[dev]'` plus `google-genai`, `python-multipart`.
- `alembic upgrade head`, `scripts/seed_postgres.py`, `amad-agent setup-langgraph` run against the Replit DB.

## User preferences
- Keep the existing project structure and stack.
