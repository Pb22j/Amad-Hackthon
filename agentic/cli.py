from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from agentic.config.loader import load_config
from agentic.evals.runner import run_security_dataset
from agentic.persistence.checkpointer import postgres_checkpointer
from agentic.persistence.database import Database
from agentic.persistence.repositories.retention import RetentionRepository
from agentic.persistence.store import postgres_memory_store
from agentic.policy.engine import PolicyEngine


async def setup_langgraph() -> None:
    config = load_config()
    connection_string = config.secrets.langgraph_database_url.get_secret_value()
    encryption_key = (
        config.secrets.checkpoint_encryption_key.get_secret_value()
        if config.secrets.checkpoint_encryption_key
        else ""
    )
    async with postgres_checkpointer(
        connection_string, encryption_key=encryption_key, setup=True
    ):
        pass
    async with postgres_memory_store(connection_string, setup=True):
        pass


async def cleanup_retention() -> None:
    config = load_config()
    database = Database(
        config.secrets.database_url.get_secret_value(),
        pool_size=config.app.database.pool_size,
        max_overflow=config.app.database.max_overflow,
        pool_timeout=config.app.database.pool_timeout_seconds,
    )
    try:
        async with database.session() as session:
            task_ids, deleted_memories = await RetentionRepository(session).cleanup_expired()
        connection_string = config.secrets.langgraph_database_url.get_secret_value()
        encryption_key = (
            config.secrets.checkpoint_encryption_key.get_secret_value()
            if config.secrets.checkpoint_encryption_key
            else ""
        )
        async with postgres_checkpointer(
            connection_string, encryption_key=encryption_key, setup=False
        ) as checkpointer:
            for task_id in task_ids:
                await checkpointer.adelete_thread(task_id)
        print(f"deleted_checkpoints={len(task_ids)} deleted_memories={deleted_memories}")
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Amad financial agent operations")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("setup-langgraph", help="Create or migrate LangGraph storage")
    subcommands.add_parser("eval-security", help="Run the deterministic security dataset")
    subcommands.add_parser("cleanup-retention", help="Delete expired memory and checkpoints")
    args = parser.parse_args()
    if args.command == "setup-langgraph":
        asyncio.run(setup_langgraph())
    elif args.command == "eval-security":
        config = load_config()
        dataset = Path(__file__).parent / "evals" / "datasets" / "security.jsonl"
        report = run_security_dataset(dataset, PolicyEngine(config.policies))
        print(report.model_dump_json(indent=2))
        if report.failures:
            raise SystemExit(1)
    elif args.command == "cleanup-retention":
        asyncio.run(cleanup_retention())


if __name__ == "__main__":
    main()
