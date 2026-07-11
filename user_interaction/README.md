# User Interaction Layer

This package contains the user-facing interaction layer for the financial app.

It supports:

- bilingual chat with deterministic offline behavior and optional API models,
- English and Arabic voice through a shared WebSocket pipeline,
- optional OpenAI STT/TTS and PersonaPlex adapters,
- one natural-language request API to the agentic layer,
- financial privacy and prompt-injection guardrails before dispatch.
- LLM-based financial security guard with deterministic fallback.

The interaction layer owns the conversation experience. The agentic layer owns action planning, tool use, approval logic, and business checks for large or destructive financial actions.

## Current Implementation Status

Implemented foundation:

- session and turn models,
- language detection,
- request clarity checks,
- prompt-injection detection,
- financial privacy checks,
- LLM security guard through OpenRouter,
- redaction for logs and user-safe notifications,
- single natural-language agentic request schema,
- mock and HTTP agentic clients,
- chat orchestration path,
- notification rendering,
- provider interfaces plus working OpenAI and mock voice audio adapters,
- unit tests for the core behavior.

## Run Tests

From the repo root:

```bash
python3 -m venv user_interaction/.venv
user_interaction/.venv/bin/python -m pip install -r user_interaction/requirements.txt
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=user_interaction/src user_interaction/.venv/bin/python -m unittest discover -s user_interaction/tests
```

## Configure Environment

Nafi has one environment file for the whole project. From the repository root:

```bash
cp .env.template .env
```

No keys are required. The default starts the real interaction-to-agentic HTTP
boundary with a mock banking backend, deterministic safety guard, and offline
voice provider. `user_interaction/run_server.py` and the full launcher both
load this root file automatically; exported shell variables take precedence.

For local testing without a real agentic service:

```text
USER_INTERACTION_USE_MOCK_AGENTIC=true
```

For real wiring:

```text
USER_INTERACTION_USE_MOCK_AGENTIC=false
AGENTIC_BASE_URL=http://127.0.0.1:8090
AGENTIC_REQUEST_PATH=/agentic/request
```

For production financial security:

```text
SECURITY_GUARD_PROVIDER=openrouter
SECURITY_GUARD_MODEL=<cheap-but-reliable-json-capable-model>
SECURITY_GUARD_REQUIRED=true
```

When `SECURITY_GUARD_REQUIRED=true`, the interaction layer fails closed if the LLM guard is unavailable. For local development, leave it `false` to use the deterministic fallback when keys are missing.

For model-backed chat and voice, set one server-side secret:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-5.6-luna
VOICE_AUDIO_PROVIDER=auto
OPENAI_REALTIME_MODEL=gpt-realtime-2.1
OPENAI_REALTIME_VOICE=marin
```

With `VOICE_AUDIO_PROVIDER=auto`, the interaction server chooses OpenAI when
the key exists and the offline provider otherwise. An explicit
`VOICE_AUDIO_PROVIDER=openai` with no key also degrades safely to mock mode and
reports the fallback in `/health` instead of failing during the demo.

## Security Guard

The security layer uses a hybrid model:

- Redaction runs first so card/account-like numbers, emails, and secrets are masked before any external guard call.
- The LLM guard classifies prompt injection, hidden prompt/tool disclosure, secret exfiltration, unauthorized financial data access, and bulk customer/account export attempts.
- The model must return strict JSON with `action`, `risk_level`, `categories`, reason, and safe user-facing messages.
- High or critical risk classifications cannot pass through as allowed; they are normalized to refusal.
- If the model is down and `SECURITY_GUARD_REQUIRED=true`, the system refuses instead of dispatching.
- Large transfers or destructive-looking financial actions are still passed to the agentic layer when they are not privacy or prompt-injection attacks, because business approval policy lives there.

## Run Local Server

```bash
PYTHONPATH=user_interaction/src user_interaction/.venv/bin/python user_interaction/run_server.py
```

Default URL:

```text
http://127.0.0.1:8088
```

Health check (includes non-secret provider modes and capabilities):

```bash
curl http://127.0.0.1:8088/health
```

## Agentic API Boundary

The interaction layer sends one request to the agentic layer:

```http
POST /agentic/request
```

The payload contains the final natural-language request plus metadata. It does not send action-specific structured commands such as intents, entities, or constraints as the primary contract.

## Local Interaction Endpoints

### Chat

```bash
curl -X POST http://127.0.0.1:8088/interaction/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-1",
    "message": "Please review my account cashflow for last month."
  }'
