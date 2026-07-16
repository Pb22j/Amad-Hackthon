from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from agentic.config.environment import load_backend_environment
from agentic.persistence.models import Base


config = context.config
load_backend_environment()
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata

LANGGRAPH_TABLES = {
    "checkpoint_migrations",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoints",
    "store_migrations",
    "store",
    "store_vectors",
    "store_vector_migrations",
}

# These tables are shared by the DB-API-backed financial tools and interaction
# service. Their explicit migration is authoritative; excluding them keeps
# SQLAlchemy autogenerate from proposing destructive drops.
UNIFIED_RUNTIME_TABLES = {
    "users",
    "bank_accounts",
    "beneficiaries",
    "qattas",
    "qatta_bills",
    "fatoorahs",
    "transactions",
    "investment_assets",
    "investment_holdings",
    "interaction_sessions",
    "interaction_requests",
    "interaction_tasks",
    "interaction_events",
    "voice_turns",
}


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    if type_ == "table" and name in LANGGRAPH_TABLES | UNIFIED_RUNTIME_TABLES:
        return False
    return parent_names.get("table_name") not in LANGGRAPH_TABLES | UNIFIED_RUNTIME_TABLES


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
