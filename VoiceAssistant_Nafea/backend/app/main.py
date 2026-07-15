"""Authenticated voice interaction service and agentic-layer bridge."""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import time
from collections import defaultdict
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import websockets
from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings
from app.interaction import (
    AgentEvent,
    InteractionSession,
    InteractionStore,
    issue_confirmation_token,
    sign_message,
    verify_message,
)
from app.prompts import gemini_setup
from app.services.llm_service import LLMException, get_llm_service
from app.services.stt_service import STTException, get_stt_service
from app.services.tts_service import TTSException, get_tts_service
from app.utils.cache import audio_cache
from app.utils.logger import logger


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


app = FastAPI(
    title="Nafea Voice Interaction Layer",
    description="Authenticated voice proxy and durable agentic interaction boundary",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Session-Token"],
)

interaction_store = InteractionStore(
    settings.INTERACTION_DATABASE_URL,
    encryption_key=settings.INTERACTION_DATA_ENCRYPTION_KEY,
    max_user_turns=settings.VOICE_MEMORY_MAX_USER_TURNS,
    max_assistant_turns=settings.VOICE_MEMORY_MAX_ASSISTANT_TURNS,
    max_memory_text_characters=settings.VOICE_MEMORY_MAX_TEXT_CHARACTERS,
)


class TokenBucketLimiter:
    def __init__(self, rate_limit: int) -> None:
        self.rate_limit = rate_limit
        self.buckets: dict[str, tuple[float, float]] = {}

    def is_allowed(self, key: str) -> bool:
        if self.rate_limit <= 0:
            return True
        now = time.monotonic()
        tokens, updated = self.buckets.get(key, (float(self.rate_limit), now))
        tokens = min(float(self.rate_limit), tokens + (now - updated) * self.rate_limit / 60)
        allowed = tokens >= 1
        self.buckets[key] = (tokens - 1 if allowed else tokens, now)
        if len(self.buckets) > 2000:
            self.buckets = {
                item: state for item, state in self.buckets.items() if now - state[1] < 600
            }
        return allowed


limiter = TokenBucketLimiter(settings.RATE_LIMIT_PER_MIN)
realtime_resume_handles: dict[str, str] = {}
active_realtime_connections: dict[tuple[str, str], WebSocket] = {}


@app.middleware("http")
async def secure_http_boundary(request: Request, call_next: Any) -> Response:
    # Browser CORS preflight requests intentionally carry no session cookie.
    # Let CORSMiddleware validate and answer them before enforcing endpoint auth.
    if request.method == "OPTIONS":
        return await call_next(request)

    if (
        request.url.path
        in {
            "/api/realtime-token",
            "/api/voice-chat",
            "/api/submit-task",
            "/api/resume-task",
            "/api/confirm-task",
        }
        and interaction_store.get_session(_session_token(request)) is None
    ):
        return Response(
            content=json.dumps({"detail": "Authenticated interaction session required"}),
            status_code=401,
            media_type="application/json",
        )
    if request.url.path.startswith("/api/") and request.url.path not in {
        "/api/health",
        "/api/config",
    }:
        client_ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(client_ip):
            return Response(
                content=json.dumps({"detail": "Too many requests"}),
                status_code=429,
                media_type="application/json",
            )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _session_token(request: Request) -> str | None:
    return request.headers.get("X-Session-Token") or request.cookies.get("nafea_session")


def require_session(request: Request) -> InteractionSession:
    session = interaction_store.get_session(_session_token(request))
    if session is None:
        raise HTTPException(status_code=401, detail="Authenticated interaction session required")
    return session


def _websocket_token(websocket: WebSocket) -> str | None:
    return websocket.cookies.get("nafea_session") or websocket.query_params.get("session_token")


def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    return origin is None or origin in settings.frontend_origins


class ConfigResponse(StrictModel):
    realtime_provider: str
    stt_provider: str
    llm_provider: str
    tts_provider: str
    openai_configured: bool
    gemini_configured: bool
    elevenlabs_configured: bool
    deepgram_configured: bool


class SessionRequest(StrictModel):
    language: str = Field(default="ar", pattern="^(ar|en)$")


class SessionResponse(StrictModel):
    session_id: str
    language: str
    expires_at: float


