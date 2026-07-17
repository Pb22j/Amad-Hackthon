"""Operational commands for database setup, retention, and security evals."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from agentic.config.loader import load_config
from agentic.evals.runner import SecurityEvalReport, run_security_dataset
from agentic.persistence.checkpointer import postgres_checkpointer
from agentic.persistence.database import Database
from agentic.persistence.repositories.retention import RetentionRepository
from agentic.persistence.store import postgres_memory_store
from agentic.policy.engine import PolicyEngine


def print_security_summary(report: SecurityEvalReport) -> None:
    print(f"Security screening evaluation: {report.passed}/{report.total} ({report.pass_rate:.0%})")
    print(f"  regressions : {len(report.failures)}")
    print(f"  known gaps  : {len(report.known_gaps)}")
    print("\n  category                     passed   gaps")
    for row in report.categories:
        print(f"  {row.category:26} {row.passed:3}/{row.total:<3} {row.known_gaps:5}")
    if report.known_gaps:
        print("\nKnown gaps (documented, not fatal):")
        for gap in report.known_gaps:
            print(f"  [{gap.category}] {gap.case_id}: expected {gap.expected}, got {gap.actual}")
    if report.fixed_gaps:
        print("\nGaps that now pass; remove their known_gap marker:")
        for case_id in report.fixed_gaps:
            print(f"  {case_id}")
    if report.failures:
        print("\nRegressions:")
        for failure in report.failures:
            print(
                f"  [{failure.category}] {failure.case_id}: "
                f"expected {failure.expected}, got {failure.actual}"
            )


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
    eval_security = subcommands.add_parser(
        "eval-security", help="Run the deterministic security dataset"
    )
    eval_security.add_argument(
        "--json", action="store_true", help="Emit the full report as JSON instead of a summary"
    )
    eval_security.add_argument(
        "--dataset",
        choices=("baseline", "holdout", "challenge"),
        default="baseline",
        help="Select the documented baseline or strict 100-case holdout dataset",
    )
    subcommands.add_parser("cleanup-retention", help="Delete expired memory and checkpoints")
    args = parser.parse_args()
    if args.command == "setup-langgraph":
        asyncio.run(setup_langgraph())
    elif args.command == "eval-security":
        config = load_config()
        dataset_file = {
            "baseline": "security.jsonl",
            "holdout": "security_holdout.jsonl",
            "challenge": "security_challenge.jsonl",
        }[args.dataset]
        dataset = Path(__file__).parent / "evals" / "datasets" / dataset_file
        report = run_security_dataset(dataset, PolicyEngine(config.policies))
        if args.json:
            print(report.model_dump_json(indent=2))
        else:
            print_security_summary(report)
        # Documented gaps are reported but do not fail the suite; only an undocumented
        # mismatch is a regression.
        if report.failures or report.fixed_gaps:
            raise SystemExit(1)
    elif args.command == "cleanup-retention":
        asyncio.run(cleanup_retention())


if __name__ == "__main__":
    main()
