"""add the user-owned Nafi wallet balance

Revision ID: a1d7e3c9b5f2
Revises: f6a9c2d4e810
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a1d7e3c9b5f2"
down_revision: str | None = "f6a9c2d4e810"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "nafi_balance",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_users_nafi_balance",
        "users",
        "nafi_balance >= 0",
    )

    # Before this wallet existed, financial tools treated the primary linked
    # account as their operational balance. Preserve each existing customer's
    # spendable amount once, then all future mutations target nafi_balance only.
    op.execute(
        """
        UPDATE users AS u
           SET nafi_balance = primary_account.balance_sar
          FROM bank_accounts AS primary_account
         WHERE primary_account.user_uuid = u.uuid
           AND primary_account.is_primary
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_nafi_balance", "users", type_="check")
    op.drop_column("users", "nafi_balance")
