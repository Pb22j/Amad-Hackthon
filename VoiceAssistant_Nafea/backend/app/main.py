"""Authenticated voice interaction service and agentic-layer bridge."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import json
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterator, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

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

from app.auth import AuthenticatedUser, AuthenticationStore, RegistrationConflict
from app.config import settings
from app.dashboard import (
    DashboardStore,
    DepositAccountNotFound,
    DepositInsufficientFunds,
    DepositRequestConflict,
)
from app.interaction import (
    AgentEvent,
    InteractionSession,
    InteractionStore,
    issue_confirmation_token,
    sign_message,
    verify_message,
)
from app.prompts import gemini_initial_history, gemini_setup
from app.services.llm_service import LLMException, get_llm_service
from app.services.stt_service import STTException, get_stt_service
from app.services.tts_service import TTSException, get_tts_service
from app.utils.cache import audio_cache
from app.utils.logger import logger


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


@asynccontextmanager
async def app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await recover_task_watchdogs()
    yield


app = FastAPI(
    title="Nafea Voice Interaction Layer",
    description="Authenticated voice proxy and durable agentic interaction boundary",
    version="1.1.0",
    lifespan=app_lifespan,
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
    max_context_characters=settings.VOICE_MEMORY_CONTEXT_MAX_CHARACTERS,
)
dashboard_store = DashboardStore(settings.INTERACTION_DATABASE_URL)
authentication_store = AuthenticationStore(settings.INTERACTION_DATABASE_URL)


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
task_watchdogs: dict[str, asyncio.Task[None]] = {}


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
            "/api/cancel-task",
            "/api/new-chat",
            "/api/auth/session",
            "/api/auth/logout",
        }
        and await asyncio.to_thread(interaction_store.get_session, _session_token(request)) is None
    ):
        return Response(
            content=json.dumps({"detail": "Authenticated interaction session required"}),
            status_code=401,
            media_type="application/json",
        )
    if request.url.path.startswith("/api/") and request.url.path not in {
        "/api/health",
        "/api/config",
        # Agent events are authenticated with an HMAC signature and must not
        # compete with browser traffic for the per-client bucket. Otherwise a
        # normal task consumes the user's quota again for every event and can
        # strand the UI without its clarification or terminal result.
        "/api/webhook",
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


async def require_session(request: Request) -> InteractionSession:
    session = await asyncio.to_thread(interaction_store.get_session, _session_token(request))
    if session is None:
        raise HTTPException(status_code=401, detail="Authenticated interaction session required")
    return session


async def _interaction_call(method: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Keep synchronous Psycopg work outside the realtime event loop."""

    return await asyncio.to_thread(method, *args, **kwargs)


def _websocket_token(websocket: WebSocket) -> str | None:
    return websocket.cookies.get("nafea_session") or websocket.query_params.get("session_token")


def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    return origin is None or origin in settings.frontend_origins


def _localized_user_name(identity: dict[str, str], language: str) -> str:
    preferred, fallback = (
        (identity.get("full_name_en"), identity.get("full_name_ar"))
        if language == "en"
        else (identity.get("full_name_ar"), identity.get("full_name_en"))
    )
    name = (preferred or fallback or "").strip()
    if not name:
        raise LookupError("Authenticated customer profile has no name")
    return name


def _issue_voice_evidence(*, session_id: str, call_id: str, transcript: str) -> str:
    claims = {"session_id": session_id, "call_id": call_id, "transcript": transcript}
    body = json.dumps(claims, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp, signature = sign_message(settings.INTERACTION_SHARED_SECRET, body)
    encoded = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    return f"{timestamp}.{encoded}.{signature}"


def _verify_voice_evidence(token: str, *, session_id: str, call_id: str) -> str:
    try:
        timestamp, encoded, signature = token.split(".", 2)
        body = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        verify_message(
            settings.INTERACTION_SHARED_SECRET,
            body,
            timestamp=timestamp,
            signature=signature,
            max_age_seconds=120,
        )
        claims = json.loads(body)
        transcript = claims["transcript"]
        if (
            claims["session_id"] != session_id
            or claims["call_id"] != call_id
            or not isinstance(transcript, str)
            or not transcript.strip()
            or len(transcript) > 20_000
        ):
            raise ValueError
        return transcript.strip()
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise PermissionError("invalid voice transcript evidence") from exc


def _bind_voice_tool_calls(
    message: dict[str, Any], *, session_id: str, transcript: str
) -> None:
    """Replace model-reconstructed intent with signed provider transcription."""

    canonical = transcript.strip()
    if not canonical:
        return
    calls = (message.get("toolCall") or {}).get("functionCalls") or []
    for call in calls:
        if call.get("name") != "submit_financial_task":
            continue
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id:
            continue
        call["args"] = {
            "voice_transcript": canonical,
            "voice_evidence": _issue_voice_evidence(
                session_id=session_id,
                call_id=call_id,
                transcript=canonical,
            ),
        }


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
    reuse_existing: bool = False


class LoginRequest(StrictModel):
    identifier: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256, repr=False)
    language: str = Field(default="ar", pattern="^(ar|en)$")


