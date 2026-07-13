from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from agentic.agent.graph import build_financial_agent
from agentic.agent.service import AgentService
from agentic.api.schemas import ResumeTaskRequest, TaskStatus, TaskStatusRequest
from agentic.memory.extraction import MemoryCandidate
from agentic.persistence.models import AgentTaskRow, ClarificationRow
from agentic.policy.models import Intent
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext
from agentic.telemetry.events import InMemoryEventPublisher
from agentic.tools.metadata import ToolMetadata, ToolRisk
from tests.fakes import ScriptedChatModel, StaticClassifier, report_message


class TransferArgs(BaseModel):
    amount: int
    destination: str


def build_service(
    *,
    database,
    app_config,
    model,
    intent=Intent.ACCOUNT_INFORMATION,
    tools=(),
    metadata=(),
    memory_extractor=None,
):
    signer = ConfirmationSigner("c" * 32)
    events = InMemoryEventPublisher()
    graph = build_financial_agent(
        primary_model=model,
        classifier_model=StaticClassifier(intent),
        external_tools=tools,
        tool_metadata=metadata,
        config=app_config,
        checkpointer=InMemorySaver(),
    )
    return (
        AgentService(
            graph=graph,
            database=database,
            config=app_config,
            confirmation_signer=signer,
            events=events,
            memory_extractor=memory_extractor,
        ),
        signer,
        events,
    )


class StaticMemoryExtractor:
    async def extract(self, request: str):
        if "Use SAR" not in request:
            return []
        return [
            MemoryCandidate(
                memory_type="reporting_currency",
                value={"currency": "SAR"},
                direct_quote="Use SAR",
                confidence=1,
            )
        ]


@pytest.mark.integration
async def test_service_completes_and_persists_report(database, app_config, agentic_request):
    service, _, events = build_service(
        database=database,
        app_config=app_config,
        model=ScriptedChatModel(responses=[report_message(summary="Balance retrieved")]),
    )
    accepted = await service.submit(agentic_request, background=False)
    status = await service.get_task_status(
        accepted.task_id,
        TaskStatusRequest(
            request_id=agentic_request.request_id,
            session_id=agentic_request.session_id,
            user_id=agentic_request.user_id,
            tenant_id=agentic_request.tenant_id,
        ),
    )
    async with database.session() as session:
        task = await session.get(AgentTaskRow, str(accepted.task_id))
        assert task.status == TaskStatus.COMPLETED.value
        assert task.final_report["summary"] == "Balance retrieved"
    assert status.status == TaskStatus.COMPLETED
    assert status.final_report["summary"] == "Balance retrieved"
    assert status.pending_action is None
    assert [event.event_type.value for event in events.events] == ["accepted", "completed"]


@pytest.mark.integration
async def test_service_persists_clarification_and_resumes(
    database, app_config, agentic_request
):
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "request_user_input",
                        "args": {
                            "question": "Which source account?",
                            "reason_code": "missing_source_account",
                            "expected_answer": {"type": "string"},
                            "expires_in_seconds": 900,
                        },
                        "id": "ask-account",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Source account selected"),
        ]
    )
    service, _, events = build_service(
        database=database,
        app_config=app_config,
        model=model,
        intent=Intent.MONEY_TRANSFER,
    )
    accepted = await service.submit(agentic_request, background=False)
    input_event = events.events[-1]
    assert input_event.event_type.value == "input_needed"
    status = await service.get_task_status(
        accepted.task_id,
        TaskStatusRequest(
            request_id=agentic_request.request_id,
            session_id=agentic_request.session_id,
            user_id=agentic_request.user_id,
            tenant_id=agentic_request.tenant_id,
        ),
    )
    assert status.status == TaskStatus.WAITING_FOR_INPUT
    assert status.pending_action["question"] == "Which source account?"
    clarification_id = UUID(input_event.details["clarification_id"])
    async with database.session() as session:
        clarification = await session.get(ClarificationRow, str(clarification_id))
        task = await session.get(AgentTaskRow, str(accepted.task_id))
        assert clarification.status == "pending"
        assert task.status == TaskStatus.WAITING_FOR_INPUT.value
    await service.resume(
        accepted.task_id,
        ResumeTaskRequest(
            request_id=agentic_request.request_id,
            session_id=agentic_request.session_id,
            user_id=agentic_request.user_id,
            tenant_id=agentic_request.tenant_id,
            clarification_id=clarification_id,
            answer="checking",
        ),
    )
    async with database.session() as session:
        task = await session.get(AgentTaskRow, str(accepted.task_id))
        clarification = await session.get(ClarificationRow, str(clarification_id))
        assert task.status == TaskStatus.COMPLETED.value
        assert clarification.status == "answered"


