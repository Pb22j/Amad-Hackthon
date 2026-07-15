"""FastAPI composition root for the financial agentic service.

This module intentionally performs dependency wiring only. Request execution
lives in :mod:`agentic.agent.service`; graph construction lives in
:mod:`agentic.agent.graph`; and every external financial tool is wrapped by the
security boundary in :mod:`agentic.tools.guard` before it reaches the model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from langchain_core.tools import BaseTool

from agentic import __version__
from agentic.agent.graph import build_financial_agent
from agentic.agent.service import AgentService
from agentic.api.schemas import (
    AgenticRequest,
    HealthResponse,
    MemoryDeleteRequest,
    ResumeTaskRequest,
    TaskStatusRequest,
    TaskStatusResponse,
)
from agentic.config.loader import AppConfig, load_config
from agentic.llm.factory import ModelFactory
from agentic.memory.extraction import LLMMemoryExtractor
from agentic.persistence.checkpointer import postgres_checkpointer
from agentic.persistence.database import Database
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.signing import InteractionSignatureVerifier
from agentic.security.rate_limit import RateLimitError
from agentic.telemetry.events import InMemoryEventPublisher, WebhookEventPublisher
from agentic.telemetry.logging import configure_logging
from agentic.tools.metadata import ToolMetadata
from agentic.tools.guard import ToolGuardError
from agentic.tools.provider import load_tool_bundle


def create_app(
    *,
    service: AgentService | None = None,
    config: AppConfig | None = None,
    external_tools: Sequence[BaseTool] | None = None,
    tool_metadata: Sequence[ToolMetadata] | None = None,
    signature_verifier: InteractionSignatureVerifier | None = None,
) -> FastAPI:
    """Build the API and initialize production dependencies during lifespan.

    Tests may inject a prebuilt ``service`` or explicit tools. Normal startup
    discovers the list exported by the root ``tools`` package, unless
    ``AGENTIC_TOOL_PROVIDER`` selects a different provider.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            app.state.agent_service = service
            app.state.config = config or service.config
            app.state.signature_verifier = signature_verifier
            start_worker = getattr(service, "start_event_delivery_worker", None)
            if start_worker is not None:
                start_worker()
            try:
                yield
                await service.wait_for_background_tasks()
            finally:
                stop_worker = getattr(service, "stop_event_delivery_worker", None)
                if stop_worker is not None:
                    await stop_worker()
            return

        runtime_config = config or load_config()
        configure_logging()
        database = Database(
            runtime_config.secrets.database_url.get_secret_value(),
            pool_size=runtime_config.app.database.pool_size,
            max_overflow=runtime_config.app.database.max_overflow,
            pool_timeout=runtime_config.app.database.pool_timeout_seconds,
            echo=runtime_config.app.database.echo,
        )
        stack = AsyncExitStack()
        checkpointer = await stack.enter_async_context(
            postgres_checkpointer(
                runtime_config.secrets.langgraph_database_url.get_secret_value(),
                encryption_key=(
                    runtime_config.secrets.checkpoint_encryption_key.get_secret_value()
                    if runtime_config.secrets.checkpoint_encryption_key
                    else ""
                ),
                setup=runtime_config.app.service.environment == "development",
            )
        )
        models = ModelFactory(runtime_config.llm)
        if external_tools is None:
            bundle = load_tool_bundle(
                runtime_config.app.agent.tool_provider,
                runtime_config.tools.tools,
                require_tools=runtime_config.app.service.environment == "production",
            )
            runtime_tools = bundle.tools
            runtime_metadata = bundle.metadata
        else:
            runtime_tools = external_tools
            runtime_metadata = tool_metadata or ()
        graph = build_financial_agent(
            primary_model=models.create("primary"),
            classifier_model=models.create("intent_classifier"),
            external_tools=runtime_tools,
            tool_metadata=runtime_metadata,
            config=runtime_config,
            checkpointer=checkpointer,
            fallback_models=models.create_fallbacks("primary"),
        )
        signer = ConfirmationSigner(
            runtime_config.secrets.confirmation_signing_key.get_secret_value()
        )
        if runtime_config.secrets.interaction_event_webhook_url:
            publisher = WebhookEventPublisher(
                runtime_config.secrets.interaction_event_webhook_url,
                runtime_config.secrets.interaction_shared_secret.get_secret_value(),
            )
        else:
            publisher = InMemoryEventPublisher()
        runtime_service = AgentService(
            graph=graph,
            database=database,
            config=runtime_config,
            confirmation_signer=signer,
            events=publisher,
            memory_extractor=LLMMemoryExtractor(models.create("memory_extractor")),
        )
        app.state.agent_service = runtime_service
        app.state.config = runtime_config
        app.state.signature_verifier = signature_verifier or InteractionSignatureVerifier(
            runtime_config.secrets.interaction_shared_secret.get_secret_value()
        )
        runtime_service.start_event_delivery_worker()
        try:
            yield
            await runtime_service.wait_for_background_tasks()
        finally:
            await runtime_service.stop_event_delivery_worker()
            if isinstance(publisher, WebhookEventPublisher):
                await publisher.close()
            await database.dispose()
            await stack.aclose()

    app = FastAPI(
        title="Amad Financial Agent",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    app.mount("/metrics", make_asgi_app())

    @app.exception_handler(PermissionError)
    async def permission_error_handler(_: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(LookupError)
    async def lookup_error_handler(_: Request, __: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "task not found"})

    @app.exception_handler(RateLimitError)
    async def rate_limit_error_handler(_: Request, exc: RateLimitError) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    async def verify_request_signature(
        request: Request,
        body: bytes,
        timestamp: str | None,
        signature: str | None,
    ) -> None:
        runtime_config: AppConfig = request.app.state.config
        if not runtime_config.app.agent.require_signed_interaction_requests:
            return
        if not timestamp or not signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="signed interaction request required",
            )
        verifier: InteractionSignatureVerifier | None = request.app.state.signature_verifier
        if verifier is None:
            raise HTTPException(status_code=503, detail="signature verifier unavailable")
        try:
            verifier.verify(body, timestamp, signature)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.post("/agentic/request", status_code=status.HTTP_202_ACCEPTED)
    async def submit_task(
        request: Request,
        x_interaction_timestamp: str | None = Header(default=None),
        x_interaction_signature: str | None = Header(default=None),
    ) -> Any:
        body = await request.body()
        await verify_request_signature(
            request, body, x_interaction_timestamp, x_interaction_signature
        )
        try:
            payload = AgenticRequest.model_validate_json(body)
            service_instance: AgentService = request.app.state.agent_service
            return await service_instance.submit(payload, background=True)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/agentic/tasks/{task_id}/resume", status_code=status.HTTP_202_ACCEPTED)
    async def resume_task(
        task_id: UUID,
        request: Request,
        x_interaction_timestamp: str | None = Header(default=None),
        x_interaction_signature: str | None = Header(default=None),
    ) -> Response:
        body = await request.body()
        await verify_request_signature(
            request, body, x_interaction_timestamp, x_interaction_signature
        )
        try:
            payload = ResumeTaskRequest.model_validate_json(body)
            service_instance: AgentService = request.app.state.agent_service
            await service_instance.resume(task_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ToolGuardError:
            # The service has already persisted a terminal failed state and
            # delivered its user-safe event. A resume remains accepted from the
            # interaction layer's perspective; surfacing the internal guard as
            # a 500/502 only creates a duplicate, misleading transport failure.
            pass
        return Response(status_code=status.HTTP_202_ACCEPTED)

    @app.post(
        "/agentic/tasks/{task_id}/status",
        response_model=TaskStatusResponse,
        include_in_schema=False,
    )
    async def evaluation_task_status(
        task_id: UUID,
        request: Request,
        x_interaction_timestamp: str | None = Header(default=None),
        x_interaction_signature: str | None = Header(default=None),
    ) -> TaskStatusResponse:
        """Poll a task from the standalone evaluator; disabled in production."""

        runtime_config: AppConfig = request.app.state.config
        if runtime_config.app.service.environment == "production":
            raise HTTPException(status_code=404, detail="not found")
        body = await request.body()
        await verify_request_signature(
            request, body, x_interaction_timestamp, x_interaction_signature
        )
        try:
            payload = TaskStatusRequest.model_validate_json(body)
            service_instance: AgentService = request.app.state.agent_service
            return await service_instance.get_task_status(task_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/agentic/memory", status_code=status.HTTP_200_OK)
    async def delete_memory(
        request: Request,
        x_interaction_timestamp: str | None = Header(default=None),
        x_interaction_signature: str | None = Header(default=None),
    ) -> dict[str, int]:
        body = await request.body()
        await verify_request_signature(
            request, body, x_interaction_timestamp, x_interaction_signature
        )
        payload = MemoryDeleteRequest.model_validate_json(body)
        service_instance: AgentService = request.app.state.agent_service
        deleted = await service_instance.delete_memory(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            session_id=str(payload.session_id),
        )
        return {"deleted": deleted}

    return app
