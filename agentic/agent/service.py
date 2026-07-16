"""Application service coordinating durable financial-agent task lifecycles.

``AgentService`` is the bridge between the stateless HTTP API and the resumable
LangGraph. It persists task transitions, scopes memory, constructs trusted
runtime identity, records interrupts, validates reports, and publishes safe
events. It never asks the end user directly; that remains the interaction
layer's responsibility.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import time
from decimal import Decimal, InvalidOperation
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
    CancelTaskRequest,
    RequestMetadata,
    ResumeTaskRequest,
    TERMINAL_TASK_STATUSES,
    TaskStatus,
    TaskStatusRequest,
    TaskStatusResponse,
)
from agentic.config.loader import AppConfig
from agentic.memory.extraction import MemoryExtractor
from agentic.memory.policy import MemoryPolicy, MemoryPolicyError
from agentic.memory.service import MemoryService
from agentic.persistence.database import Database
from agentic.persistence.models import (
    AgentTaskRow,
    EventOutboxRow,
    TaskEventRow,
    ToolExecutionRow,
)
from agentic.policy.output_policy import OutputPolicy
from agentic.persistence.repositories.clarifications import ClarificationRepository
from agentic.persistence.repositories.outbox import EventOutboxRepository
from agentic.persistence.repositories.tasks import TaskRepository
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext
from agentic.security.redaction import redact_text
from agentic.security.rate_limit import InMemoryRateLimiter
from agentic.telemetry.events import EventPublisher
from agentic.telemetry.metrics import TASK_DURATION, TASKS
from agentic.tools.guard import AgentRuntimeContext


_NUMBER_TOKEN = re.compile(r"(?<!\w)[+-]?\d[\d,]*(?:\.\d+)?")


def _numbers_in(value: Any) -> set[Decimal]:
    rendered = (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    )
    numbers: set[Decimal] = set()
    for token in _NUMBER_TOKEN.findall(rendered):
        try:
            numbers.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            continue
    return numbers


def _validate_report_number_grounding(
    report: AgentReport,
    *,
    original_request: str,
    executions: list[ToolExecutionRow],
) -> None:
    """Reject model-created financial figures not present in trusted evidence."""

    if not executions:
        return
    claims = _numbers_in(
        {
            "summary": report.summary,
            "actions": report.actions,
            "result": report.result,
            "interaction_context": report.interaction_context.model_dump(mode="json"),
        }
    )
    evidence = _numbers_in(original_request)
    for execution in executions:
        evidence.update(_numbers_in(execution.arguments or {}))
        evidence.update(_numbers_in(execution.result or {}))
    if not claims.issubset(evidence):
        raise ValueError("report contains a numeric claim not grounded in authoritative evidence")


def _localized(language: str, english: str, arabic: str) -> str:
    return arabic if language == "ar" else english


def _conversation_context(metadata: RequestMetadata) -> list[dict[str, Any]]:
    """Normalize signed interaction context into provenance-labelled evidence."""

    context: list[dict[str, Any]] = []
    if metadata.conversation_context_summary:
        context.append(
            {
                "type": "interaction_summary",
                "text": metadata.conversation_context_summary,
                "provenance": "signed_interaction_request",
            }
        )
    context.extend(
        {
            "type": "prior_user_statement",
            "text": statement,
            "sequence": index,
            "provenance": "signed_interaction_request",
        }
        for index, statement in enumerate(metadata.conversation_user_statements)
    )
    return context


class AgentService:
    """Run, pause, resume, and audit authenticated agent tasks."""

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
        self._task_handles: dict[str, asyncio.Task[Any]] = {}
        self._outbox_worker: asyncio.Task[None] | None = None
        self._outbox_stop = asyncio.Event()
        self._outbox_delivery_lock = asyncio.Lock()

    def _valid_demo_otp(self, otp_code: str | None) -> bool:
        """Validate the demo OTP without placing it in graph state or audit data."""

        if otp_code is None:
            return False
        expected = self.config.secrets.demo_confirmation_otp.get_secret_value()
        return hmac.compare_digest(otp_code, expected)

    async def submit(self, request: AgenticRequest, *, background: bool = True) -> AcceptedTask:
        """Accept an idempotent request and optionally execute it in the background."""

        if request.confirmation and request.confirmation.authorization_token:
            if not self._valid_demo_otp(request.confirmation.otp_code):
                raise PermissionError("invalid confirmation OTP")
        if len(request.natural_language_request) > self.config.limits.task.max_request_characters:
            raise ValueError("request exceeds configured maximum length")
        await self.rate_limiter.acquire(tenant_id=request.tenant_id, user_id=request.user_id)
        request_fingerprint = TaskRepository.request_fingerprint(request)
        sanitized_request = request.model_copy(
            update={
                "natural_language_request": redact_text(request.natural_language_request),
                "original_user_message": redact_text(request.original_user_message),
                "metadata": request.metadata.model_copy(
                    update={
                        "conversation_context_summary": (
                            redact_text(request.metadata.conversation_context_summary)
                            if request.metadata.conversation_context_summary
                            else None
                        ),
                        "conversation_user_statements": [
                            redact_text(statement)
                            for statement in request.metadata.conversation_user_statements
                        ],
                    }
                ),
            }
        )
        try:
            accepted, task_id, should_run = await self._accept(
                sanitized_request, request_fingerprint=request_fingerprint
            )
        except Exception:
            await self.rate_limiter.release(tenant_id=request.tenant_id, user_id=request.user_id)
            raise
        if not should_run:
            await self.rate_limiter.release(tenant_id=request.tenant_id, user_id=request.user_id)
            return accepted
        if background:
            task_handle = asyncio.create_task(
                self._run_new_with_release(task_id, sanitized_request)
            )
            self._background_tasks.add(task_handle)
            self._task_handles[task_id] = task_handle

            def discard_handle(completed: asyncio.Task[Any]) -> None:
                self._background_tasks.discard(completed)
                if self._task_handles.get(task_id) is completed:
                    self._task_handles.pop(task_id, None)

            task_handle.add_done_callback(discard_handle)
        else:
            try:
                await self._run_new(task_id, sanitized_request)
            finally:
                await self.rate_limiter.release(
                    tenant_id=request.tenant_id, user_id=request.user_id
                )
        return accepted

    async def _accept(
        self, request: AgenticRequest, *, request_fingerprint: str
    ) -> tuple[AcceptedTask, str, bool]:
        outbox_id: str | None = None
        async with self.database.session() as session:
            task, created = await TaskRepository(session).create_or_get(
                request,
                config_hash=self.config_hash,
                request_fingerprint=request_fingerprint,
            )
            if task.expires_at is None:
                task.expires_at = datetime.now(timezone.utc) + timedelta(
                    days=self.config.limits.memory.task_checkpoint_ttl_days
                )
            task_id = task.id
            if created:
                outbox = await EventOutboxRepository(session).enqueue(
                    AgentEvent(
                        task_id=UUID(task_id),
                        request_id=request.request_id,
                        session_id=request.session_id,
                        event_type=AgentEventType.ACCEPTED,
                        user_safe_summary=_localized(
                            request.language,
                            "The request was accepted.",
                            "تم قبول الطلب.",
                        ),
                    )
                )
                outbox_id = outbox.id
        accepted = AcceptedTask(
            request_id=request.request_id,
            task_id=UUID(task_id),
            status="accepted",
            user_safe_message=_localized(
                request.language,
                "The financial task was accepted.",
                "تم قبول المهمة المالية.",
            ),
        )
        if outbox_id is not None:
            await self._deliver_outbox_id(outbox_id)
            TASKS.labels(outcome="accepted", language=request.language).inc()
        return accepted, task_id, TaskStatus(task.status) == TaskStatus.RECEIVED

    async def _run_new_with_release(self, task_id: str, request: AgenticRequest) -> None:
        try:
            await self._run_new(task_id, request)
        finally:
            await self.rate_limiter.release(tenant_id=request.tenant_id, user_id=request.user_id)

    async def _run_new(self, task_id: str, request: AgenticRequest) -> None:
        """Build trusted graph context and invoke a newly accepted task once."""

        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(
                task_id, tenant_id=request.tenant_id, user_id=request.user_id
            )
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
            context=_conversation_context(request.metadata),
        )
        # Only the signed request envelope supplies identity and scopes. Neither
        # the user message nor model output can mutate this runtime object.
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
            otp_verified=(
                self._valid_demo_otp(request.confirmation.otp_code)
                if request.confirmation
                else False
            ),
            original_request=request.natural_language_request,
            prior_user_statements=tuple(request.metadata.conversation_user_statements),
        )
        async with self.database.session() as session:
            memories = await MemoryService(
                session,
                self.memory_policy,
                max_items_per_session=self.config.limits.memory.max_items_per_session,
                max_items_per_type=self.config.limits.memory.max_items_per_type,
                max_value_characters=self.config.limits.memory.max_value_characters,
            ).list_for_session(auth=auth, limit=self.config.limits.memory.recent_messages)
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
        """Resume a paused task after rechecking its full identity tuple."""

        await self.rate_limiter.acquire(tenant_id=request.tenant_id, user_id=request.user_id)
        try:
            await self._resume(task_id, request)
        finally:
            await self.rate_limiter.release(tenant_id=request.tenant_id, user_id=request.user_id)

    async def _resume(self, task_id: UUID, request: ResumeTaskRequest) -> None:
        task_id_str = str(task_id)
        rejection_outbox_id: str | None = None
        rejection_language: str | None = None
        async with self.database.session() as session:
            repository = TaskRepository(session)
            clarifications = ClarificationRepository(session)
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
                await clarifications.answer(
                    str(request.clarification_id), task_id=task_id_str, answer=request.answer
                )
                resume_value = request.answer
            else:
                if current != TaskStatus.WAITING_FOR_CONFIRMATION:
                    raise ValueError("task is not waiting for confirmation")
                if request.confirmation_rejected:
                    await repository.transition(
                        row,
                        TaskStatus.REJECTED,
                        payload={"reason_code": "user_rejected_confirmation"},
                    )
                    outbox = await EventOutboxRepository(session).enqueue(
                        AgentEvent(
                            task_id=task_id,
                            request_id=UUID(row.request_id),
                            session_id=UUID(row.session_id),
                            event_type=AgentEventType.REJECTED,
                            user_safe_summary=_localized(
                                row.language,
                                "The user declined the requested financial action.",
                                "رفض المستخدم العملية المالية المطلوبة.",
                            ),
                            details={"reason_code": "user_rejected_confirmation"},
                        )
                    )
                    rejection_outbox_id = outbox.id
                    rejection_language = row.language
                    resume_value = None
                    explicit_user_field_values = {}
                    original = None
                else:
                    if not self._valid_demo_otp(request.otp_code):
                        raise PermissionError("invalid confirmation OTP")
                    resume_value = request.authorization_token
            if rejection_outbox_id is None:
                explicit_user_field_values = await clarifications.answered_field_values(task_id_str)
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
                    metadata=RequestMetadata.model_validate(row.request_context or {}),
                )
        if rejection_outbox_id is not None:
            await self._deliver_outbox_id(rejection_outbox_id)
            TASKS.labels(
                outcome=TaskStatus.REJECTED.value,
                language=rejection_language or "unknown",
            ).inc()
            return
        assert original is not None
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
            otp_verified=request.authorization_token is not None,
            original_request=original.natural_language_request,
            prior_user_statements=tuple(
                original.metadata.conversation_user_statements
            ),
            explicit_user_field_values=explicit_user_field_values,
            resuming_from_clarification=request.clarification_id is not None,
        )
        await self._invoke(
            task_id_str,
            original,
            Command(resume=resume_value),
            runtime_context,
        )

    async def delete_memory(self, *, tenant_id: str, user_id: str, session_id: str) -> int:
        """Delete curated cross-task memory within an authenticated namespace."""

        auth = AuthContext(user_id, tenant_id, session_id, frozenset())
        async with self.database.session() as session:
            return await MemoryService(
                session,
                self.memory_policy,
                max_items_per_session=self.config.limits.memory.max_items_per_session,
                max_items_per_type=self.config.limits.memory.max_items_per_type,
                max_value_characters=self.config.limits.memory.max_value_characters,
            ).delete_for_session(auth=auth)

    async def cancel(self, task_id: UUID, request: CancelTaskRequest) -> bool:
        """Cancel a running task after the interaction layer's response deadline."""

        task_id_str = str(task_id)
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(
                task_id_str,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
            )
            if (
                row is None
                or row.session_id != str(request.session_id)
                or row.request_id != str(request.request_id)
            ):
                raise LookupError("task not found")
            if TaskStatus(row.status) in TERMINAL_TASK_STATUSES:
                return False
            handle = self._task_handles.get(task_id_str)
            if handle is not None and not handle.done():
                handle.cancel()
            await repository.transition(
                row,
                (
                    TaskStatus.REJECTED
                    if request.reason_code == "user_cancelled"
                    else TaskStatus.FAILED
                ),
                payload={"error_code": request.reason_code},
            )
            outbox = await EventOutboxRepository(session).enqueue(
                AgentEvent(
                    task_id=task_id,
                    request_id=request.request_id,
                    session_id=request.session_id,
                    event_type=(
                        AgentEventType.REJECTED
                        if request.reason_code == "user_cancelled"
                        else AgentEventType.FAILED
                    ),
                    user_safe_summary=_localized(
                        row.language,
                        (
                            "Request cancelled. You can start a new request now."
                            if request.reason_code == "user_cancelled"
                            else "The request took too long, so it was cancelled safely."
                        ),
                        (
                            "ألغيت الطلب. يمكنك بدء طلب جديد الآن."
                            if request.reason_code == "user_cancelled"
                            else "استغرق الطلب وقتاً طويلاً، لذلك تم إلغاؤه بأمان."
                        ),
                    ),
                    details={
                        "reason_code": request.reason_code,
                        "action_cancelled": True,
                    },
                )
            )
            outbox_id = outbox.id
        await self._deliver_outbox_id(outbox_id)
        TASKS.labels(outcome=request.reason_code, language=row.language).inc()
        return True

    async def get_task_status(
        self, task_id: UUID, request: TaskStatusRequest
    ) -> TaskStatusResponse:
        """Return identity-scoped state for the temporary external evaluator.

        The API exposes this method only outside production. It intentionally
        returns the persisted safe interrupt payload or final report, never a
        checkpoint, prompt, model trace, or raw tool result.
        """

        async with self.database.session() as session:
            row = await session.scalar(
                select(AgentTaskRow).where(
                    AgentTaskRow.id == str(task_id),
                    AgentTaskRow.tenant_id == request.tenant_id,
                    AgentTaskRow.user_id == request.user_id,
                    AgentTaskRow.session_id == str(request.session_id),
                    AgentTaskRow.request_id == str(request.request_id),
                )
            )
            if row is None:
                raise LookupError("task not found")

            status = TaskStatus(row.status)
            pending_action = None
            if status in {TaskStatus.WAITING_FOR_INPUT, TaskStatus.WAITING_FOR_CONFIRMATION}:
                event = await session.scalar(
                    select(TaskEventRow)
                    .where(
                        TaskEventRow.task_id == str(task_id),
                        TaskEventRow.event_type == status.value,
                    )
                    .order_by(TaskEventRow.created_at.desc())
                    .limit(1)
                )
                pending_action = event.payload if event else None

            return TaskStatusResponse(
                task_id=task_id,
                status=status,
                final_report=row.final_report,
                pending_action=pending_action,
            )

    async def _invoke(
        self,
        task_id: str,
        request: AgenticRequest,
        graph_input: Any,
        runtime_context: AgentRuntimeContext,
    ) -> None:
        """Invoke the graph under its wall-clock budget and persist the outcome."""

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
        elif kind == "confirmation":
            target = TaskStatus.WAITING_FOR_CONFIRMATION
            event_type = AgentEventType.CONFIRMATION_NEEDED
        else:
            raise ValueError("unsupported graph interrupt")
        async with self.database.session() as session:
            if kind == "clarification":
                await ClarificationRepository(session).create(
                    clarification_id=payload["clarification_id"],
                    task_id=task_id,
                    question=payload["question"],
                    reason_code=payload["reason_code"],
                    expected_answer=payload["expected_answer"],
                    expires_in_seconds=payload["expires_in_seconds"],
                )
            repository = TaskRepository(session)
            row = await repository.get(
                task_id, tenant_id=request.tenant_id, user_id=request.user_id
            )
            if row is None:
                raise LookupError("task not found")
            await repository.transition(row, target, payload=payload)
            outbox = await EventOutboxRepository(session).enqueue(
                AgentEvent(
                    task_id=UUID(task_id),
                    request_id=request.request_id,
                    session_id=request.session_id,
                    event_type=event_type,
                    user_safe_summary=(
                        payload.get("question")
                        or _localized(
                            request.language,
                            "Confirmation is required before continuing.",
                            "يلزم التأكيد قبل المتابعة.",
                        )
                    ),
                    details=payload,
                )
            )
            outbox_id = outbox.id
        await self._deliver_outbox_id(outbox_id)
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
            service = MemoryService(
                session,
                self.memory_policy,
                max_items_per_session=self.config.limits.memory.max_items_per_session,
                max_items_per_type=self.config.limits.memory.max_items_per_type,
                max_value_characters=self.config.limits.memory.max_value_characters,
            )
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
        _validate_report_number_grounding(
            report,
            original_request=request.original_user_message,
            executions=executions,
        )
        if not set(report.receipt_ids).issubset(authoritative_receipts):
            raise ValueError(f"report contains a receipt not returned by an authoritative tool: {report.receipt_ids} vs {authoritative_receipts}")
        required_tool_names = self.config.policies.financial_actions.require_authoritative_receipt
        required_receipts = {
            row.receipt_id
            for row in executions
            if row.tool_name in required_tool_names and row.status == "completed" and row.receipt_id
        }
        # The model may omit a receipt, but it may never invent one. Attach
        # missing IDs deterministically from completed persisted executions so
        # a successful provider action is not turned into a failed task merely
        # because report formatting was incomplete.
        if not required_receipts.issubset(set(report.receipt_ids)):
            report = AgentReport.model_validate(
                report.model_dump(mode="json")
                | {"receipt_ids": sorted(set(report.receipt_ids) | required_receipts)}
            )
        target = {
            "completed": TaskStatus.COMPLETED,
            "partially_completed": TaskStatus.PARTIALLY_COMPLETED,
            "rejected": TaskStatus.REJECTED,
            "failed": TaskStatus.FAILED,
        }[report.status]
        event_type = {
            TaskStatus.COMPLETED: AgentEventType.COMPLETED,
            TaskStatus.PARTIALLY_COMPLETED: AgentEventType.COMPLETED,
            TaskStatus.REJECTED: AgentEventType.REJECTED,
            TaskStatus.FAILED: AgentEventType.FAILED,
        }[target]
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(
                task_id, tenant_id=request.tenant_id, user_id=request.user_id
            )
            if row is None:
                raise LookupError("task not found")
            row.final_report = report.model_dump(mode="json")
            row.intent = result["intent"]["intent"] if result.get("intent") else None
            row.risk = result["risk"]["level"] if result.get("risk") else None
            await repository.transition(row, target, payload={"report": row.final_report})
            outbox = await EventOutboxRepository(session).enqueue(
                AgentEvent(
                    task_id=UUID(task_id),
                    request_id=request.request_id,
                    session_id=request.session_id,
                    event_type=event_type,
                    user_safe_summary=report.summary,
                    details={"report": report.model_dump(mode="json")},
                )
            )
            outbox_id = outbox.id
        await self._deliver_outbox_id(outbox_id)
        TASKS.labels(outcome=target.value, language=request.language).inc()
        if target in {TaskStatus.COMPLETED, TaskStatus.PARTIALLY_COMPLETED}:
            await self._extract_memories(request, task_id)

    async def _record_failure(self, task_id: str, request: AgenticRequest, error_code: str) -> None:
        outbox_id: str | None = None
        async with self.database.session() as session:
            repository = TaskRepository(session)
            row = await repository.get(
                task_id, tenant_id=request.tenant_id, user_id=request.user_id
            )
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
            if row is not None:
                outbox = await EventOutboxRepository(session).enqueue(
                    AgentEvent(
                        task_id=UUID(task_id),
                        request_id=request.request_id,
                        session_id=request.session_id,
                        event_type=AgentEventType.FAILED,
                        user_safe_summary=_localized(
                            request.language,
                            "The financial task could not be completed safely.",
                            "تعذّر إكمال المهمة المالية بأمان.",
                        ),
                        details={"error_code": error_code},
                    )
                )
                outbox_id = outbox.id
        if outbox_id is not None:
            await self._deliver_outbox_id(outbox_id)
        TASKS.labels(outcome="failed", language=request.language).inc()

    async def _deliver_outbox_id(self, outbox_id: str) -> bool:
        async with self._outbox_delivery_lock:
            async with self.database.session() as session:
                row = await session.get(EventOutboxRow, outbox_id)
                if row is None or row.delivered_at is not None:
                    return True
                if await EventOutboxRepository(session).has_undelivered_predecessor(row):
                    return False
                event = AgentEvent.model_validate(row.payload)
            try:
                await self.events.publish(event)
            except Exception as exc:
                async with self.database.session() as session:
                    row = await session.get(EventOutboxRow, outbox_id)
                    if row is not None and row.delivered_at is None:
                        await EventOutboxRepository(session).failed(
                            row, error_code=type(exc).__name__
                        )
                return False
            async with self.database.session() as session:
                row = await session.get(EventOutboxRow, outbox_id)
                if row is not None and row.delivered_at is None:
                    await EventOutboxRepository(session).delivered(row)
            return True

    async def _deliver_pending_outbox(self) -> None:
        async with self.database.session() as session:
            rows = await EventOutboxRepository(session).pending()
            outbox_ids = [row.id for row in rows]
        for outbox_id in outbox_ids:
            await self._deliver_outbox_id(outbox_id)

    def start_event_delivery_worker(self) -> None:
        if self._outbox_worker is not None and not self._outbox_worker.done():
            return
        self._outbox_stop.clear()
        self._outbox_worker = asyncio.create_task(self._event_delivery_loop())

    async def _event_delivery_loop(self) -> None:
        while not self._outbox_stop.is_set():
            try:
                await asyncio.wait_for(self._outbox_stop.wait(), timeout=1)
            except TimeoutError:
                pass
            if not self._outbox_stop.is_set():
                try:
                    await self._deliver_pending_outbox()
                except Exception:
                    # A transient database outage must not permanently kill the
                    # retry worker; the next pass will retry the durable rows.
                    continue

    async def stop_event_delivery_worker(self) -> None:
        if self._outbox_worker is None:
            return
        self._outbox_stop.set()
        await self._outbox_worker
        self._outbox_worker = None

    async def wait_for_background_tasks(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks), return_exceptions=True)
