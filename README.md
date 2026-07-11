# Nafi (نافع)

Nafi is a bilingual agentic-finance demo for Saudi Arabia. It accepts natural
chat or voice requests, applies financial safety rules, and executes them
through a seeded banking simulator. The same adapter boundary is ready for the
Saudi Open Banking provider when its credentials and endpoints become
available.

## Judge demo

```bash
cp .env.template .env
python3 main.py
```

Open <http://localhost:3000>. No API keys or network calls are required for the
demo. Transfers, beneficiaries, Saudi-market investing, Qatta, reports,
savings, gifts, financial analysis, and store purchases all use deterministic
seeded data.

On a fresh clone, `python3 main.py` creates the local Python environment and
runs `npm ci` automatically before starting. Later runs reuse those installed
dependencies. Python 3.10+ and Node.js 22.13+ are the only prerequisites.

To enable model-backed chat and voice, add only these values to the root
`.env`; every secret remains server-side:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-5.6-luna
```

The template already supplies the recommended realtime voice model and voice.
`VOICE_AUDIO_PROVIDER=auto` selects OpenAI STT/TTS when the key exists and the
offline provider otherwise. `OPENAI_REALTIME_MODEL` and
`OPENAI_REALTIME_VOICE` configure the browser live-call channel.

Before presenting, validate the environment without starting anything:

```bash
python3 main.py --check
```

The launcher installs missing dependencies, validates configuration and startup ports; starts
the agentic, interaction, and web services; waits for all three health checks;
and stops the full process tree on Ctrl+C. Its startup summary never prints API
keys.

## Optional manual dependency install

The launcher normally performs this automatically. For an offline or managed
development environment, the equivalent pinned setup is:

```bash
python3 -m venv user_interaction/.venv
user_interaction/.venv/bin/python -m pip install -r requirements.lock
cd web_ui
npm ci
cd ..
```

Architecture and provider details live in
[agentic/README.md](agentic/README.md) and
[user_interaction/README.md](user_interaction/README.md).
