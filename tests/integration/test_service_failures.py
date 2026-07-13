from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from agentic.agent.service import AgentService
from agentic.api.schemas import TaskStatus
from agentic.memory.extraction import MemoryCandidate
from agentic.persistence.models import AgentTaskRow, ToolExecutionRow
from agentic.security.confirmation import ConfirmationSigner
from agentic.telemetry.events import InMemoryEventPublisher


class FakeGraph:
    def __init__(self, result=None, error=None, *, delay=0):
        self.result = result
        self.error = error
        self.delay = delay

    async def ainvoke(self, graph_input, config, context):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        if callable(self.result):
            return await self.result(graph_input, config, context)
        return self.result


def service(database, app_config, graph, memory_extractor=None):
    return AgentService(
        graph=graph,
        database=database,
        config=app_config,
        confirmation_signer=ConfirmationSigner("c" * 32),
        events=InMemoryEventPublisher(),
        memory_extractor=memory_extractor,
    )


def completed_result(status="completed", **overrides):
    report = {
        "status": status,
        "summary": "Result",
        "actions": [],
        "result": {},
        "warnings": [],
        "receipt_ids": [],
        "needs_follow_up": False,
    } | overrides
    return {
        "final_report": report,
        "intent": {"intent": "account_information"},
        "risk": {"level": "low"},
    }


@pytest.mark.integration
async def test_long_request_is_rejected_before_persistence(database, app_config, agentic_request):
    strict = app_config.model_copy(
        update={
            "limits": app_config.limits.model_copy(
                update={
                    "task": app_config.limits.task.model_copy(
                        update={"max_request_characters": 100}
                    )
                }
            )
        }
    )
    request = agentic_request.model_copy(
        update={"natural_language_request": "x" * 101}
    )
    with pytest.raises(ValueError, match="maximum length"):
        await service(database, strict, FakeGraph(completed_result())).submit(
            request, background=False
        )


@pytest.mark.integration
async def test_background_task_is_tracked_and_waited(database, app_config, agentic_request):
    instance = service(database, app_config, FakeGraph(completed_result(), delay=0.01))
    accepted = await instance.submit(agentic_request, background=True)
    await instance.wait_for_background_tasks()
    async with database.session() as session:
        row = await session.get(AgentTaskRow, str(accepted.task_id))
        assert row.status == TaskStatus.COMPLETED.value


@pytest.mark.integration
async def test_graph_failure_is_persisted_safely(database, app_config, agentic_request):
    instance = service(database, app_config, FakeGraph(error=RuntimeError("secret stack")))
    with pytest.raises(RuntimeError):
        await instance.submit(agentic_request, background=False)
    async with database.session() as session:
        row = await session.scalar(__import__("sqlalchemy").select(AgentTaskRow))
        assert row.status == TaskStatus.FAILED.value
        assert row.final_report is None


@pytest.mark.integration
@pytest.mark.security
async def test_forged_receipt_in_report_fails_task(database, app_config, agentic_request):
    result = completed_result(receipt_ids=["invented-receipt"])
    instance = service(database, app_config, FakeGraph(result))
    with pytest.raises(ValueError, match="not returned"):
        await instance.submit(agentic_request, background=False)


@pytest.mark.integration
@pytest.mark.security
async def test_omitted_receipt_is_attached_only_from_authoritative_execution(
    database, app_config, agentic_request
):
    async def graph_result(graph_input, config, context):
        async with context.session_factory() as session:
            session.add(
                ToolExecutionRow(
                    task_id=context.task_id,
                    tenant_id=context.auth.tenant_id,
                    tool_call_id="call",
                    tool_name="transfer_funds",
                    arguments={},
                    idempotency_key="key",
                    status="completed",
                    receipt_id="authoritative-receipt",
                )
            )
            await session.commit()
        return completed_result()

    instance = service(database, app_config, FakeGraph(graph_result))
    accepted = await instance.submit(agentic_request, background=False)
    async with database.session() as session:
        row = await session.get(AgentTaskRow, str(accepted.task_id))
        assert row.status == TaskStatus.COMPLETED.value
        assert row.final_report["receipt_ids"] == ["authoritative-receipt"]


@pytest.mark.integration
async def test_unknown_interrupt_fails_closed(database, app_config, agentic_request):
    instance = service(
        database,
        app_config,
        FakeGraph({"__interrupt__": [{"kind": "unsupported"}]}),
    )
    with pytest.raises(ValueError, match="unsupported graph interrupt"):
        await instance.submit(agentic_request, background=False)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("report_status", "task_status"),
    [
        ("partially_completed", TaskStatus.PARTIALLY_COMPLETED),
        ("rejected", TaskStatus.REJECTED),
        ("failed", TaskStatus.FAILED),
    ],
)
async def test_all_terminal_report_statuses_are_persisted(
    database, app_config, agentic_request, report_status, task_status
):
    request = agentic_request.model_copy(update={"request_id": uuid4()})
    instance = service(database, app_config, FakeGraph(completed_result(report_status)))
    accepted = await instance.submit(request, background=False)
    async with database.session() as session:
        row = await session.get(AgentTaskRow, str(accepted.task_id))
        assert row.status == task_status.value


class BrokenExtractor:
    async def extract(self, request):
        raise RuntimeError("unavailable")


class UnsafeExtractor:
    async def extract(self, request):
        return [
            MemoryCandidate(
                memory_type="unsupported",
                value={"password": "secret"},
                direct_quote=request,
                confidence=1,
            )
        ]


@pytest.mark.integration
@pytest.mark.parametrize("extractor", [BrokenExtractor(), UnsafeExtractor()])
async def test_memory_extraction_failure_never_fails_completed_task(
    database, app_config, agentic_request, extractor
):
    instance = service(
        database, app_config, FakeGraph(completed_result()), memory_extractor=extractor
    )
    accepted = await instance.submit(agentic_request, background=False)
    async with database.session() as session:
        row = await session.get(AgentTaskRow, str(accepted.task_id))
        assert row.status == TaskStatus.COMPLETED.value


def test_interrupt_payload_handles_empty_and_scalar_values():
    assert AgentService._interrupt_payload({"__interrupt__": []}) is None
    assert AgentService._interrupt_payload({"__interrupt__": ["pause"]}) == {
        "kind": "unknown",
        "value": "pause",
    }


class FailingPublisher:
    async def publish(self, event):
        raise RuntimeError("webhook unavailable")


@pytest.mark.integration
async def test_acceptance_failure_releases_concurrency_slot(
    database, app_config, agentic_request
):
    instance = AgentService(
        graph=FakeGraph(completed_result()),
        database=database,
        config=app_config,
        confirmation_signer=ConfirmationSigner("c" * 32),
        events=FailingPublisher(),
    )
    with pytest.raises(RuntimeError, match="webhook"):
        await instance.submit(agentic_request, background=False)
    await instance.rate_limiter.acquire(
        tenant_id=agentic_request.tenant_id, user_id=agentic_request.user_id
    )
    await instance.rate_limiter.release(
        tenant_id=agentic_request.tenant_id, user_id=agentic_request.user_id
    )
