"""add Nafi liquid savings and idle-cash recommendations

Revision ID: f2a6c8e4d1b3
Revises: c9f51a2e7d44
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a6c8e4d1b3"
down_revision: str | None = "c9f51a2e7d44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UUID = postgresql.UUID(as_uuid=False)
MONEY = sa.Numeric(18, 2)


def upgrade() -> None:
    op.create_table(
        "nafi_savings_accounts",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column(
            "user_uuid",
            UUID,
            sa.ForeignKey("users.uuid", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_number", sa.String(40), nullable=False, unique=True),
        sa.Column("account_type", sa.String(30), nullable=False, server_default="liquid"),
        sa.Column("name", sa.String(100), nullable=False, server_default="Nafi Liquid Savings"),
        sa.Column("name_ar", sa.String(100), nullable=False, server_default="مدخرات نافي السائلة"),
        sa.Column("balance_sar", MONEY, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("balance_sar >= 0", name="ck_nafi_savings_balance"),
        sa.CheckConstraint("account_type = 'liquid'", name="ck_nafi_savings_type"),
        sa.UniqueConstraint("user_uuid", "account_type", name="uq_nafi_savings_user_type"),
    )
    op.create_index("ix_nafi_savings_user", "nafi_savings_accounts", ["user_uuid"])
    op.execute(
        """
        INSERT INTO nafi_savings_accounts
          (uuid, user_uuid, account_number, account_type, name, name_ar,
           balance_sar, created_at, updated_at)
        SELECT gen_random_uuid(), uuid,
               'NFS' || upper(substr(replace(uuid::text, '-', ''), 1, 29)),
               'liquid', 'Nafi Liquid Savings', 'مدخرات نافي السائلة',
               0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
          FROM users
        """
    )

    op.create_table(
        "idle_cash_recommendations",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column(
            "user_uuid",
            UUID,
            sa.ForeignKey("users.uuid", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("methodology_version", sa.String(30), nullable=False),
        sa.Column("analysis_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_months", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("emergency_months", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("average_monthly_spend_sar", MONEY, nullable=False),
        sa.Column("emergency_reserve_target_sar", MONEY, nullable=False),
        sa.Column("stable_operating_cash_sar", MONEY, nullable=False),
        sa.Column("regular_idle_cash_sar", MONEY, nullable=False),
        sa.Column("recommended_wallet_transfer_sar", MONEY, nullable=False),
        sa.Column("bank_deposit_required_sar", MONEY, nullable=False),
        sa.Column("wallet_balance_snapshot_sar", MONEY, nullable=False),
        sa.Column("wallet_liquid_savings_snapshot_sar", MONEY, nullable=False),
        sa.Column("linked_bank_operating_cash_sar", MONEY, nullable=False),
        sa.Column("linked_bank_liquid_savings_sar", MONEY, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("execution_reference", sa.String(100)),
        sa.CheckConstraint(
            "status IN ('active','executed','superseded','expired')",
            name="ck_idle_cash_recommendation_status",
        ),
        sa.CheckConstraint(
            "analysis_months = 3 AND emergency_months = 3",
            name="ck_idle_cash_three_month_method",
        ),
        sa.CheckConstraint(
            "average_monthly_spend_sar >= 0 AND emergency_reserve_target_sar >= 0 "
            "AND stable_operating_cash_sar >= 0 AND regular_idle_cash_sar >= 0 "
            "AND recommended_wallet_transfer_sar >= 0 AND bank_deposit_required_sar >= 0 "
            "AND wallet_balance_snapshot_sar >= 0 "
            "AND wallet_liquid_savings_snapshot_sar >= 0 "
            "AND linked_bank_operating_cash_sar >= 0 "
            "AND linked_bank_liquid_savings_sar >= 0",
            name="ck_idle_cash_recommendation_amounts",
        ),
    )
    op.create_index(
        "ix_idle_cash_recommendations_user_created",
        "idle_cash_recommendations",
        ["user_uuid", "created_at"],
    )
    op.create_index(
        "uq_idle_cash_active_user",
        "idle_cash_recommendations",
        ["user_uuid"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_table("idle_cash_recommendations")
    op.drop_table("nafi_savings_accounts")