class RealtimeRequest(StrictModel):
    language: str = Field(default="ar", pattern="^(ar|en)$")


class SubmitTaskRequest(StrictModel):
    natural_language_request: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class ResumeTaskRequest(StrictModel):
    task_id: str
    user_answer: Any


class ConfirmTaskRequest(StrictModel):
    task_id: str
    approved: bool
    otp_code: str | None = Field(
        default=None, min_length=4, max_length=4, pattern=r"^\d{4}$", repr=False
    )

    @model_validator(mode="after")
    def otp_is_only_for_approval(self) -> "ConfirmTaskRequest":
        if self.approved and self.otp_code is None:
            raise ValueError("otp_code is required when approving a financial action")
        if not self.approved and self.otp_code is not None:
            raise ValueError("otp_code must not be sent when rejecting an action")
        return self


class VoiceChatResponse(StrictModel):
    user_transcript: str
    agent_text: str
    audio_base64: str
    audio_mime_type: str
    processing_time_sec: float


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/api/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    return ConfigResponse(
        realtime_provider="gemini",
        stt_provider=settings.STT_PROVIDER,
        llm_provider=settings.LLM_PROVIDER,
        tts_provider=settings.TTS_PROVIDER,
        openai_configured=bool(settings.OPENAI_API_KEY),
        gemini_configured=bool(settings.GEMINI_API_KEY),
        elevenlabs_configured=bool(settings.ELEVENLABS_API_KEY),
        deepgram_configured=bool(settings.DEEPGRAM_API_KEY),
    )