class RegistrationRequest(StrictModel):
    username: str = Field(
        min_length=3, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$"
    )
    full_name_ar: str = Field(min_length=2, max_length=200)
    full_name_en: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=256, repr=False)
    language: str = Field(default="ar", pattern="^(ar|en)$")

    @model_validator(mode="after")
    def validate_password_strength(self) -> "RegistrationRequest":
        if not any(character.isalpha() for character in self.password) or not any(
            character.isdigit() for character in self.password
        ):
            raise ValueError("password must contain at least one letter and one number")
        return self


class SessionResponse(StrictModel):
    session_id: str
    session_token: str
    language: str
    expires_at: float


class RealtimeRequest(StrictModel):
    language: str = Field(default="ar", pattern="^(ar|en)$")


class SubmitTaskRequest(StrictModel):
    natural_language_request: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    source: Literal["chat", "voice"] = "chat"
    voice_evidence: str | None = Field(default=None, min_length=32, max_length=40_000, repr=False)


class ResumeTaskRequest(StrictModel):
    task_id: str
    user_answer: Any


class CancelTaskRequest(StrictModel):
    task_id: str


def _normalize_clarification_answer(answer: Any, schema: Any) -> Any:
    """Validate and coerce the safe scalar clarification contract used by UI and voice."""

    if not isinstance(schema, dict):
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
        raise HTTPException(status_code=422, detail="A non-empty answer is required")

    answer_type = schema.get("type", "string")
    try:
        if answer_type == "string":
            if not isinstance(answer, str):
                raise ValueError
            normalized: Any = answer.strip()
            if not normalized:
                raise ValueError
            if len(normalized) < int(schema.get("minLength", 1)) or len(normalized) > int(
                schema.get("maxLength", 500)
            ):
                raise ValueError
        elif answer_type == "integer":
            if isinstance(answer, bool):
                raise ValueError
            numeric = float(answer)
            if not numeric.is_integer():
                raise ValueError
            normalized = int(numeric)
        elif answer_type == "number":
            if isinstance(answer, bool):
                raise ValueError
            normalized = float(answer)
        elif answer_type == "boolean":
            if isinstance(answer, bool):
                normalized = answer
            elif isinstance(answer, str) and answer.strip().lower() in {"true", "yes", "1"}:
                normalized = True
            elif isinstance(answer, str) and answer.strip().lower() in {"false", "no", "0"}:
                normalized = False
            else:
                raise ValueError
        else:
            raise ValueError

        if "enum" in schema and normalized not in schema["enum"]:
            raise ValueError
        if answer_type in {"number", "integer"}:
            if "minimum" in schema and normalized < schema["minimum"]:
                raise ValueError
            if "maximum" in schema and normalized > schema["maximum"]:
                raise ValueError
        return normalized
    except (TypeError, ValueError, OverflowError):
        raise HTTPException(
            status_code=422, detail="The answer does not match the requested information"
        ) from None


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


class WalletDepositPreviewRequest(StrictModel):
    request_id: UUID
    source_account_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class InvestmentProjectionRequest(StrictModel):
    monthly_contribution_sar: Decimal = Field(
        ge=0, le=10_000_000, max_digits=14, decimal_places=2
    )
    years: int = Field(ge=1, le=50)
    annual_return_percent: Decimal = Field(
        default=Decimal("7.0"), ge=-20, le=30, max_digits=5, decimal_places=2
    )
    one_time_contribution_sar: Decimal = Field(
        default=Decimal("0"), ge=0, le=100_000_000, max_digits=14, decimal_places=2
    )
    inflation_percent: Decimal = Field(
        default=Decimal("2.5"), ge=0, le=20, max_digits=5, decimal_places=2
    )
    target_amount_sar: Decimal | None = Field(
        default=None, gt=0, le=1_000_000_000, max_digits=15, decimal_places=2
    )


