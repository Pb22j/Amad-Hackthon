"""allow both ledger sides to share one operation reference

Revision ID: e2a47b19d8f1
Revises: d4e91f7a2c30
"""

from collections.abc import Sequence

from alembic import op


revision: str = "e2a47b19d8f1"
down_revision: str | None = "d4e91f7a2c30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("transactions_reference_key", "transactions", type_="unique")
    op.create_index("ix_transactions_reference", "transactions", ["reference"])


def downgrade() -> None:
    op.drop_index("ix_transactions_reference", table_name="transactions")
    op.create_unique_constraint("transactions_reference_key", "transactions", ["reference"])
