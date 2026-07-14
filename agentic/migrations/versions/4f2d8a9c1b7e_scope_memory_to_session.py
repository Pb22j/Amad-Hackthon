"""scope curated memory to an authenticated session

Revision ID: 4f2d8a9c1b7e
Revises: c7c35a156d7c
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "4f2d8a9c1b7e"
down_revision: str | None = "c7c35a156d7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_items",
        sa.Column(
            "session_id",
            sa.String(length=36),
            nullable=False,
            server_default="legacy-unscoped",
        ),
    )
    # Recover the exact session whenever provenance points at a durable task.
    op.execute(
        sa.text(
            """
            UPDATE memory_items
            SET session_id = (
                SELECT agent_tasks.session_id
                FROM agent_tasks
                WHERE agent_tasks.id = memory_items.source_task_id
            )
            WHERE source_task_id IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM agent_tasks
                WHERE agent_tasks.id = memory_items.source_task_id
              )
            """
        )
    )
    op.alter_column("memory_items", "session_id", server_default=None)
    op.drop_index("ix_memory_namespace", table_name="memory_items")
    op.drop_constraint("uq_memory_item", "memory_items", type_="unique")
    op.create_unique_constraint(
        "uq_memory_item",
        "memory_items",
        ["tenant_id", "user_id", "session_id", "memory_type", "deduplication_key"],
    )
    op.create_index(
        "ix_memory_namespace",
        "memory_items",
        ["tenant_id", "user_id", "session_id", "memory_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_memory_namespace", table_name="memory_items")
    op.drop_constraint("uq_memory_item", "memory_items", type_="unique")
    op.create_unique_constraint(
        "uq_memory_item",
        "memory_items",
        ["tenant_id", "user_id", "memory_type", "deduplication_key"],
    )
    op.create_index(
        "ix_memory_namespace",
        "memory_items",
        ["tenant_id", "user_id", "memory_type"],
        unique=False,
    )
    op.drop_column("memory_items", "session_id")