class WalletDepositConfirmationRequest(StrictModel):
    request_id: UUID
    confirmation_token: str = Field(min_length=32, max_length=4096, repr=False)
    otp_code: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$", repr=False)


def _issue_wallet_deposit_token(
    *,
    session: InteractionSession,
    request_id: UUID,
    source_account_id: UUID,
    amount: Decimal,
) -> str:
    claims = {
        "request_id": str(request_id),
        "source_account_id": str(source_account_id),
        "amount": format(amount.quantize(Decimal("0.01")), "f"),
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "purpose": "wallet_deposit",
    }
    body = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")
    timestamp, signature = sign_message(settings.CONFIRMATION_SIGNING_KEY, body)
    return f"{timestamp}.{encoded}.{signature}"


def _verify_wallet_deposit_token(
    token: str,
    *,
    session: InteractionSession,
    request_id: UUID,
) -> tuple[str, Decimal]:
    try:
        timestamp, encoded, signature = token.split(".", 2)
        body = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        verify_message(
            settings.CONFIRMATION_SIGNING_KEY,
            body,
            timestamp=timestamp,
            signature=signature,
            max_age_seconds=300,
        )
        claims = json.loads(body)
        if (
            claims.get("purpose") != "wallet_deposit"
            or claims.get("request_id") != str(request_id)
            or claims.get("user_id") != session.user_id
            or claims.get("tenant_id") != session.tenant_id
        ):
            raise PermissionError("deposit confirmation does not match this session")
        return str(UUID(claims["source_account_id"])), Decimal(claims["amount"])
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise PermissionError("invalid or expired deposit confirmation") from exc


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


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "nafea_session",
        token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def _session_response(session: InteractionSession, token: str) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        session_token=token,
        language=session.language,
        expires_at=session.expires_at,
    )


def _scopes_for_user(user: AuthenticatedUser) -> tuple[str, ...]:
    # Self-registered profiles remain read-only until their banking identity is verified.
    return settings.demo_scopes if user.verified else ("financial:read",)


