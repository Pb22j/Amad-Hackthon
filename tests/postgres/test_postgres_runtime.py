from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy import func, select

from agentic.agent.graph import build_financial_agent, initial_state
from agentic.api.schemas import AgenticRequest, AuthorizationContext
from agentic.config.loader import load_config
from agentic.persistence.checkpointer import postgres_checkpointer
from agentic.persistence.database import Database
from agentic.persistence.models import AgentTaskRow
from agentic.persistence.models import ToolExecutionRow
from agentic.persistence.repositories.executions import ToolExecutionRepository
from agentic.persistence.repositories.tasks import TaskRepository
from agentic.persistence.store import postgres_memory_store
from agentic.policy.models import Intent
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext
from agentic.tools.guard import AgentRuntimeContext
from agentic.tools.metadata import ToolMetadata, ToolRisk
from tests.fakes import ScriptedChatModel, StaticClassifier, report_message


class TransferArgs(BaseModel):
    amount: int
    destination: str


@pytest.fixture
def postgres_url():
    value = os.getenv("TEST_POSTGRES_URL")
    if not value:
        pytest.skip("TEST_POSTGRES_URL is not configured")
    return value


@pytest.mark.postgres
@pytest.mark.security
async def test_encrypted_checkpoint_interrupt_resume_and_postgres_store(postgres_url):
    sqlalchemy_url = postgres_url.replace("postgresql://", "postgresql+psycopg://", 1)
    database = Database(sqlalchemy_url)
    config = load_config()
    task_id = str(uuid4())
    request_id = str(uuid4())
    session_id = str(uuid4())
    async with database.session() as session:
        session.add(
            AgentTaskRow(
                id=task_id,
                request_id=request_id,
                session_id=session_id,
                user_id="postgres-user",
                tenant_id="postgres-tenant",
                language="en",
                authorized_scopes=["financial:write"],
                assurance_level="high",
                original_request="transfer encrypted",
            )
        )

    async def transfer(amount: int, destination: str):
        return {
            "status": "completed",
            "summary": "Transfer completed",
            "data": {"amount": amount},
            "user_id": "postgres-user",
            "tenant_id": "postgres-tenant",
            "receipt_id": "postgres-receipt",
        }

    tool = StructuredTool.from_function(
        coroutine=transfer,
        name="transfer_funds",
        description="Transfer funds",
        args_schema=TransferArgs,
    )
    arguments = {"amount": 123, "destination": "beneficiary-secret-name"}
    model = ScriptedChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "transfer_funds",
                        "args": arguments,
                        "id": "postgres-transfer",
                        "type": "tool_call",
                    }
                ],
            ),
            report_message(
                summary="Transfer completed", receipt_ids=["postgres-receipt"]
            ),
        ]
    )
    auth = AuthContext(
        "postgres-user",
        "postgres-tenant",
        session_id,
        frozenset({"financial:write"}),
    )
    signer = ConfirmationSigner("c" * 32)
    context = AgentRuntimeContext(
        auth,
        task_id,
        database.session_factory,
        config,
        signer,
    )
    async with postgres_checkpointer(
        postgres_url, encryption_key="e" * 32, setup=False
    ) as checkpointer:
        graph = build_financial_agent(
            primary_model=model,
            classifier_model=StaticClassifier(Intent.MONEY_TRANSFER),
            external_tools=[tool],
            tool_metadata=[
                ToolMetadata(
                    name="transfer_funds",
                    risk=ToolRisk.FINANCIAL_ACTION,
                    required_scopes=frozenset({"financial:write"}),
                    requires_confirmation=True,
                    requires_receipt=True,
                )
            ],
            config=config,
            checkpointer=checkpointer,
        )
        graph_config = {"configurable": {"thread_id": task_id}}
        interrupted = await graph.ainvoke(
            initial_state(
                task_id=task_id,
                request_id=request_id,
                session_id=session_id,
                user_id="postgres-user",
                tenant_id="postgres-tenant",
                language="en",
                request="Transfer 123 to beneficiary-secret-name",
            ),
            config=graph_config,
            context=context,
        )
        assert interrupted["__interrupt__"][0].value["kind"] == "confirmation"
        token = signer.issue(
            auth=auth,
            task_id=task_id,
            tool_name="transfer_funds",
            arguments=arguments,
        )
        context.otp_verified = True
        completed = await graph.ainvoke(
            Command(resume=token), config=graph_config, context=context
        )
        assert completed["final_report"]["receipt_ids"] == ["postgres-receipt"]

    async with database.session() as session:
        raw_checkpoints = await session.scalars(
            text("SELECT checkpoint::text FROM checkpoints WHERE thread_id = :thread_id"),
            {"thread_id": task_id},
        )
        serialized = " ".join(raw_checkpoints)
        assert "beneficiary-secret-name" not in serialized
        assert "Transfer 123" not in serialized
        raw_request = await session.scalar(
            text("SELECT original_request FROM agent_tasks WHERE id = :task_id"),
            {"task_id": task_id},
        )
        raw_arguments = await session.scalar(
            text("SELECT arguments FROM tool_executions WHERE task_id = :task_id"),
            {"task_id": task_id},
        )
        assert b"transfer encrypted" not in bytes(raw_request)
        assert b"beneficiary-secret-name" not in bytes(raw_arguments)

    namespace = ("postgres-tenant", "postgres-user", "memory")
    async with postgres_memory_store(postgres_url, setup=False) as store:
        await store.aput(namespace, "currency", {"currency": "SAR"})
        item = await store.aget(namespace, "currency")
        assert item.value == {"currency": "SAR"}
        await store.adelete(namespace, "currency")
    await database.dispose()


@pytest.mark.postgres
@pytest.mark.security
async def test_concurrent_request_and_execution_idempotency(postgres_url):
    sqlalchemy_url = postgres_url.replace("postgresql://", "postgresql+psycopg://", 1)
    database = Database(sqlalchemy_url)
    request = AgenticRequest(
        request_id=uuid4(),
        session_id=uuid4(),
        user_id="concurrent-user",
        tenant_id=f"tenant-{uuid4()}",
        language="en",
        natural_language_request="Show my balance",
        original_user_message="Show my balance",
        authorization=AuthorizationContext(
            scopes=frozenset({"financial:read"}),
            authenticated_at=datetime.now(timezone.utc),
            assurance_level="high",
        ),
    )

    async def create_task():
        async with database.session() as session:
            return await TaskRepository(session).create(request, config_hash="a" * 64)

    first, second = await asyncio.gather(create_task(), create_task())
    assert first.id == second.id
    async with database.session() as session:
        count = await session.scalar(
            select(func.count()).select_from(AgentTaskRow).where(
                AgentTaskRow.tenant_id == request.tenant_id,
                AgentTaskRow.request_id == str(request.request_id),
            )
        )
        assert count == 1

    async def start_execution(call_id: str):
        async with database.session() as session:
            return await ToolExecutionRepository(session).start(
                task_id=first.id,
                tenant_id=request.tenant_id,
                tool_call_id=call_id,
                tool_name="get_balance",
                arguments={"account": "checking"},
                idempotency_key="same-idempotency-key",
            )

    one, two = await asyncio.gather(start_execution("one"), start_execution("two"))
    assert one[0].id == two[0].id
    assert sorted((one[1], two[1])) == [False, True]
    async with database.session() as session:
        count = await session.scalar(
            select(func.count()).select_from(ToolExecutionRow).where(
                ToolExecutionRow.tenant_id == request.tenant_id,
                ToolExecutionRow.idempotency_key == "same-idempotency-key",
            )
        )
        assert count == 1
    await database.dispose()
