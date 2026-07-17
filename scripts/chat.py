"""Interactive terminal chat with the Amad financial agent.

A local development harness that runs the full agent stack — intent
classification, policy screening, the guarded bank tools, clarification and
confirmation interrupts — against the real model and the configured PostgreSQL
database. It plays the interaction layer's role in the terminal: it shows
clarification questions, asks the human to approve financial actions, and
signs the confirmation token with the local development key.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    .venv/bin/python scripts/chat.py            # chat as evaluation-user
    .venv/bin/python scripts/chat.py --user admin

State: agent tasks and the bank ledger both persist in PostgreSQL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Development-only secrets, set before any agentic import reads them.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://amad:development-only-password@localhost:55432/amad",
)
os.environ.setdefault(
    "LANGGRAPH_DATABASE_URL",
    "postgresql://amad:development-only-password@localhost:55432/amad",
)
os.environ.setdefault(
    "BANK_DATABASE_URL",
    "postgresql://amad:development-only-password@localhost:55432/amad",
)
os.environ.setdefault("CONFIRMATION_SIGNING_KEY", "development-confirmation-key-0001")
os.environ.setdefault("CHECKPOINT_ENCRYPTION_KEY", "development-checkpoint-key-00001")
os.environ.setdefault("APP_DATA_ENCRYPTION_KEY", "development-appdata-key-00000001")
os.environ.setdefault("INTERACTION_SHARED_SECRET", "development-interaction-secret-1")

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from agentic.agent.graph import build_financial_agent  # noqa: E402
from agentic.agent.service import AgentService  # noqa: E402
from agentic.api.schemas import (  # noqa: E402
    AgenticRequest,
    AuthorizationContext,
    ResumeTaskRequest,
    TaskStatus,
    TaskStatusRequest,
    TERMINAL_TASK_STATUSES,
)
from agentic.config.loader import load_config  # noqa: E402
from agentic.llm.factory import ModelFactory  # noqa: E402
from agentic.persistence.database import Database  # noqa: E402
from agentic.security.confirmation import ConfirmationSigner  # noqa: E402
from agentic.security.identity import AuthContext  # noqa: E402
from agentic.telemetry.events import InMemoryEventPublisher  # noqa: E402
from agentic.tools.provider import load_tool_bundle  # noqa: E402

SCOPES = frozenset({"financial:read", "financial:write", "investment:trade"})
TENANT_ID = "evaluation-tenant"


def detect_language(text: str) -> str:
    return "ar" if any("؀" <= char <= "ۿ" for char in text) else "en"


def print_report(report: dict) -> None:
    print(f"\n🤖 {report.get('summary', '(no summary)')}")
    details = report.get("details")
    if details:
        print(json.dumps(details, ensure_ascii=False, indent=2, default=str))
    receipts = report.get("receipt_ids") or []
    for receipt in receipts:
        print(f"🧾 receipt: {receipt}")
    print()


async def drive_task(
    service: AgentService,
    signer: ConfirmationSigner,
    request: AgenticRequest,
    task_id: UUID,
    user_id: str,
) -> None:
    """Poll one task and walk it through clarification/confirmation to the end."""

    identity = TaskStatusRequest(
        request_id=request.request_id,
        session_id=request.session_id,
        user_id=user_id,
        tenant_id=TENANT_ID,
    )
    while True:
        status = await service.get_task_status(task_id, identity)
        if status.status in TERMINAL_TASK_STATUSES:
            if status.final_report:
                print_report(status.final_report)
            else:
                print(f"\n🤖 task ended with status: {status.status.value}\n")
            return

        if status.status == TaskStatus.WAITING_FOR_INPUT:
            pending = status.pending_action or {}
            print(f"\n❓ {pending.get('question', 'The agent needs more information.')}")
            answer = input("👤 answer> ").strip()
            await service.resume(
                task_id,
                ResumeTaskRequest(
                    request_id=request.request_id,
                    session_id=request.session_id,
                    user_id=user_id,
                    tenant_id=TENANT_ID,
                    clarification_id=UUID(pending["clarification_id"]),
                    answer=answer,
                ),
            )
            continue

        if status.status == TaskStatus.WAITING_FOR_CONFIRMATION:
            pending = status.pending_action or {}
            print("\n⚠️  the agent wants to execute a financial action:")
            print(f"   tool: {pending.get('tool_name')}")
            print(
                "   arguments: "
                + json.dumps(pending.get("arguments", {}), ensure_ascii=False, default=str)
            )
            approval = input("👤 confirm? [y/N]> ").strip().lower()
            if approval not in {"y", "yes", "نعم"}:
                print("🚫 not confirmed — the action was not executed.\n")
                return
            token = signer.issue(
                auth=AuthContext(user_id, TENANT_ID, str(request.session_id), SCOPES),
                task_id=str(task_id),
                tool_name=pending["tool_name"],
                arguments=pending["arguments"],
            )
            await service.resume(
                task_id,
                ResumeTaskRequest(
                    request_id=request.request_id,
                    session_id=request.session_id,
                    user_id=user_id,
                    tenant_id=TENANT_ID,
                    authorization_token=token,
                    otp_code=input("🔐 demo OTP [1111]> ").strip(),
                ),
            )
            continue

        await asyncio.sleep(0.2)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with the Amad financial agent")
    parser.add_argument(
        "--user",
        default="evaluation-user",
        help="Bank username to chat as (seeded: evaluation-user, admin)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Override every model role with this OpenRouter model id, e.g. a free one: "
            "openai/gpt-oss-120b:free"
        ),
    )
    args = parser.parse_args()

    if not os.getenv("OPENROUTER_API_KEY"):
        raise SystemExit(
            "OPENROUTER_API_KEY is not set. Export a key first:\n"
            "  export OPENROUTER_API_KEY=sk-or-..."
        )

    os.environ["BANK_TOOL_USER_ID"] = args.user
    os.environ["BANK_TOOL_TENANT_ID"] = TENANT_ID

    config = load_config()
    if args.model:
        overridden = {
            role: model.model_copy(update={"model": args.model})
            for role, model in config.llm.models.items()
            if role != "embeddings"
        }
        config = config.model_copy(
            update={
                "llm": config.llm.model_copy(
                    update={"models": {**config.llm.models, **overridden}}
                )
            }
        )
        print(f"model override: {args.model}")
    database = Database(config.secrets.database_url.get_secret_value())
    await database.create_schema()
    models = ModelFactory(config.llm)
    bundle = load_tool_bundle(
        config.app.agent.tool_provider, config.tools.tools, require_tools=True
    )
    signer = ConfirmationSigner(config.secrets.confirmation_signing_key.get_secret_value())
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
        events=InMemoryEventPublisher(),
        memory_extractor=None,
    )

    session_id = uuid4()
    tools = ", ".join(tool.name for tool in bundle.tools)
    print("=" * 60)
    print("Amad Financial Agent — local chat")
    print(f"user: {args.user} | tools: {tools}")
    print("type 'exit' to quit")
    print("=" * 60)

    try:
        while True:
            try:
                text = input("👤 ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in {"exit", "quit", "خروج"}:
                break

            request = AgenticRequest(
                request_id=uuid4(),
                session_id=session_id,
                user_id=args.user,
                tenant_id=TENANT_ID,
                language=detect_language(text),
                natural_language_request=text,
                original_user_message=text,
                authorization=AuthorizationContext(
                    scopes=SCOPES,
                    authenticated_at=datetime.now(timezone.utc),
                    assurance_level="aal2",
                ),
            )
            accepted = None
            for attempt in range(3):
                # Retries need a fresh request_id; status polling must use the
                # same one, so the resubmitted request replaces the original.
                request = request.model_copy(update={"request_id": uuid4()})
                try:
                    accepted = await service.submit(request, background=False)
                    break
                except Exception as exc:  # surfaced to the terminal, not the model
                    message = str(exc)
                    if "429" in message and attempt < 2:
                        match = re.search(r"retry_after_seconds': (\d+)", message)
                        delay = min(int(match.group(1)) if match else 30, 60) + 2
                        print(f"⏳ free model is busy — retrying in {delay}s...")
                        await asyncio.sleep(delay)
                        continue
                    print(f"💥 request failed: {exc}\n")
                    break
            if accepted is None:
                continue
            if accepted.status == "rejected":
                print(f"🚫 {accepted.user_safe_message or 'request rejected'}\n")
                continue
            try:
                await drive_task(service, signer, request, accepted.task_id, args.user)
            except Exception as exc:
                print(f"💥 task failed: {exc}\n")
    finally:
        await service.wait_for_background_tasks()
        await database.dispose()
        print("bye 👋")


if __name__ == "__main__":
    asyncio.run(main())
