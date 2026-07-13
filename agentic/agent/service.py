from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from langgraph.types import Command
from sqlalchemy import select

from agentic.agent.graph import initial_state
from agentic.agent.report import AgentReport
from agentic.api.schemas import (
    AcceptedTask,
    AgentEvent,
    AgentEventType,
    AgenticRequest,
    AuthorizationContext,
    ResumeTaskRequest,
    TaskStatus,
)
from agentic.config.loader import AppConfig
from agentic.memory.extraction import MemoryExtractor
from agentic.memory.policy import MemoryPolicy, MemoryPolicyError
from agentic.memory.service import MemoryService
from agentic.persistence.database import Database
from agentic.persistence.models import ToolExecutionRow
from agentic.policy.output_policy import OutputPolicy
from agentic.persistence.repositories.clarifications import ClarificationRepository
from agentic.persistence.repositories.tasks import TaskRepository
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext
from agentic.security.redaction import redact_text
from agentic.security.rate_limit import InMemoryRateLimiter
from agentic.telemetry.events import EventPublisher
from agentic.telemetry.metrics import TASK_DURATION, TASKS
from agentic.tools.guard import AgentRuntimeContext


class AgentService:
    def __init__(
        self,
        *,
        graph: Any,
        database: Database,
        config: AppConfig,
        confirmation_signer: ConfirmationSigner,
        events: EventPublisher,
        memory_extractor: MemoryExtractor | None = None,
        rate_limiter: InMemoryRateLimiter | None = None,
    ) -> None:
        self.graph = graph
        self.database = database
        self.config = config
        self.confirmation_signer = confirmation_signer
        self.events = events
        self.memory_extractor = memory_extractor
        self.memory_policy = MemoryPolicy(
            allowed_types=config.policies.memory.allowed_types,
            forbidden_key_fragments=config.policies.memory.forbidden_key_fragments,
        )
        self.output_policy = OutputPolicy(config.limits.report)
        self.rate_limiter = rate_limiter or InMemoryRateLimiter(config.limits.rate_limit)
        public_config = config.model_dump(mode="json", exclude={"secrets"})
        self.config_hash = hashlib.sha256(
            json.dumps(public_config, sort_keys=True).encode()
        ).hexdigest()
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def submit(self, request: AgenticRequest, *, background: bool = True) -> AcceptedTask:
        if len(request.natural_language_request) > self.config.limits.task.max_request_characters:
            raise ValueError("request exceeds configured maximum length")
        await self.rate_limiter.acquire(tenant_id=request.tenant_id, user_id=request.user_id)
        sanitized_request = request.model_copy(
            update={
                "natural_language_request": redact_text(request.natural_language_request),
                "original_user_message": redact_text(request.original_user_message),
            }
        )
        try:
            accepted, task_id = await self._accept(sanitized_request)
        except Exception:
            await self.rate_limiter.release(
                tenant_id=request.tenant_id, user_id=request.user_id
            )
            raise
        if background:
            task_handle = asyncio.create_task(
                self._run_new_with_release(task_id, sanitized_request)
            )
            self._background_tasks.add(task_handle)
            task_handle.add_done_callback(self._background_tasks.discard)
        else:
            try:
                await self._run_new(task_id, sanitized_request)
            finally:
                await self.rate_limiter.release(
                    tenant_id=request.tenant_id, user_id=request.user_id
                )
        return accepted

    async def _accept(self, request: AgenticRequest) -> tuple[AcceptedTask, str]:
        async with self.database.session() as session:
            task = await TaskRepository(session).create(request, config_hash=self.config_hash)
            if task.expires_at is None:
                task.expires_at = datetime.now(timezone.utc) + timedelta(
                    days=self.config.limits.memory.task_checkpoint_ttl_days
                )
            task_id = task.id
        accepted = AcceptedTask(
            request_id=request.request_id,
            task_id=UUID(task_id),
            status="accepted",
            user_safe_message="The financial task was accepted.",
        )
        await self.events.publish(
            AgentEvent(
                task_id=UUID(task_id),
                request_id=request.request_id,
                session_id=request.session_id,
                event_type=AgentEventType.ACCEPTED,
                user_safe_summary="The request was accepted.",
            )
        )
        TASKS.labels(outcome="accepted", language=request.language).inc()
        return accepted, task_id

    async def _run_new_with_release(self, task_id: str, request: AgenticRequest) -> None:
        try:
            await self._run_new(task_id, request)
        finally:
            await self.rate_limiter.release(
                tenant_id=request.tenant_id, user_id=request.user_id
            )

    async def _run_new(self, task_id: str, request: AgenticRequest) -> None:
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(task_id, tenant_id=request.tenant_id, user_id=request.user_id)
            if row is None:
                raise LookupError("task not found")
            if TaskStatus(row.status) != TaskStatus.RECEIVED:
                return
            await repository.transition(row, TaskStatus.VALIDATING)
            await repository.transition(row, TaskStatus.RUNNING)
        state = initial_state(
            task_id=task_id,
            request_id=str(request.request_id),
            session_id=str(request.session_id),
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            language=request.language,
            request=request.natural_language_request,
            context=(
                [{"type": "interaction_summary", "text": request.metadata.conversation_context_summary}]
                if request.metadata.conversation_context_summary
                else []
            ),
        )
        auth = AuthContext(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            session_id=str(request.session_id),
            scopes=request.authorization.scopes,
        )
        runtime_context = AgentRuntimeContext(
            auth=auth,
            task_id=task_id,
            session_factory=self.database.session_factory,
            config=self.config,
            confirmation_signer=self.confirmation_signer,
            initial_authorization_token=(
                request.confirmation.authorization_token if request.confirmation else None
            ),
        )
        async with self.database.session() as session:
            memories = await MemoryService(session, self.memory_policy).list_for_user(
                auth=auth, limit=self.config.limits.memory.recent_messages
            )
        state["relevant_context"].extend(
            {
                "type": item.memory_type,
                "value": item.value,
                "provenance": item.provenance,
                "verified": item.verified,
            }
            for item in memories
        )
        # Rebuild messages so curated memories are present as explicitly untrusted context.
        state = initial_state(
            task_id=task_id,
            request_id=str(request.request_id),
            session_id=str(request.session_id),
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            language=request.language,
            request=request.natural_language_request,
            context=state["relevant_context"],
        )
        await self._invoke(task_id, request, state, runtime_context)

    async def resume(self, task_id: UUID, request: ResumeTaskRequest) -> None:
        await self.rate_limiter.acquire(tenant_id=request.tenant_id, user_id=request.user_id)
        try:
            await self._resume(task_id, request)
        finally:
            await self.rate_limiter.release(
                tenant_id=request.tenant_id, user_id=request.user_id
            )

    async def _resume(self, task_id: UUID, request: ResumeTaskRequest) -> None:
        task_id_str = str(task_id)
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(
                task_id_str, tenant_id=request.tenant_id, user_id=request.user_id
            )
            if row is None or row.session_id != str(request.session_id):
                raise LookupError("task not found")
            if row.request_id != str(request.request_id):
                raise PermissionError("resume request does not match the original task")
            current = TaskStatus(row.status)
            if request.clarification_id:
                if current != TaskStatus.WAITING_FOR_INPUT:
                    raise ValueError("task is not waiting for clarification")
                await ClarificationRepository(session).answer(
                    str(request.clarification_id), task_id=task_id_str, answer=request.answer
                )
                resume_value = request.answer
            else:
                if current != TaskStatus.WAITING_FOR_CONFIRMATION:
                    raise ValueError("task is not waiting for confirmation")
                resume_value = request.authorization_token
            await repository.transition(row, TaskStatus.RUNNING)
            original = AgenticRequest(
                request_id=UUID(row.request_id),
                session_id=UUID(row.session_id),
                user_id=row.user_id,
                tenant_id=row.tenant_id,
                language=row.language,
                natural_language_request=row.original_request,
                original_user_message=row.original_request,
                authorization=AuthorizationContext(
                    scopes=frozenset(row.authorized_scopes),
                    authenticated_at=row.created_at,
                    assurance_level=row.assurance_level,
                ),
            )
        auth = AuthContext(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            session_id=str(request.session_id),
            scopes=original.authorization.scopes,
        )
        runtime_context = AgentRuntimeContext(
            auth=auth,
            task_id=task_id_str,
            session_factory=self.database.session_factory,
            config=self.config,
            confirmation_signer=self.confirmation_signer,
        )
        await self._invoke(
            task_id_str,
            original,
            Command(resume=resume_value),
            runtime_context,
        )

    async def delete_memory(self, *, tenant_id: str, user_id: str, session_id: str) -> int:
        auth = AuthContext(user_id, tenant_id, session_id, frozenset())
        async with self.database.session() as session:
            return await MemoryService(session, self.memory_policy).delete_for_user(auth=auth)

    async def _invoke(
        self,
        task_id: str,
        request: AgenticRequest,
        graph_input: Any,
        runtime_context: AgentRuntimeContext,
    ) -> None:
        graph_config = {"configurable": {"thread_id": task_id}}
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.config.limits.task.max_runtime_seconds):
                result = await self.graph.ainvoke(
                    graph_input,
                    config=graph_config,
                    context=runtime_context,
                )
            interrupt_payload = self._interrupt_payload(result)
            if interrupt_payload:
                await self._record_interrupt(task_id, request, interrupt_payload)
                return
            await self._record_completion(task_id, request, result)
        except Exception as exc:
            await self._record_failure(task_id, request, type(exc).__name__)
            raise
        finally:
            TASK_DURATION.observe(time.monotonic() - started)

    @staticmethod
    def _interrupt_payload(result: Any) -> dict[str, Any] | None:
        if not isinstance(result, dict) or "__interrupt__" not in result:
            return None
        interrupts = result["__interrupt__"]
        if not interrupts:
            return None
        item = interrupts[0]
        value = getattr(item, "value", item)
        return value if isinstance(value, dict) else {"kind": "unknown", "value": value}

    async def _record_interrupt(
        self, task_id: str, request: AgenticRequest, payload: dict[str, Any]
    ) -> None:
        kind = payload.get("kind")
        if kind == "clarification":
            target = TaskStatus.WAITING_FOR_INPUT
            event_type = AgentEventType.INPUT_NEEDED
            async with self.database.session() as session:
                await ClarificationRepository(session).create(
                    clarification_id=payload["clarification_id"],
                    task_id=task_id,
                    question=payload["question"],
                    reason_code=payload["reason_code"],
                    expected_answer=payload["expected_answer"],
                    expires_in_seconds=payload["expires_in_seconds"],
                )
        elif kind == "confirmation":
            target = TaskStatus.WAITING_FOR_CONFIRMATION
            event_type = AgentEventType.CONFIRMATION_NEEDED
        else:
            raise ValueError("unsupported graph interrupt")
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(task_id, tenant_id=request.tenant_id, user_id=request.user_id)
            if row is None:
                raise LookupError("task not found")
            await repository.transition(row, target, payload=payload)
        await self.events.publish(
            AgentEvent(
                task_id=UUID(task_id),
                request_id=request.request_id,
                session_id=request.session_id,
                event_type=event_type,
                user_safe_summary=(
                    payload.get("question", "Confirmation is required before continuing.")
                ),
                details=payload,
            )
        )
        TASKS.labels(outcome=target.value, language=request.language).inc()

    async def _extract_memories(self, request: AgenticRequest, task_id: str) -> None:
        if self.memory_extractor is None:
            return
        try:
            candidates = await self.memory_extractor.extract(request.natural_language_request)
        except Exception:
            return
        auth = AuthContext(
            request.user_id,
            request.tenant_id,
            str(request.session_id),
            request.authorization.scopes,
        )
        async with self.database.session() as session:
            service = MemoryService(session, self.memory_policy)
            for candidate in candidates:
                try:
                    await service.put(
                        auth=auth,
                        memory_type=candidate.memory_type,
                        value=candidate.value,
                        provenance="explicit_user_statement",
                        confidence=candidate.confidence,
                        sensitivity="low",
                        consent_basis="explicit_request_text",
                        source_task_id=task_id,
                        verified=True,
                    )
                except MemoryPolicyError:
                    continue

    async def _record_completion(
        self, task_id: str, request: AgenticRequest, result: dict[str, Any]
    ) -> None:
        report = result.get("final_report")
        if not isinstance(report, AgentReport):
            report = AgentReport.model_validate(report)
        report = self.output_policy.validate(report)
        async with self.database.session() as session:
            execution_result = await session.scalars(
                select(ToolExecutionRow).where(ToolExecutionRow.task_id == task_id)
            )
            executions = list(execution_result)
        authoritative_receipts = {
            row.receipt_id for row in executions if row.receipt_id and row.status == "completed"
        }
        if not set(report.receipt_ids).issubset(authoritative_receipts):
            raise ValueError("report contains a receipt not returned by an authoritative tool")
        required_tool_names = self.config.policies.financial_actions.require_authoritative_receipt
        required_receipts = {
            row.receipt_id
            for row in executions
            if row.tool_name in required_tool_names and row.status == "completed" and row.receipt_id
        }
        if not required_receipts.issubset(set(report.receipt_ids)):
            raise ValueError("report omitted an authoritative financial-action receipt")
        target = {
            "completed": TaskStatus.COMPLETED,
            "partially_completed": TaskStatus.PARTIALLY_COMPLETED,
            "rejected": TaskStatus.REJECTED,
            "failed": TaskStatus.FAILED,
        }[report.status]
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(task_id, tenant_id=request.tenant_id, user_id=request.user_id)
            if row is None:
                raise LookupError("task not found")
            row.final_report = report.model_dump(mode="json")
            row.intent = result["intent"]["intent"] if result.get("intent") else None
            row.risk = result["risk"]["level"] if result.get("risk") else None
            await repository.transition(row, target, payload={"report": row.final_report})
        event_type = {
            TaskStatus.COMPLETED: AgentEventType.COMPLETED,
            TaskStatus.PARTIALLY_COMPLETED: AgentEventType.COMPLETED,
            TaskStatus.REJECTED: AgentEventType.REJECTED,
            TaskStatus.FAILED: AgentEventType.FAILED,
        }[target]
        await self.events.publish(
            AgentEvent(
                task_id=UUID(task_id),
                request_id=request.request_id,
                session_id=request.session_id,
                event_type=event_type,
                user_safe_summary=report.summary,
                details={"report": report.model_dump(mode="json")},
            )
        )
        TASKS.labels(outcome=target.value, language=request.language).inc()
        if target in {TaskStatus.COMPLETED, TaskStatus.PARTIALLY_COMPLETED}:
            await self._extract_memories(request, task_id)

    async def _record_failure(
        self, task_id: str, request: AgenticRequest, error_code: str
    ) -> None:
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(task_id, tenant_id=request.tenant_id, user_id=request.user_id)
            if row is not None and TaskStatus(row.status) not in {
                TaskStatus.COMPLETED,
                TaskStatus.PARTIALLY_COMPLETED,
                TaskStatus.REJECTED,
                TaskStatus.FAILED,
                TaskStatus.EXPIRED,
            }:
                await repository.transition(
                    row, TaskStatus.FAILED, payload={"error_code": error_code}
                )
        await self.events.publish(
            AgentEvent(
                task_id=UUID(task_id),
                request_id=request.request_id,
                session_id=request.session_id,
                event_type=AgentEventType.FAILED,
                user_safe_summary="The financial task could not be completed safely.",
                details={"error_code": error_code},
            )
        )
        TASKS.labels(outcome="failed", language=request.language).inc()

    async def wait_for_background_tasks(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks), return_exceptions=True)
