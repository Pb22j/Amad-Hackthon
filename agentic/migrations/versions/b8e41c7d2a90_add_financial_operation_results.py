"""add provider-side financial operation reconciliation results

Revision ID: b8e41c7d2a90
Revises: a1d7e3c9b5f2
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b8e41c7d2a90"
down_revision: str | None = "a1d7e3c9b5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_operation_results",
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False),
        sa.Column("user_id", sa.String(200), nullable=False),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("financial_operation_results")