@pytest.mark.integration
@pytest.mark.security
async def test_service_transfer_confirmation_and_receipt(
    database, app_config, agentic_request
):
    calls = 0

    async def transfer(amount: int, destination: str):
        nonlocal calls
        calls += 1
        return {
            "status": "completed",
            "summary": "Transfer completed",
            "data": {"amount": amount, "destination": destination},
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "receipt_id": "receipt-123",
        }

    tool = StructuredTool.from_function(
        coroutine=transfer,
        name="transfer_funds",
        description="Transfer funds.",
        args_schema=TransferArgs,
    )
    arguments = {"amount": 500, "destination": "beneficiary-1"}
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "transfer_funds",
                        "args": arguments,
                        "id": "transfer-1",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(summary="Transfer completed", receipt_ids=["receipt-123"]),
        ]
    )
    service, signer, events = build_service(
        database=database,
        app_config=app_config,
        model=model,
        intent=Intent.MONEY_TRANSFER,
        tools=[tool],
        metadata=[
            ToolMetadata(
                name="transfer_funds",
                risk=ToolRisk.FINANCIAL_ACTION,
                required_scopes=frozenset({"financial:write"}),
                requires_confirmation=True,
                requires_receipt=True,
            )
        ],
    )
    accepted = await service.submit(agentic_request, background=False)
    assert calls == 0
    confirmation_event = events.events[-1]
    assert confirmation_event.event_type.value == "confirmation_needed"
    auth = AuthContext(
        agentic_request.user_id,
        agentic_request.tenant_id,
        str(agentic_request.session_id),
        agentic_request.authorization.scopes,
    )
    token = signer.issue(
        auth=auth,
        task_id=str(accepted.task_id),
        tool_name="transfer_funds",
        arguments=arguments,
    )
    await service.resume(
        accepted.task_id,
        ResumeTaskRequest(
            request_id=agentic_request.request_id,
            session_id=agentic_request.session_id,
            user_id=agentic_request.user_id,
            tenant_id=agentic_request.tenant_id,
            authorization_token=token,
        ),
    )
    assert calls == 1
    async with database.session() as session:
        task = await session.get(AgentTaskRow, str(accepted.task_id))
        assert task.status == TaskStatus.COMPLETED.value
        assert task.final_report["receipt_ids"] == ["receipt-123"]


@pytest.mark.integration
@pytest.mark.security
async def test_resume_rejects_wrong_identity_and_request(database, app_config, agentic_request):
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "request_user_input",
                        "args": {
                            "question": "Which account?",
                            "reason_code": "missing_account",
                            "expected_answer": {"type": "string"},
                            "expires_in_seconds": 900,
                        },
                        "id": "ask",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    )
    service, _, events = build_service(
        database=database, app_config=app_config, model=model
    )
    accepted = await service.submit(agentic_request, background=False)
    clarification_id = UUID(events.events[-1].details["clarification_id"])
    with pytest.raises(LookupError):
        await service.get_task_status(
            accepted.task_id,
            TaskStatusRequest(
                request_id=agentic_request.request_id,
                session_id=agentic_request.session_id,
                user_id="another-user",
                tenant_id=agentic_request.tenant_id,
            ),
        )
    with pytest.raises(LookupError):
        await service.resume(
            accepted.task_id,
            ResumeTaskRequest(
                request_id=agentic_request.request_id,
                session_id=agentic_request.session_id,
                user_id="another-user",
                tenant_id=agentic_request.tenant_id,
                clarification_id=clarification_id,
                answer="checking",
            ),
        )


@pytest.mark.integration
async def test_service_extracts_and_retrieves_curated_memory(
    database, app_config, agentic_request
):
    first_request = agentic_request.model_copy(
        update={
            "natural_language_request": "Use SAR for my reports.",
            "original_user_message": "Use SAR for my reports.",
        }
    )
    first_model = ScriptedChatModel(responses=[report_message(summary="Preference saved")])
    first_service, _, _ = build_service(
        database=database,
        app_config=app_config,
        model=first_model,
        memory_extractor=StaticMemoryExtractor(),
    )
    await first_service.submit(first_request, background=False)

    second_request = agentic_request.model_copy(
        update={
            "request_id": uuid4(),
            "natural_language_request": "Show my balance.",
            "original_user_message": "Show my balance.",
        }
    )
    second_model = ScriptedChatModel(responses=[report_message(summary="Balance shown")])
    second_service, _, _ = build_service(
        database=database,
        app_config=app_config,
        model=second_model,
    )
    await second_service.submit(second_request, background=False)
    serialized_messages = " ".join(
        str(message.content)
        for invocation in second_model.seen_messages
        for message in invocation
    )
    assert "reporting_currency" in serialized_messages
    assert "SAR" in serialized_messages
    assert "untrusted context" in serialized_messages


@pytest.mark.integration
@pytest.mark.security
async def test_service_redacts_card_numbers_before_persistence_and_model(
    database, app_config, agentic_request
):
    unsafe = agentic_request.model_copy(
        update={
            "natural_language_request": "Use card 4111 1111 1111 1111",
            "original_user_message": "Use card 4111 1111 1111 1111",
        }
    )
    model = ScriptedChatModel(responses=[report_message(summary="Request handled")])
    service, _, _ = build_service(database=database, app_config=app_config, model=model)
    accepted = await service.submit(unsafe, background=False)
    async with database.session() as session:
        task = await session.get(AgentTaskRow, str(accepted.task_id))
        assert "4111" not in task.original_request
    assert "4111" not in " ".join(
        str(message.content) for invocation in model.seen_messages for message in invocation
    )
