"""add request fingerprint and event outbox

Revision ID: 8c6b42e91d2a
Revises: 4f2d8a9c1b7e
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "8c6b42e91d2a"
down_revision: str | None = "4f2d8a9c1b7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_tasks",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "event_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_outbox_pending",
        "event_outbox",
        ["delivered_at", "next_attempt_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_event_outbox_pending", table_name="event_outbox")
    op.drop_table("event_outbox")
    op.drop_column("agent_tasks", "request_fingerprint")