```

### Voice Final Transcript

The transcript endpoint accepts final transcripts from a voice provider adapter and sends them through the same policy and agentic request flow.

```bash
curl -X POST http://127.0.0.1:8088/interaction/voice/transcript \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-1",
    "language": "en",
    "source_provider": "personaplex",
    "transcript": "Please check whether my latest card payment was posted."
  }'
```

Arabic example:

```bash
curl -X POST http://127.0.0.1:8088/interaction/voice/transcript \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-1",
    "language": "ar",
    "source_provider": "arabic_voice",
    "transcript": "راجع حالة دفع البطاقة من أمس من فضلك"
  }'
```

### Agentic Notification

```bash
curl -X POST http://127.0.0.1:8088/interaction/agentic-notification \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "task-id",
    "request_id": "request-id",
    "session_id": "session-id",
    "event_type": "completed",
    "user_safe_summary": "Done. I prepared the account activity summary.",
    "details": {}
  }'
```

## Voice Implementation

Voice is implemented through two runtime paths:

1. Turn-based voice pipeline for both English and Arabic:
   - client sends audio chunks over WebSocket,
   - server buffers until `commit`,
   - configured STT provider transcribes,
   - interaction policy checks privacy and prompt injection,
   - orchestrator sends one natural-language request to the agentic layer,
   - configured TTS provider returns playable audio to the user.

2. PersonaPlex realtime bridge for English:
   - client connects to this server,
   - server bridges Opus audio to a self-hosted PersonaPlex server,
   - PersonaPlex audio and text-token frames are forwarded back to the client.

PersonaPlex does not provide user transcripts in the currently documented LiveKit integration, so the agentic handoff path uses the turn-based voice pipeline where STT is available.

### Voice WebSocket Pipeline

Connect:

```text
ws://127.0.0.1:8088/interaction/voice/ws?user_id=user-1&language=en
```

Arabic:

```text
ws://127.0.0.1:8088/interaction/voice/ws?user_id=user-1&language=ar
```

Protocol:

- Server sends `{"type":"ready","mode":"pipeline",...}` after connection.
- Client sends binary audio chunks.
- Client sends `{"type":"commit"}` when the utterance is complete.
- Server sends a `voice_turn` JSON event with transcript, natural user-facing text, task ID, and request ID.
- Server sends `audio_start`, then a binary audio frame, then `audio_end`.

For development, clients can send a text command instead of audio:

```json
{
  "type": "text",
  "text": "Please check whether my latest card payment was posted."
}
```

### PersonaPlex Realtime Bridge

Connect:

```text
ws://127.0.0.1:8088/interaction/voice/personaplex/ws
```

Required `.env` values:

```text
PERSONAPLEX_URL=wss://localhost:8998
PERSONAPLEX_API_KEY=
PERSONAPLEX_VOICE=NATF2.pt
PERSONAPLEX_TEXT_PROMPT=You are a warm financial voice assistant.
```

The bridge follows the PersonaPlex WebSocket convention:

- `0x00` server handshake,
- `0x01` Opus audio frames in both directions,
- `0x02` UTF-8 text token frames from PersonaPlex.

For local hosting guidance and hardware expectations, see
[PERSONAPLEX_LOCAL_HOSTING.md](docs/PERSONAPLEX_LOCAL_HOSTING.md).

Current behavior:

- `OpenAIVoiceAudioProvider` provides functional STT and TTS for English and Arabic when `VOICE_AUDIO_PROVIDER=openai`.
- `MockVoiceAudioProvider` provides local development and tests when `VOICE_AUDIO_PROVIDER=mock`.
- `PersonaPlexVoiceProvider` starts English voice sessions and validates PersonaPlex configuration.
- `ArabicVoiceProvider` starts Arabic voice sessions through a replaceable provider name/API key.
- `EnglishVoiceChannel.handle_final_transcript(...)` routes English transcripts from an external STT/callback path into the orchestrator.
- `ArabicVoiceChannel.handle_final_transcript(...)` routes Arabic transcripts from an external STT/callback path into the orchestrator.
- Both voice paths use the same privacy checks, prompt-injection checks, natural acknowledgement, and single natural-language agentic API as chat.

Production follow-ups after the judge demo are provider-specific voice tuning,
long-running latency/interruption observability, and hardening against the live
Saudi Open Banking conformance environment.