@app.post("/api/auth/login", response_model=SessionResponse)
async def login(payload: LoginRequest, response: Response) -> SessionResponse:
    user = await asyncio.to_thread(
        authentication_store.authenticate,
        identifier=payload.identifier,
        password=payload.password,
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    session, token = await _interaction_call(
        interaction_store.create_session,
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        language=payload.language,
        scopes=_scopes_for_user(user),
        ttl_seconds=settings.SESSION_TTL_SECONDS,
    )
    _set_session_cookie(response, token)
    return _session_response(session, token)


@app.post("/api/auth/register", response_model=SessionResponse, status_code=201)
async def register(payload: RegistrationRequest, response: Response) -> SessionResponse:
    try:
        user = await asyncio.to_thread(
            authentication_store.register,
            username=payload.username,
            full_name_ar=payload.full_name_ar,
            full_name_en=payload.full_name_en,
            password=payload.password,
        )
    except RegistrationConflict as error:
        raise HTTPException(status_code=409, detail="username_taken") from error
    session, token = await _interaction_call(
        interaction_store.create_session,
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        language=payload.language,
        scopes=_scopes_for_user(user),
        ttl_seconds=settings.SESSION_TTL_SECONDS,
    )
    _set_session_cookie(response, token)
    return _session_response(session, token)


@app.get("/api/auth/session", response_model=SessionResponse)
async def current_session(request: Request) -> SessionResponse:
    token = _session_token(request)
    session = await require_session(request)
    assert token is not None
    return _session_response(session, token)


@app.post("/api/auth/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    await _interaction_call(interaction_store.revoke_session, _session_token(request))
    response.delete_cookie("nafea_session", path="/", samesite="strict")
    response.status_code = 204
    return response


@app.post("/api/session", response_model=SessionResponse)
async def refresh_session(
    payload: SessionRequest,
    request: Request,
    response: Response,
) -> SessionResponse:
    token = _session_token(request)
    session = await _interaction_call(
        interaction_store.refresh_session,
        token,
        language=payload.language,
        ttl_seconds=settings.SESSION_TTL_SECONDS,
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Authenticated session required")
    assert token is not None
    _set_session_cookie(response, token)
    return _session_response(session, token)


@app.get("/api/active-task")
async def get_active_task(request: Request) -> dict[str, Any]:
    """Return only the current session's resumable task for UI recovery."""

    session = await require_session(request)
    task = await _interaction_call(
        interaction_store.get_active_task, session_id=session.session_id
    )
    if task is None:
        return {"active_task": None}
    return {
        "active_task": {
            "task_id": task.task_id,
            "request_id": task.request_id,
            "status": task.status,
            "pending_event": task.pending_event,
        }
    }


@app.get("/api/dashboard")
async def get_dashboard(request: Request) -> dict[str, Any]:
    """Return a read-only banking snapshot scoped to the authenticated session."""

    session = await require_session(request)
    if "financial:read" not in session.scopes:
        raise HTTPException(status_code=403, detail="Financial read access is required")
    try:
        return await asyncio.to_thread(
            dashboard_store.snapshot,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/investments/projection")
async def get_investment_projection(
    payload: InvestmentProjectionRequest, request: Request
) -> dict[str, Any]:
    """Return a server-calculated illustration based on the live portfolio value."""

    session = await require_session(request)
    if "financial:read" not in session.scopes:
        raise HTTPException(status_code=403, detail="Financial read access is required")
    try:
        return await asyncio.to_thread(
            dashboard_store.investment_projection,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
            monthly_contribution=payload.monthly_contribution_sar,
            years=payload.years,
            annual_return_percent=payload.annual_return_percent,
            one_time_contribution=payload.one_time_contribution_sar,
            inflation_percent=payload.inflation_percent,
            target_amount=payload.target_amount_sar,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/wallet/deposit/request")
async def request_wallet_deposit(
    payload: WalletDepositPreviewRequest, request: Request
) -> dict[str, Any]:
    """Validate the selected bank and amount before asking for an OTP."""

    session = await require_session(request)
    if "financial:write" not in session.scopes:
        raise HTTPException(status_code=403, detail="Financial write access is required")
    try:
        preview = await asyncio.to_thread(
            dashboard_store.preview_wallet_deposit,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
            source_account_id=str(payload.source_account_id),
            amount=payload.amount,
        )
        preview["confirmation_token"] = _issue_wallet_deposit_token(
            session=session,
            request_id=payload.request_id,
            source_account_id=payload.source_account_id,
            amount=payload.amount,
        )
        return preview
    except DepositAccountNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DepositInsufficientFunds as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/wallet/deposit/confirm")
async def confirm_wallet_deposit(
    payload: WalletDepositConfirmationRequest, request: Request
) -> dict[str, Any]:
    """Move the token-bound amount only after the subsequent OTP check."""

    session = await require_session(request)
    if "financial:write" not in session.scopes:
        raise HTTPException(status_code=403, detail="Financial write access is required")
    try:
        source_account_id, amount = _verify_wallet_deposit_token(
            payload.confirmation_token,
            session=session,
            request_id=payload.request_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not hmac.compare_digest(payload.otp_code, settings.DEMO_CONFIRMATION_OTP):
        raise HTTPException(status_code=403, detail="Invalid demo OTP")
    try:
        return await asyncio.to_thread(
            dashboard_store.deposit_to_wallet,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
            source_account_id=source_account_id,
            amount=amount,
            request_id=str(payload.request_id),
        )
    except DepositAccountNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (DepositInsufficientFunds, DepositRequestConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/tasks/{task_id}/latest-event")
async def get_latest_task_event(task_id: str, request: Request) -> dict[str, Any]:
    """Replay a durable task event when a browser WebSocket frame was missed."""

    session = await require_session(request)
    task = await _interaction_call(
        interaction_store.get_task, task_id=task_id, session_id=session.session_id
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found in this session")
    return {
        "event": await _interaction_call(
            interaction_store.latest_task_event,
            task_id=task_id,
            session_id=session.session_id,
        )
    }


@app.post("/api/realtime-token")
async def realtime_connection(request: Request, payload: RealtimeRequest) -> dict[str, str]:
    session = await require_session(request)
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
        # Initial history is exclusively server-owned. Letting a browser append
        # clientContent would bypass the bounded, labeled memory contract.
        allowed = {"realtimeInput", "toolResponse"}
        if len(message) != 1 or next(iter(message)) not in allowed:
            raise ValueError("unsupported realtime client message")
        realtime_input = message.get("realtimeInput")
        if isinstance(realtime_input, dict) and "text" in realtime_input:
            realtime_text = realtime_input["text"]
            if (
                not isinstance(realtime_text, str)
                or len(realtime_text) > settings.VOICE_REALTIME_MAX_TEXT_CHARACTERS
            ):
                raise ValueError("realtime text input is too large")
        await provider.send(raw)


async def _wait_for_provider_setup(provider: Any) -> None:
    """Honor Gemini's setup barrier before sending history or microphone data."""

    raw = await asyncio.wait_for(
        provider.recv(), timeout=settings.REALTIME_SETUP_TIMEOUT_SECONDS
    )
    text = raw if isinstance(raw, str) else raw.decode("utf-8")
    message = json.loads(text)
    if "setupComplete" not in message:
        raise RuntimeError("realtime provider did not acknowledge session setup")


async def _record_realtime_turn(**kwargs: Any) -> None:
    try:
        await _interaction_call(interaction_store.record_voice_turn, **kwargs)
    except Exception as exc:
        logger.warning("Could not persist realtime transcription memory: %s", type(exc).__name__)


async def _relay_provider_to_browser(provider: Any, browser: WebSocket, *, session_id: str) -> None:
    user_transcript: list[str] = []
    assistant_transcript: list[str] = []
    last_user_transcript = ""
    persistence_tasks: set[asyncio.Task[None]] = set()
    async for raw in provider:
        text = raw if isinstance(raw, str) else raw.decode("utf-8")
        outgoing = text
        try:
            message = json.loads(text)
            resumption = message.get("sessionResumptionUpdate") or {}
            if resumption.get("resumable") and resumption.get("newHandle"):
                realtime_resume_handles[session_id] = str(resumption["newHandle"])
            content = message.get("serverContent") or {}
            input_text = (content.get("inputTranscription") or {}).get("text")
            output_text = (content.get("outputTranscription") or {}).get("text")
            if input_text:
                if not user_transcript:
                    last_user_transcript = ""
                user_transcript.append(input_text)
            if output_text:
                assistant_transcript.append(output_text)
            _bind_voice_tool_calls(
                message,
                session_id=session_id,
                transcript="".join(user_transcript) or last_user_transcript,
            )
            if content.get("interrupted"):
                assistant_transcript.clear()
            if content.get("turnComplete"):
                if user_transcript:
                    last_user_transcript = "".join(user_transcript)
                    persistence_tasks.add(
                        asyncio.create_task(
                            _record_realtime_turn(
                                session_id=session_id,
                                role="user",
                                text=last_user_transcript,
                                provenance="provider_input_audio_transcription",
                            )
                        )
                    )
                if assistant_transcript:
                    persistence_tasks.add(
                        asyncio.create_task(
                            _record_realtime_turn(
                                session_id=session_id,
                                role="assistant",
                                text="".join(assistant_transcript),
                                provenance="provider_output_audio_transcription_untrusted",
                            )
                        )
                    )
                user_transcript.clear()
                assistant_transcript.clear()
            outgoing = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        except (json.JSONDecodeError, LookupError, ValueError):
            logger.warning("Ignored invalid realtime transcription memory")
        await browser.send_text(outgoing)
        persistence_tasks = {task for task in persistence_tasks if not task.done()}
    if persistence_tasks:
        await asyncio.gather(*persistence_tasks)


@app.websocket("/api/realtime")
async def realtime_websocket(websocket: WebSocket) -> None:
    session = await _interaction_call(interaction_store.get_session, _websocket_token(websocket))
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
        "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        f"?key={settings.GEMINI_API_KEY}"
    )
    resume_handle = realtime_resume_handles.get(session.session_id)
    try:
        identity = await _interaction_call(
            dashboard_store.user_identity,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
        )
        user_name = _localized_user_name(identity, session.language)
        async with websockets.connect(provider_url, max_size=2_000_000) as provider:
            await provider.send(
                json.dumps(
                    gemini_setup(
                        model=settings.REALTIME_MODEL,
                        language=session.language,
                        voice=settings.REALTIME_VOICE,
                        user_name=user_name,
                        resume_handle=resume_handle,
                        context_trigger_tokens=settings.VOICE_CONTEXT_TRIGGER_TOKENS,
                        context_target_tokens=settings.VOICE_CONTEXT_TARGET_TOKENS,
                    ),
                    ensure_ascii=False,
                )
            )
            await _wait_for_provider_setup(provider)
            if resume_handle is None:
                memory_context = await _interaction_call(
                    interaction_store.grounded_voice_context,
                    session_id=session.session_id,
                    limit=settings.VOICE_MEMORY_CONTEXT_TURNS,
                )
                await provider.send(
                    json.dumps(
                        gemini_initial_history(memory_context),
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
        logger.error("Realtime proxy failed: %s: %s", type(exc).__name__, str(exc))
        await websocket.close(code=1011)
    finally:
        if active_realtime_connections.get(identity_key) is websocket:
            active_realtime_connections.pop(identity_key, None)


@app.post("/api/voice-chat", response_model=VoiceChatResponse)
async def voice_chat(
    request: Request,
    file: UploadFile = File(...),
) -> VoiceChatResponse:
    await require_session(request)
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
    session = await _interaction_call(interaction_store.get_session, _websocket_token(websocket))
    if session is None or not _websocket_origin_allowed(websocket):
        await websocket.close(code=4401)
        return
    await manager.connect(session.session_id, websocket)
    try:
        events = await _interaction_call(
            interaction_store.recent_events, session_id=session.session_id
        )
        for event in events:
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
        inserted = await _interaction_call(interaction_store.record_event, event)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid agent event") from exc
    if inserted:
        if event.event_type in {
            "input_needed",
            "confirmation_needed",
            "completed",
            "rejected",
            "failed",
        }:
            _cancel_task_watchdog(event.task_id)
        if event.event_type in {
            "input_needed",
            "confirmation_needed",
            "completed",
            "rejected",
            "failed",
        }:
            await _interaction_call(
                interaction_store.record_conversation_turn,
                session_id=event.session_id,
                role="assistant",
                text=event.user_safe_summary,
                provenance="signed_agentic_event",
            )
        await manager.send(event.session_id, event.model_dump(mode="json"))
    return {"status": "received" if inserted else "duplicate"}


async def _agentic_post(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float | None = None,
) -> httpx.Response:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    timestamp, signature = sign_message(settings.INTERACTION_SHARED_SECRET, body)
    async with httpx.AsyncClient(
        timeout=timeout_seconds or settings.AGENTIC_TIMEOUT_SECONDS,
        verify=settings.SSL_VERIFY,
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


def _cancel_task_watchdog(task_id: str) -> None:
    watchdog = task_watchdogs.pop(task_id, None)
    if watchdog is not None and watchdog is not asyncio.current_task():
        watchdog.cancel()


async def _task_response_watchdog(
    *,
    task_id: str,
    request_id: str,
    session: InteractionSession,
    delay_seconds: float | None = None,
) -> None:
    try:
        await asyncio.sleep(
            settings.AGENTIC_TIMEOUT_SECONDS if delay_seconds is None else max(0, delay_seconds)
        )
        event = await _interaction_call(
            interaction_store.record_timeout,
            task_id=task_id,
            session_id=session.session_id,
            language=session.language,
        )
        if event is None:
            return
        await _interaction_call(
            interaction_store.record_conversation_turn,
            session_id=session.session_id,
            role="assistant",
            text=event.user_safe_summary,
            provenance="interaction_timeout",
        )
        await manager.send(session.session_id, event.model_dump(mode="json"))
        cancel_payload = {
            "request_id": request_id,
            "session_id": session.session_id,
            "user_id": session.user_id,
            "tenant_id": session.tenant_id,
            "reason_code": "interaction_timeout",
        }
        try:
            response = await _agentic_post(
                f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/tasks/{task_id}/cancel",
                cancel_payload,
                timeout_seconds=5.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Agentic cancellation failed after timeout: %s", type(exc).__name__)
    except asyncio.CancelledError:
        return
    finally:
        if task_watchdogs.get(task_id) is asyncio.current_task():
            task_watchdogs.pop(task_id, None)


def _schedule_task_watchdog(
    *,
    task_id: str,
    request_id: str,
    session: InteractionSession,
    delay_seconds: float | None = None,
) -> None:
    _cancel_task_watchdog(task_id)
    task_watchdogs[task_id] = asyncio.create_task(
        _task_response_watchdog(
            task_id=task_id,
            request_id=request_id,
            session=session,
            delay_seconds=delay_seconds,
        )
    )


async def recover_task_watchdogs() -> None:
    """Restore durable deadlines for tasks that survived an interaction restart."""

    pending = await _interaction_call(
        interaction_store.pending_task_watchdogs,
        timeout_seconds=settings.AGENTIC_TIMEOUT_SECONDS,
    )
    now = time.time()
    for item in pending:
        _schedule_task_watchdog(
            task_id=item.task_id,
            request_id=item.request_id,
            session=item.session,
            delay_seconds=item.deadline_at - now,
        )


@app.post("/api/cancel-task", status_code=202)
async def cancel_task(request: Request, payload: CancelTaskRequest) -> dict[str, Any]:
    session = await require_session(request)
    task = await _interaction_call(
        interaction_store.get_task, task_id=payload.task_id, session_id=session.session_id
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found in this session")
    if task.status in {
        "completed",
        "partially_completed",
        "rejected",
        "failed",
        "timed_out",
    }:
        return {"status": "already_finished"}
    cancel_payload = {
        "request_id": task.request_id,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "reason_code": "user_cancelled",
    }
    try:
        response = await _agentic_post(
            f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/tasks/{task.task_id}/cancel",
            cancel_payload,
            timeout_seconds=5.0,
        )
        response.raise_for_status()
        accepted = bool(response.json().get("cancelled"))
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="The task could not be cancelled yet. Please try again.",
        ) from exc
    _cancel_task_watchdog(task.task_id)
    event = await _interaction_call(
        interaction_store.record_user_cancellation,
        task_id=task.task_id,
        session_id=session.session_id,
        language=session.language,
    )
    if event is not None:
        await manager.send(session.session_id, event.model_dump(mode="json"))
    return {"status": "cancelled" if accepted or event is not None else "already_finished"}


@app.post("/api/new-chat", response_model=SessionResponse)
async def new_chat(request: Request, response: Response) -> SessionResponse:
    token = _session_token(request)
    previous_session = await require_session(request)
    if await _interaction_call(
        interaction_store.get_active_task, session_id=previous_session.session_id
    ) is not None:
        raise HTTPException(status_code=409, detail="Cancel the active request first")
    # A new chat is a new memory and correlation namespace, not merely an empty
    # transcript in the existing session. Preserve only authenticated identity.
    session, new_token = await _interaction_call(
        interaction_store.create_session,
        user_id=previous_session.user_id,
        tenant_id=previous_session.tenant_id,
        language=previous_session.language,
        scopes=previous_session.scopes,
        ttl_seconds=settings.SESSION_TTL_SECONDS,
    )
    await _interaction_call(
        interaction_store.clear_conversation, session_id=previous_session.session_id
    )
    await _interaction_call(interaction_store.revoke_session, token)
    realtime_resume_handles.pop(previous_session.session_id, None)
    _set_session_cookie(response, new_token)
    return _session_response(session, new_token)


@app.post("/api/submit-task", status_code=202)
async def submit_task(request: Request, payload: SubmitTaskRequest) -> dict[str, Any]:
    session = await require_session(request)
    natural_language_request = payload.natural_language_request
    if payload.source == "voice":
        if payload.voice_evidence is None or payload.idempotency_key is None:
            raise HTTPException(
                status_code=422, detail="Signed voice transcript evidence is required"
            )
        try:
            natural_language_request = _verify_voice_evidence(
                payload.voice_evidence,
                session_id=session.session_id,
                call_id=payload.idempotency_key,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
    elif payload.voice_evidence is not None:
        raise HTTPException(
            status_code=422, detail="Voice evidence is only valid for voice requests"
        )
    request_id = str(
        uuid5(NAMESPACE_URL, f"nafea:{session.session_id}:{payload.idempotency_key}")
        if payload.idempotency_key
        else uuid4()
    )
    try:
        await _interaction_call(
            interaction_store.reserve_request,
            session_id=session.session_id,
            request_id=request_id,
            natural_language_request=natural_language_request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    existing = await _interaction_call(
        interaction_store.get_task_by_request,
        request_id=request_id, session_id=session.session_id
    )
    if existing is not None:
        return {
            "request_id": existing.request_id,
            "task_id": existing.task_id,
            "status": "accepted",
            "user_safe_message": "The existing financial task was returned.",
        }
    if await _interaction_call(
        interaction_store.get_active_task, session_id=session.session_id
    ) is not None:
        raise HTTPException(
            status_code=409,
            detail="Finish the active financial task before starting another one",
        )
    prior_user_statements = await _interaction_call(
        interaction_store.recent_user_statements,
        session_id=session.session_id,
        limit=settings.VOICE_MEMORY_CONTEXT_TURNS,
    )
    # Provider input transcription is the canonical voice-memory record. Saving
    # the tool argument too would store the same spoken turn twice. Chat has no
    # provider transcription, so it is persisted here instead.
    if payload.source == "chat":
        await _interaction_call(
            interaction_store.record_conversation_turn,
            session_id=session.session_id,
            role="user",
            text=natural_language_request,
            provenance="chat_user_message",
        )
    agentic_payload = {
        "request_id": request_id,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "language": session.language,
        "natural_language_request": natural_language_request,
        "original_user_message": natural_language_request,
        "authorization": {
            "scopes": list(session.scopes),
            "authenticated_at": session.authenticated_at,
            "assurance_level": "password_authenticated",
        },
        "metadata": {
            "source_provider": f"nafea-{payload.source}",
            "conversation_context_summary": json.dumps(
                {"recent_user_statements": prior_user_statements},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "conversation_user_statements": prior_user_statements,
        },
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
        await _interaction_call(
            interaction_store.record_task,
            session_id=session.session_id, request_id=request_id, task_id=task_id
        )
        _schedule_task_watchdog(
            task_id=task_id,
            request_id=request_id,
            session=session,
        )
        return accepted
    except httpx.TimeoutException as exc:
        logger.error("Agentic submit timed out")
        raise HTTPException(
            status_code=504,
            detail=(
                "This is taking longer than 20 seconds, so I cancelled the request. "
                "Nothing should be treated as completed."
            ),
        ) from exc
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("Agentic submit failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail="Agentic layer did not accept the task"
        ) from exc


@app.post("/api/resume-task", status_code=202)
async def resume_task(request: Request, payload: ResumeTaskRequest) -> dict[str, str]:
    session = await require_session(request)
    task = await _interaction_call(
        interaction_store.get_task, task_id=payload.task_id, session_id=session.session_id
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found in this session")
    event = task.pending_event
    if not event or event.get("event_type") != "input_needed":
        raise HTTPException(status_code=409, detail="Task is not waiting for clarification")
    clarification_id = event.get("details", {}).get("clarification_id")
    if not clarification_id:
        raise HTTPException(status_code=409, detail="Clarification event is incomplete")
    expected_answer = event.get("details", {}).get("expected_answer")
    normalized_answer = _normalize_clarification_answer(payload.user_answer, expected_answer)
    resume_payload = {
        "request_id": task.request_id,
        "session_id": session.session_id,
        "user_id": session.user_id,
        "tenant_id": session.tenant_id,
        "clarification_id": clarification_id,
        "answer": normalized_answer,
    }
    try:
        response = await _agentic_post(
            f"{settings.AGENTIC_BASE_URL.rstrip('/')}/agentic/tasks/{task.task_id}/resume",
            resume_payload,
        )
        if response.status_code != 202:
            response.raise_for_status()
            raise ValueError("unexpected resume response")
        await _interaction_call(
            interaction_store.clear_pending,
            task_id=task.task_id,
            session_id=session.session_id,
            expected_event=event,
        )
        _schedule_task_watchdog(
            task_id=task.task_id,
            request_id=task.request_id,
            session=session,
        )
        return {"status": "resumed"}
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="The continuation timed out after 20 seconds and was cancelled.",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Agentic layer rejected the clarification"
        ) from exc


@app.post("/api/confirm-task", status_code=202)
async def confirm_task(request: Request, payload: ConfirmTaskRequest) -> dict[str, str]:
    session = await require_session(request)
    task = await _interaction_call(
        interaction_store.get_task, task_id=payload.task_id, session_id=session.session_id
    )
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
            await _interaction_call(
                interaction_store.clear_pending,
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
        await _interaction_call(
            interaction_store.clear_pending,
            task_id=task.task_id,
            session_id=session.session_id,
            expected_event=event,
        )
        _schedule_task_watchdog(
            task_id=task.task_id,
            request_id=task.request_id,
            session=session,
        )
        return {"status": "confirmed"}
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="The confirmation timed out after 20 seconds and was cancelled.",
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Agentic layer rejected the confirmation"
        ) from exc
