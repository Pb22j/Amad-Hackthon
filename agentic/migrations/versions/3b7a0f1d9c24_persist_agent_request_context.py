"""persist agent request context

Revision ID: 3b7a0f1d9c24
Revises: e2a47b19d8f1
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "3b7a0f1d9c24"
down_revision: str | None = "e2a47b19d8f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The application writes AES-GCM ciphertext through EncryptedJSON. Existing
    # tasks remain NULL and safely resume without legacy conversation context.
    op.add_column(
        "agent_tasks",
        sa.Column("request_context", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_tasks", "request_context")