@app.post("/api/session", response_model=SessionResponse)
async def create_session(payload: SessionRequest, response: Response) -> SessionResponse:
    if not settings.ALLOW_DEMO_SESSION_BOOTSTRAP:
        raise HTTPException(status_code=404, detail="Demo session bootstrap is disabled")
    session, token = interaction_store.create_session(
        user_id=settings.DEMO_USER_ID,
        tenant_id=settings.DEMO_TENANT_ID,
        language=payload.language,
        scopes=settings.demo_scopes,
        ttl_seconds=settings.SESSION_TTL_SECONDS,
    )
    response.set_cookie(
        "nafea_session",
        token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return SessionResponse(
        session_id=session.session_id,
        language=session.language,
        expires_at=session.expires_at,
    )


@app.post("/api/realtime-token")
async def realtime_connection(request: Request, payload: RealtimeRequest) -> dict[str, str]:
    session = require_session(request)
    if payload.language != session.language:
        raise HTTPException(
            status_code=409, detail="Language does not match the interaction session"
        )
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Realtime voice provider is not configured")
    return {
        "provider": "gemini",
        "model": settings.REALTIME_MODEL,
        "websocket_url": "/api/realtime",
    }


async def _relay_browser_to_provider(browser: WebSocket, provider: Any) -> None:
    while True:
        raw = await browser.receive_text()
        if len(raw) > 1_000_000:
            raise ValueError("realtime message is too large")
        message = json.loads(raw)
        allowed = {"realtimeInput", "toolResponse", "clientContent"}
        if len(message) != 1 or next(iter(message)) not in allowed:
            raise ValueError("unsupported realtime client message")
        await provider.send(raw)


async def _relay_provider_to_browser(provider: Any, browser: WebSocket, *, session_id: str) -> None:
    user_transcript: list[str] = []
    assistant_transcript: list[str] = []
    async for raw in provider:
        text = raw if isinstance(raw, str) else raw.decode("utf-8")
        try:
            message = json.loads(text)
            resumption = message.get("sessionResumptionUpdate") or {}
            if resumption.get("resumable") and resumption.get("newHandle"):
                realtime_resume_handles[session_id] = str(resumption["newHandle"])
            content = message.get("serverContent") or {}
            input_text = (content.get("inputTranscription") or {}).get("text")
            output_text = (content.get("outputTranscription") or {}).get("text")
            if input_text:
                user_transcript.append(input_text)
            if output_text:
                assistant_transcript.append(output_text)
            if content.get("interrupted"):
                assistant_transcript.clear()
            if content.get("turnComplete"):
                if user_transcript:
                    interaction_store.record_voice_turn(
                        session_id=session_id,
                        role="user",
                        text="".join(user_transcript),
                        provenance="provider_input_audio_transcription",
                    )
                if assistant_transcript:
                    interaction_store.record_voice_turn(
                        session_id=session_id,
                        role="assistant",
                        text="".join(assistant_transcript),
                        provenance="provider_output_audio_transcription_untrusted",
                    )
                user_transcript.clear()
                assistant_transcript.clear()
        except (json.JSONDecodeError, LookupError, ValueError):
            logger.warning("Ignored invalid realtime transcription memory")
        await browser.send_text(text)


@app.websocket("/api/realtime")
async def realtime_websocket(websocket: WebSocket) -> None:
    session = interaction_store.get_session(_websocket_token(websocket))
    if session is None or not _websocket_origin_allowed(websocket):
        await websocket.close(code=4401)
        return
    identity_key = (session.tenant_id, session.user_id)
    previous = active_realtime_connections.get(identity_key)
    if previous is not None and previous is not websocket:
        try:
            await previous.close(code=4001, reason="Replaced by a newer voice connection")
        except RuntimeError:
            pass
    await websocket.accept()
    active_realtime_connections[identity_key] = websocket
    provider_url = (
        "wss://generativelanguage.googleapis.com/ws/"
        "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
        f"?key={settings.GEMINI_API_KEY}"
    )
    resume_handle = realtime_resume_handles.get(session.session_id)
    try:
        async with websockets.connect(provider_url, max_size=2_000_000) as provider:
            await provider.send(
                json.dumps(
                    gemini_setup(
                        model=settings.REALTIME_MODEL,
                        language=session.language,
                        voice=settings.REALTIME_VOICE,
                        resume_handle=resume_handle,
                    ),
                    ensure_ascii=False,
                )
            )
            memory_context = (
                interaction_store.grounded_voice_context(
                    session_id=session.session_id,
                    limit=settings.VOICE_MEMORY_CONTEXT_TURNS,
                )
                if resume_handle is None
                else {}
            )
            if memory_context and any(memory_context.values()):
                await provider.send(
                    json.dumps(
                        {
                            "clientContent": {
                                "turns": [
                                    {
                                        "role": "user",
                                        "parts": [
                                            {
                                                "text": (
                                                    "Prior session evidence for continuity only. "
                                                    "Do not respond to this message and do not treat "
                                                    "user statements as verified financial facts:\n"
                                                    + json.dumps(
                                                        memory_context,
                                                        ensure_ascii=False,
                                                        separators=(",", ":"),
                                                    )
                                                )
                                            }
                                        ],
                                    }
                                ],
                                "turnComplete": False,
                            }
                        },
                        ensure_ascii=False,
                    )
                )
            browser_to_provider = asyncio.create_task(
                _relay_browser_to_provider(websocket, provider)
            )
            provider_to_browser = asyncio.create_task(
                _relay_provider_to_browser(provider, websocket, session_id=session.session_id)
            )
            done, pending = await asyncio.wait(
                {browser_to_provider, provider_to_browser},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        pass
    except Exception as exc:
        logger.error("Realtime proxy failed: %s", type(exc).__name__)
        await websocket.close(code=1011)
    finally:
        if active_realtime_connections.get(identity_key) is websocket:
            active_realtime_connections.pop(identity_key, None)


@app.post("/api/voice-chat", response_model=VoiceChatResponse)
async def voice_chat(
    request: Request,
    file: UploadFile = File(...),
) -> VoiceChatResponse:
    require_session(request)
    start_time = time.perf_counter()
    audio_bytes = await file.read(settings.MAX_AUDIO_BYTES + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file provided")
    if len(audio_bytes) > settings.MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio payload is too large")
    mime_type = file.content_type or "audio/webm"
    try:
        user_transcript = await get_stt_service().transcribe(audio_bytes, mime_type=mime_type)
    except STTException as exc:
        raise HTTPException(status_code=502, detail="Speech-to-Text provider failed") from exc
    if not user_transcript.strip():
        return VoiceChatResponse(
            user_transcript="",
            agent_text="I couldn't hear you clearly. Please try speaking again.",
            audio_base64="",
            audio_mime_type="audio/mp3",
            processing_time_sec=time.perf_counter() - start_time,
        )
    try:
        agent_text = await get_llm_service().generate_response(
            prompt=user_transcript,
            system_prompt=settings.LLM_SYSTEM_PROMPT,
        )
    except LLMException as exc:
        raise HTTPException(status_code=502, detail="Language model provider failed") from exc
    try:
        cached = audio_cache.get(
            provider=settings.TTS_PROVIDER,
            voice_id=settings.TTS_VOICE_ID,
            text=agent_text,
        )
        audio_response = cached or await get_tts_service().synthesize(
            text=agent_text, voice_id=settings.TTS_VOICE_ID
        )
        if cached is None:
            audio_cache.set(
                provider=settings.TTS_PROVIDER,
                voice_id=settings.TTS_VOICE_ID,
                text=agent_text,
                audio_bytes=audio_response,
            )
    except TTSException as exc:
        raise HTTPException(status_code=502, detail="Text-to-Speech provider failed") from exc
    return VoiceChatResponse(
        user_transcript=user_transcript,
        agent_text=agent_text,
        audio_base64=base64.b64encode(audio_response).decode("ascii"),
        audio_mime_type="audio/mp3",
        processing_time_sec=round(time.perf_counter() - start_time, 3),
    )


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[session_id].add(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        self.connections[session_id].discard(websocket)
        if not self.connections[session_id]:
            self.connections.pop(session_id, None)

    async def send(self, session_id: str, message: dict[str, Any]) -> None:
        failed: list[WebSocket] = []
        for connection in self.connections.get(session_id, set()):
            try:
                await connection.send_json(message)
            except Exception:
                failed.append(connection)
        for connection in failed:
            self.disconnect(session_id, connection)


manager = ConnectionManager()


@app.websocket("/api/ws")
async def event_websocket(websocket: WebSocket) -> None:
    session = interaction_store.get_session(_websocket_token(websocket))
    if session is None or not _websocket_origin_allowed(websocket):
        await websocket.close(code=4401)
        return
    await manager.connect(session.session_id, websocket)
    try:
        for event in interaction_store.recent_events(session_id=session.session_id):
            await websocket.send_json(event)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session.session_id, websocket)


@app.post("/api/webhook")
async def handle_agentic_webhook(request: Request) -> dict[str, str]:
    body = await request.body()
    try:
        verify_message(
            settings.INTERACTION_SHARED_SECRET,
            body,
            timestamp=request.headers.get("X-Agentic-Timestamp", ""),
            signature=request.headers.get("X-Agentic-Signature", ""),
            max_age_seconds=settings.INTERACTION_TIMESTAMP_TOLERANCE_SECONDS,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    try:
        event = AgentEvent.model_validate_json(body)
        inserted = interaction_store.record_event(event)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid agent event") from exc
    if inserted:
        await manager.send(event.session_id, event.model_dump(mode="json"))
    return {"status": "received" if inserted else "duplicate"}


async def _agentic_post(url: str, payload: dict[str, Any]) -> httpx.Response:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    timestamp, signature = sign_message(settings.INTERACTION_SHARED_SECRET, body)
    async with httpx.AsyncClient(
        timeout=settings.AGENTIC_TIMEOUT_SECONDS, verify=settings.SSL_VERIFY
    ) as client:
        return await client.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Interaction-Timestamp": timestamp,
                "X-Interaction-Signature": signature,
            },
        )


@app.post("/api/submit-task", status_code=202)
async def submit_task(request: Request, payload: SubmitTaskRequest) -> dict[str, Any]:
    session = require_session(request)
    request_id = str(
        uuid5(NAMESPACE_URL, f"nafea:{session.session_id}:{payload.idempotency_key}")
        if payload.idempotency_key
        else uuid4()
    )
    try:
        interaction_store.reserve_request(
            session_id=session.session_id,
            request_id=request_id,
            natural_language_request=payload.natural_language_request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    existing = interaction_store.get_task_by_request(
        request_id=request_id, session_id=session.session_id
    )
    if existing is not None:
        return {
            "request_id": existing.request_id,
            "task_id": existing.task_id,
            "status": "accepted",
            "user_safe_message": "The existing financial task was returned.",
        }
    if interaction_store.get_active_task(session_id=session.session_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Finish the active financial task before starting another one",
        )
    agentic_payload = {
        "request_id": request_id,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "language": session.language,
        "natural_language_request": payload.natural_language_request,
        "original_user_message": payload.natural_language_request,
        "authorization": {
            "scopes": list(session.scopes),
            "authenticated_at": session.authenticated_at,
            "assurance_level": "demo_authenticated",
        },
        "metadata": {"source_provider": "nafea-voice"},
    }
    try:
        response = await _agentic_post(
            f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/request", agentic_payload
        )
        response.raise_for_status()
        accepted = response.json()
        if response.status_code != 202 or accepted.get("request_id") != request_id:
            raise ValueError("invalid agentic acceptance response")
        task_id = str(accepted["task_id"])
        interaction_store.record_task(
            session_id=session.session_id, request_id=request_id, task_id=task_id
        )
        return accepted
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("Agentic submit failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail="Agentic layer did not accept the task"
        ) from exc


@app.post("/api/resume-task", status_code=202)
async def resume_task(request: Request, payload: ResumeTaskRequest) -> dict[str, str]:
    session = require_session(request)
    task = interaction_store.get_task(task_id=payload.task_id, session_id=session.session_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found in this session")
    event = task.pending_event
    if not event or event.get("event_type") != "input_needed":
        raise HTTPException(status_code=409, detail="Task is not waiting for clarification")
    clarification_id = event.get("details", {}).get("clarification_id")
    if not clarification_id:
        raise HTTPException(status_code=409, detail="Clarification event is incomplete")
    resume_payload = {
        "request_id": task.request_id,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "clarification_id": clarification_id,
        "answer": payload.user_answer,
    }
    try:
        response = await _agentic_post(
            f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/tasks/{task.task_id}/resume",
            resume_payload,
        )
        if response.status_code != 202:
            response.raise_for_status()
            raise ValueError("unexpected resume response")
        interaction_store.clear_pending(
            task_id=task.task_id,
            session_id=session.session_id,
            expected_event=event,
        )
        return {"status": "resumed"}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Agentic layer rejected the clarification"
        ) from exc


@app.post("/api/confirm-task", status_code=202)
async def confirm_task(request: Request, payload: ConfirmTaskRequest) -> dict[str, str]:
    session = require_session(request)
    task = interaction_store.get_task(task_id=payload.task_id, session_id=session.session_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found in this session")
    event = task.pending_event
    if not event or event.get("event_type") != "confirmation_needed":
        raise HTTPException(status_code=409, detail="Task is not waiting for confirmation")
    if not payload.approved:
        rejection_payload = {
            "request_id": task.request_id,
            "session_id": session.session_id,
            "user_id": session.user_id,
            "tenant_id": session.tenant_id,
            "confirmation_rejected": True,
        }
        try:
            response = await _agentic_post(
                f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/tasks/{task.task_id}/resume",
                rejection_payload,
            )
            if response.status_code != 202:
                response.raise_for_status()
                raise ValueError("unexpected rejection response")
            interaction_store.clear_pending(
                task_id=task.task_id,
                session_id=session.session_id,
                expected_event=event,
            )
            return {"status": "rejected_by_user"}
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=502, detail="Agentic layer rejected the decision"
            ) from exc
    if not hmac.compare_digest(payload.otp_code or "", settings.DEMO_CONFIRMATION_OTP):
        raise HTTPException(status_code=403, detail="Invalid demo OTP")
    details = event.get("details", {})
    try:
        token = issue_confirmation_token(
            settings.CONFIRMATION_SIGNING_KEY,
            session=session,
            task_id=task.task_id,
            tool_name=details["tool_name"],
            arguments_hash=details["arguments_hash"],
            ttl_seconds=int(details.get("expires_in_seconds", 300)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Confirmation event is incomplete") from exc
    resume_payload = {
        "request_id": task.request_id,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "authorization_token": token,
        "otp_code": payload.otp_code,
    }
    try:
        response = await _agentic_post(
            f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/tasks/{task.task_id}/resume",
            resume_payload,
        )
        if response.status_code != 202:
            response.raise_for_status()
            raise ValueError("unexpected confirmation response")
        interaction_store.clear_pending(
            task_id=task.task_id,
            session_id=session.session_id,
            expected_event=event,
        )
        return {"status": "confirmed"}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Agentic layer rejected the confirmation"
        ) from exc
