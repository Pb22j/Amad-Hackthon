"""link beneficiaries only by Nafi user identity

Revision ID: f6a9c2d4e810
Revises: 3b7a0f1d9c24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6a9c2d4e810"
down_revision: str | None = "3b7a0f1d9c24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in (
        "updatedat",
        "verified_at",
        "status",
        "relationship",
        "bank_name_ar",
        "account_number",
        "full_name",
    ):
        op.drop_column("beneficiaries", column)


def downgrade() -> None:
    op.add_column("beneficiaries", sa.Column("full_name", sa.String(200)))
    op.add_column("beneficiaries", sa.Column("account_number", sa.String(34)))
    op.add_column("beneficiaries", sa.Column("bank_name_ar", sa.String(200)))
    op.add_column("beneficiaries", sa.Column("relationship", sa.String(50)))
    op.add_column("beneficiaries", sa.Column("status", sa.String(20), server_default="active"))
    op.add_column("beneficiaries", sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.add_column("beneficiaries", sa.Column("updatedat", sa.DateTime(timezone=True)))
