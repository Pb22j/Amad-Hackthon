"""HTTP boundary for the agentic financial service.

The interaction layer talks to this module using one intentionally small,
natural-language-first contract.  Workflow code is kept behind
``AgenticServiceBoundary`` so the HTTP API does not need to know whether a
task is handled by an in-memory demo runner, SQLite-backed worker, or a live
provider integration.
"""

from __future__ import annotations

import inspect
import hmac
from collections.abc import Awaitable
from typing import Any, Literal, Protocol, TypeVar
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class ConfirmationPayload(BaseModel):
    """Conversation-level confirmation supplied by the interaction layer.

    In live mode, ``required=true`` plus ``received=true`` records the app-level
    confirmation of this exact idempotent request. It is never bank consent or
    strong customer authentication; those remain provider-bound context.
    """

    model_config = ConfigDict(extra="forbid")

    required: bool = False
    received: bool = False


class RequestMetadataPayload(BaseModel):
    """Non-sensitive request metadata accepted at the HTTP boundary."""

    model_config = ConfigDict(extra="forbid")

    created_at: str = Field(min_length=1)
    source_provider: str = Field(min_length=1)
    conversation_context_summary: str = ""


class AgenticRequestPayload(BaseModel):
    """Wire format shared with ``user_interaction_layer``."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    channel: Literal["chat", "voice"]
    language: Literal["en", "ar"]
    natural_language_request: str = Field(min_length=1)
    original_user_message: str = Field(min_length=1)
    confirmation: ConfirmationPayload = Field(default_factory=ConfirmationPayload)
    metadata: RequestMetadataPayload


class AgenticAcknowledgement(BaseModel):
    """Immediate response to a successfully persisted request."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    status: Literal["accepted", "rejected"]
    user_safe_message: str = ""


class AgenticServiceBoundary(Protocol):
    """Minimal application-service contract consumed by this API.

    Methods can be synchronous or asynchronous.  The concrete service owns
    idempotency, task persistence, authorization, and all provider work.
    """

    def submit(self, payload: dict[str, Any]) -> dict[str, Any] | Awaitable[dict[str, Any]]:
        """Persist a request and return its immediate acknowledgement."""

    def get_task(
        self, task_id: str, user_id: str | None = None
    ) -> dict[str, Any] | None | Awaitable[dict[str, Any] | None]:
        """Return a user-scoped task snapshot, if it exists."""

    def capabilities(self) -> dict[str, Any] | Awaitable[dict[str, Any]]:
        """Return the currently enabled capability matrix."""


T = TypeVar("T")


async def _resolve(value: T | Awaitable[T]) -> T:
    """Accept both simple test doubles and async production services."""

    if inspect.isawaitable(value):
        return await value
    return value


class PlaceholderAgenticService:
    """Small in-memory fallback for local HTTP-contract smoke tests.

    It never interprets or executes a financial request.  Production wiring
    should pass the real ``AgenticService`` into :func:`create_app`.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._acknowledgements: dict[str, dict[str, Any]] = {}

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self._acknowledgements.get(payload["request_id"])
        if existing is not None:
            return existing

        task_id = str(uuid4())
        acknowledgement = {
            "request_id": payload["request_id"],
            "task_id": task_id,
            "status": "accepted",
            "user_safe_message": "Your request was accepted and is being processed.",
        }
        self._acknowledgements[payload["request_id"]] = acknowledgement
        self._tasks[task_id] = {
            "task_id": task_id,
            "request_id": payload["request_id"],
            "session_id": payload["session_id"],
            "user_id": payload["user_id"],
            "state": "accepted",
        }
        return acknowledgement

    def get_task(self, task_id: str, user_id: str | None = None) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if task is None or (user_id is not None and task["user_id"] != user_id):
            return None
        return task

    def capabilities(self) -> dict[str, Any]:
        return {
            "mode": "placeholder",
            "ready_for_live_money": False,
            "capabilities": {},
        }


def create_app(service: AgenticServiceBoundary | None = None) -> FastAPI:
    """Create the Agentic FastAPI app using the supplied application service."""

    application_service = service or PlaceholderAgenticService()
    app = FastAPI(title="Nafi Agentic Financial Service", version="0.2.0")
    app.state.agentic_service = application_service

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness() -> Any:
        readiness_method = getattr(application_service, "readiness", None)
        if readiness_method is None:
            return {"status": "ready"}
        result = await _resolve(readiness_method())
        encoded = jsonable_encoder(result)
        if encoded.get("status") != "ready":
            return JSONResponse(status_code=503, content=encoded)
        return encoded

    @app.get("/agentic/capabilities")
    async def capabilities() -> Any:
        return jsonable_encoder(await _resolve(application_service.capabilities()))

    @app.post(
        "/agentic/request",
        response_model=AgenticAcknowledgement,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def submit_request(
        payload: AgenticRequestPayload,
        webhook_secret: str | None = Header(default=None, alias="X-Agentic-Webhook-Secret"),
    ) -> AgenticAcknowledgement:
        try:
            settings = getattr(application_service, "settings", None)
            expected_secret = getattr(settings, "request_webhook_secret", "")
            if expected_secret and not hmac.compare_digest(expected_secret, webhook_secret or ""):
                raise HTTPException(status_code=401, detail="Unauthorized agentic request")
            result = await _resolve(application_service.submit(payload.model_dump(mode="json")))
            return AgenticAcknowledgement.model_validate(result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/agentic/tasks/{task_id}")
    async def get_task(
        task_id: str,
        user_id: str = Query(min_length=1),
        webhook_secret: str | None = Header(default=None, alias="X-Agentic-Webhook-Secret"),
    ) -> Any:
        settings = getattr(application_service, "settings", None)
        expected_secret = getattr(settings, "request_webhook_secret", "")
        if expected_secret and not hmac.compare_digest(expected_secret, webhook_secret or ""):
            raise HTTPException(status_code=401, detail="Unauthorized agentic request")
        task = await _resolve(application_service.get_task(task_id, user_id))
        if task is None:
            # Do not reveal whether a task exists for a different user.
            raise HTTPException(status_code=404, detail="Task not found")
        return jsonable_encoder(task)

    return app


def create_default_app() -> FastAPI:
    """Build the runnable mock MVP for ``uvicorn agentic_service.api:app``."""
    from .service import AgenticService

    return create_app(AgenticService())


# Both the documented runner and direct Uvicorn invocation now execute the
# real mock-backed MVP rather than a no-op contract placeholder.
app = create_default_app()

# Match the interaction layer's factory naming and make integration ergonomic.
create_fastapi_app = create_app
