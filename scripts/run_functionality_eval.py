"""Run the bilingual functionality matrix through the real agent and dummy ledger."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from agentic.agent.graph import build_financial_agent
from agentic.agent.service import AgentService
from agentic.api.schemas import AgentEventType, AgenticRequest, AuthorizationContext, ResumeTaskRequest
from agentic.config.loader import AppConfig, load_config
from agentic.evals.functionality_runner import (
    FunctionalityEvalCase,
    FunctionalityObservation,
    ObservedToolCall,
    build_functionality_report,
    load_functionality_dataset,
    write_functionality_report,
)
from agentic.llm.factory import ModelFactory
from agentic.persistence.database import Database
from agentic.persistence.models import AgentTaskRow, ToolExecutionRow
from agentic.security.confirmation import ConfirmationSigner
from agentic.security.identity import AuthContext
from agentic.telemetry.events import InMemoryEventPublisher
from agentic.tools.dummy import reset_dummy_state
from agentic.tools.provider import load_tool_bundle


DEFAULT_DATASET = Path("agentic/evals/datasets/functionality.jsonl")
DEFAULT_OUTPUT = Path("outputs/functionality-eval-report.json")
DEFAULT_EVALUATION_MODEL = "MiniMax-M2.7-highspeed"
USER_ID = "evaluation-user"
TENANT_ID = "evaluation-tenant"
SCOPES = frozenset({"financial:read", "financial:write", "investment:trade"})


def _evaluation_config(config: AppConfig, model: str) -> AppConfig:
    """Pin every evaluator model role to MiniMax, independently of app overrides."""

    llm = config.llm.model_copy(
        update={
            "models": {
                role: item.model_copy(update={"provider": "minimax", "model": model})
                for role, item in config.llm.models.items()
            }
        }
    )
    return config.model_copy(update={"llm": llm})


def _request(case: FunctionalityEvalCase) -> AgenticRequest:
    return AgenticRequest(
        request_id=uuid4(),
        session_id=uuid4(),
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        language=case.language,
        natural_language_request=case.input,
        original_user_message=case.input,
        authorization=AuthorizationContext(
            scopes=SCOPES,
            authenticated_at=datetime.now(timezone.utc),
            assurance_level="functionality-evaluation",
        ),
    )


async def _task(database: Database, task_id: UUID) -> AgentTaskRow:
    async with database.session() as session:
        row = await session.scalar(select(AgentTaskRow).where(AgentTaskRow.id == str(task_id)))
        if row is None:
            raise RuntimeError(f"evaluation task disappeared: {task_id}")
        session.expunge(row)
        return row


async def _executions(database: Database, task_id: UUID) -> list[ToolExecutionRow]:
    async with database.session() as session:
        rows = list(
            await session.scalars(
                select(ToolExecutionRow)
                .where(ToolExecutionRow.task_id == str(task_id))
                .order_by(ToolExecutionRow.created_at, ToolExecutionRow.id)
            )
        )
        for row in rows:
            session.expunge(row)
        return rows


def _event(
    publisher: InMemoryEventPublisher,
    task_id: UUID,
    event_type: AgentEventType,
):
    return next(
        (
            event
            for event in reversed(publisher.events)
            if event.task_id == task_id and event.event_type == event_type
        ),
        None,
    )


def _functional_status(
    *,
    clarification_requested: bool,
    tools: list[ObservedToolCall],
    report: dict[str, Any] | None,
) -> str:
    """Resolve workflow outcome from authoritative execution before report wording."""

    if clarification_requested:
        return "needs_input"
    if any(tool.status == "failed" for tool in tools):
        return "failed"
    if report and report.get("status") in {"failed", "rejected"}:
        return "failed"
    return "completed"


async def _observe_case(
    *,
    case: FunctionalityEvalCase,
    service: AgentService,
    database: Database,
    publisher: InMemoryEventPublisher,
    signer: ConfirmationSigner,
) -> FunctionalityObservation:
    await reset_dummy_state()
    request = _request(case)
    accepted = await service.submit(request, background=False)
    row = await _task(database, accepted.task_id)
    confirmation = _event(publisher, accepted.task_id, AgentEventType.CONFIRMATION_NEEDED)
    clarification = _event(publisher, accepted.task_id, AgentEventType.INPUT_NEEDED)

    if confirmation is not None:
        arguments = confirmation.details.get("arguments")
        tool_name = confirmation.details.get("tool_name")
        if not isinstance(arguments, dict) or not isinstance(tool_name, str):
            raise RuntimeError(f"invalid confirmation event for {case.id}")
        token = signer.issue(
            auth=AuthContext(USER_ID, TENANT_ID, str(request.session_id), SCOPES),
            task_id=str(accepted.task_id),
            tool_name=tool_name,
            arguments=arguments,
        )
        await service.resume(
            accepted.task_id,
            ResumeTaskRequest(
                request_id=request.request_id,
                session_id=request.session_id,
                user_id=USER_ID,
                tenant_id=TENANT_ID,
                authorization_token=token,
                otp_code="1111",
            ),
        )
        row = await _task(database, accepted.task_id)

    executions = await _executions(database, accepted.task_id)
    tools = [
        ObservedToolCall(
            name=item.tool_name,
            arguments=item.arguments or {},
            status=item.status,
            receipt_id=item.receipt_id,
            error_code=item.error_code,
        )
        for item in executions
    ]
    status = _functional_status(
        clarification_requested=clarification is not None,
        tools=tools,
        report=row.final_report,
    )
    return FunctionalityObservation(
        status=status,
        intent=row.intent,
        risk=row.risk,
        tools=tools,
        confirmation_requested=confirmation is not None,
        clarification_requested=clarification is not None,
        report=row.final_report,
    )


async def run_live_functionality_eval(
    dataset: Path,
    *,
    limit: int | None = None,
    scenario: str | None = None,
    model: str = DEFAULT_EVALUATION_MODEL,
):
    cases = load_functionality_dataset(dataset)
    if scenario is not None:
        cases = [case for case in cases if case.scenario == scenario]
        if not cases:
            raise ValueError(f"unknown functionality scenario: {scenario}")
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        cases = cases[:limit]

    config = _evaluation_config(load_config(), model)
    bundle = load_tool_bundle(
        "agentic.tools.dummy:DUMMY_TOOLS",
        config.tools.tools,
        require_tools=True,
    )
    models = ModelFactory(config.llm)
    database = Database(
        config.secrets.database_url.get_secret_value(),
        pool_size=config.app.database.pool_size,
        max_overflow=config.app.database.max_overflow,
        pool_timeout=config.app.database.pool_timeout_seconds,
    )
    signer = ConfirmationSigner(config.secrets.confirmation_signing_key.get_secret_value())
    publisher = InMemoryEventPublisher()
    graph = build_financial_agent(
        primary_model=models.create("primary"),
        classifier_model=models.create("intent_classifier"),
        advisor_model=models.create("financial_advisor"),
        external_tools=bundle.tools,
        tool_metadata=bundle.metadata,
        config=config,
        checkpointer=InMemorySaver(),
        fallback_models=models.create_fallbacks("primary"),
        advisor_fallback_models=models.create_fallbacks("financial_advisor"),
    )
    service = AgentService(
        graph=graph,
        database=database,
        config=config,
        confirmation_signer=signer,
        events=publisher,
    )
    observations: list[FunctionalityObservation] = []
    try:
        for index, case in enumerate(cases, 1):
            print(f"[{index:03}/{len(cases):03}] {case.id}", flush=True)
            try:
                observations.append(
                    await _observe_case(
                        case=case,
                        service=service,
                        database=database,
                        publisher=publisher,
                        signer=signer,
                    )
                )
            except Exception as exc:
                # A provider or workflow failure is an evaluation result, not a reason to
                # discard the remaining matrix. Avoid serializing exception text because it
                # may contain connection details or provider response fragments.
                observations.append(
                    FunctionalityObservation(
                        status="failed",
                        report={"evaluation_error_type": type(exc).__name__},
                    )
                )
    finally:
        await database.dispose()
    return build_functionality_report(cases, observations)


def _print_summary(report) -> None:
    print(
        f"Functionality evaluation: {report.passed}/{report.total} cases "
        f"({report.pass_rate:.0%}); {report.checks_passed}/{report.checks} checks "
        f"({report.check_rate:.0%})"
    )
    print("\nScenario                 passed")
    for row in report.scenarios:
        print(f"{row.name:25} {row.passed:3}/{row.total:<3}")
    failures = [result for result in report.results if not result.passed]
    if failures:
        print("\nFailures:")
        for result in failures:
            details = ", ".join(
                f"{item.field}: expected={item.expected!r} actual={item.actual!r}"
                for item in result.mismatches
            )
            print(f"  {result.case_id}: {details}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate financial functionality end to end")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--scenario")
    parser.add_argument(
        "--model",
        default=DEFAULT_EVALUATION_MODEL,
        help="MiniMax model id used for every evaluation role",
    )
    args = parser.parse_args()
    report = asyncio.run(
        run_live_functionality_eval(
            args.dataset,
            limit=args.limit,
            scenario=args.scenario,
            model=args.model,
        )
    )
    write_functionality_report(report, args.output)
    _print_summary(report)
    print(f"\nwrote {args.output}")
    if report.passed != report.total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
