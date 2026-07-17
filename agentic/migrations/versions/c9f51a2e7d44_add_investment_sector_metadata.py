"""add investment sector metadata

Revision ID: c9f51a2e7d44
Revises: b8e41c7d2a90
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c9f51a2e7d44"
down_revision: str | None = "b8e41c7d2a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "investment_assets",
        sa.Column("sector", sa.String(40), nullable=False, server_default="other"),
    )
    op.add_column(
        "investment_assets",
        sa.Column("sector_name", sa.String(100), nullable=False, server_default="Other"),
    )
    op.add_column(
        "investment_assets",
        sa.Column("sector_name_ar", sa.String(100), nullable=False, server_default="أخرى"),
    )
    op.execute(
        """
        UPDATE investment_assets
           SET sector = CASE symbol
                 WHEN 'ARAMCO' THEN 'energy'
                 WHEN 'ALRAJHI' THEN 'financials'
                 WHEN 'SABIC' THEN 'materials'
                 ELSE 'other'
               END,
               sector_name = CASE symbol
                 WHEN 'ARAMCO' THEN 'Energy'
                 WHEN 'ALRAJHI' THEN 'Financials'
                 WHEN 'SABIC' THEN 'Materials'
                 ELSE 'Other'
               END,
               sector_name_ar = CASE symbol
                 WHEN 'ARAMCO' THEN 'الطاقة'
                 WHEN 'ALRAJHI' THEN 'القطاع المالي'
                 WHEN 'SABIC' THEN 'المواد الأساسية'
                 ELSE 'أخرى'
               END
        """
    )


def downgrade() -> None:
    op.drop_column("investment_assets", "sector_name_ar")
    op.drop_column("investment_assets", "sector_name")
    op.drop_column("investment_assets", "sector")
