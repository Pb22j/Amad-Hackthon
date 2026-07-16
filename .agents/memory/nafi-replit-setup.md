---
name: Nafi stack on Replit
description: Non-obvious constraints for running the nafi_v0.3.0 three-service stack on Replit
---

- Replit's runtime `DATABASE_URL` (plain `postgresql://`) overrides `.env.backend` (dotenv override=False); SQLAlchemy then wants psycopg2. **How to apply:** the Agentic API workflow command re-exports `DATABASE_URL` as `postgresql+psycopg://` built from PG* vars — keep that if editing workflows.
- Interaction service moved from upstream port 8001 → 8000 because 8001 is not a Replit-supported workflow port. `PORT` and webhook URL updated in `.env.backend`; browser reaches it at `https://$REPLIT_DEV_DOMAIN:8000` via `NEXT_PUBLIC_NAFEA_API_URL` in `.env.local` (regenerate if dev domain changes).
- The Next app is static-export (`output: "export"`), so no server rewrites/proxy — the browser must reach the interaction API cross-origin; its CORS `FRONTEND_ORIGINS` in `.env.backend` must include the Replit dev domain.
- `uv add google-genai` was blocked (project uses pyproject/hatchling editable install); plain `pip install` works in this repl.
