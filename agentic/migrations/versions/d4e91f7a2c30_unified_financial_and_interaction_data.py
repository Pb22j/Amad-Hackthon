"""unified PostgreSQL financial, customer, and interaction data

Revision ID: d4e91f7a2c30
Revises: 8c6b42e91d2a
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e91f7a2c30"
down_revision: str | None = "8c6b42e91d2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UUID = postgresql.UUID(as_uuid=False)
JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(18, 2)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "platform_users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("phone_e164", sa.String(20), nullable=False, unique=True),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="SA"),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("role", sa.String(40), nullable=False, server_default="user"),
        sa.Column("preferred_language", sa.String(5), nullable=False, server_default="ar"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Asia/Riyadh"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','inactive','suspended')", name="ck_platform_user_status"),
    )
    op.create_index("ix_platform_users_phone", "platform_users", ["phone_e164"])

    op.create_table(
        "users",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column("tenant_id", sa.String(200), nullable=False, server_default="evaluation-tenant"),
        sa.Column("platform_user_id", sa.BigInteger(), sa.ForeignKey("platform_users.id")),
        sa.Column("username", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("source_username", sa.String(200), nullable=False),
        sa.Column("full_name_ar", sa.String(200), nullable=False),
        sa.Column("full_name_en", sa.String(200)),
        sa.Column("dateofbirth", sa.Date()),
        sa.Column("gender", sa.String(10)),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("phone_e164", sa.String(20), nullable=False, unique=True),
        sa.Column("nationality_code", sa.String(2), nullable=False, server_default="SA"),
        sa.Column("preferred_language", sa.String(5), nullable=False, server_default="ar"),
        sa.Column("bank_name_ar", sa.String(200), nullable=False),
        sa.Column("account_number", sa.String(34), nullable=False, unique=True),
        sa.Column("account_type_ar", sa.String(100), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("balance_sar", MONEY, nullable=False, server_default="0"),
        sa.Column("available_balance_sar", MONEY, nullable=False, server_default="0"),
        sa.Column("daily_spend_limit_sar", MONEY, nullable=False, server_default="5000"),
        sa.Column("hashedpassword", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("nafath_linked", sa.String(3), nullable=False, server_default="No"),
        sa.Column("kyc_status", sa.String(20), nullable=False, server_default="verified"),
        sa.Column("kyc_tier", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("risk_rating", sa.String(20), nullable=False, server_default="low"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("gender IN ('Male','Female')", name="ck_users_gender"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_users_status"),
        sa.CheckConstraint("nafath_linked IN ('Yes','No')", name="ck_users_nafath"),
        sa.CheckConstraint("balance_sar >= 0 AND available_balance_sar >= 0", name="ck_users_balances"),
        sa.CheckConstraint("daily_spend_limit_sar > 0", name="ck_users_daily_limit"),
        sa.UniqueConstraint("tenant_id", "source_username", "account_number", name="uq_users_source_identity"),
    )
    op.create_index("ix_users_tenant_username", "users", ["tenant_id", "username"])

    op.create_table(
        "beneficiaries",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column("owner_uuid", UUID, sa.ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("short_name", postgresql.CITEXT(), nullable=False),
        sa.Column("account_number", sa.String(34), nullable=False),
        sa.Column("bank_name_ar", sa.String(200)),
        sa.Column("relationship", sa.String(50)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_beneficiaries_status"),
        sa.UniqueConstraint("owner_uuid", "account_number", name="uq_beneficiary_account"),
        sa.UniqueConstraint("owner_uuid", "short_name", name="uq_beneficiary_short_name"),
    )
    op.create_index("ix_beneficiaries_owner", "beneficiaries", ["owner_uuid"])

    op.create_table(
        "qattas",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column("creator_uuid", UUID, sa.ForeignKey("users.uuid"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("total_amount_sar", MONEY, nullable=False),
        sa.Column("share_amount_sar", MONEY, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_amount_sar > 0 AND share_amount_sar > 0", name="ck_qattas_amounts"),
        sa.CheckConstraint("status IN ('open','completed','cancelled')", name="ck_qattas_status"),
    )
    op.create_index("ix_qattas_creator", "qattas", ["creator_uuid"])

    op.create_table(
        "qatta_bills",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column("qatta_uuid", UUID, sa.ForeignKey("qattas.uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_uuid", UUID, sa.ForeignKey("users.uuid"), nullable=False),
        sa.Column("amount_sar", MONEY, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="unpaid"),
        sa.Column("paidat", sa.DateTime(timezone=True)),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_sar > 0", name="ck_qatta_bills_amount"),
        sa.CheckConstraint("status IN ('unpaid','paid')", name="ck_qatta_bills_status"),
        sa.UniqueConstraint("qatta_uuid", "participant_uuid", name="uq_qatta_participant"),
    )
    op.create_index("ix_qatta_bills_participant", "qatta_bills", ["participant_uuid", "status"])

    op.create_table(
        "fatoorahs",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column("user_uuid", UUID, sa.ForeignKey("users.uuid"), nullable=False),
        sa.Column("bill_number", sa.String(32), nullable=False, unique=True),
        sa.Column("biller_name_ar", sa.String(200), nullable=False),
        sa.Column("biller_code", sa.String(20)),
        sa.Column("amount_sar", MONEY, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="unpaid"),
        sa.Column("duedate", sa.DateTime(timezone=True)),
        sa.Column("paidat", sa.DateTime(timezone=True)),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("bill_number ~ '^[0-9]+$'", name="ck_fatoorah_bill_number"),
        sa.CheckConstraint("amount_sar > 0", name="ck_fatoorah_amount"),
        sa.CheckConstraint("status IN ('unpaid','paid')", name="ck_fatoorah_status"),
    )
    op.create_index("ix_fatoorahs_user_status", "fatoorahs", ["user_uuid", "status"])

    op.create_table(
        "transactions",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column("user_uuid", UUID, sa.ForeignKey("users.uuid"), nullable=False),
        sa.Column("account_number", sa.String(34), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("transaction_type", sa.String(60), nullable=False),
        sa.Column("amount_sar", MONEY, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("counterparty_name", sa.String(200)),
        sa.Column("counterparty_account", sa.String(34)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(80), nullable=False, server_default="general"),
        sa.Column("balance_after_sar", MONEY, nullable=False),
        sa.Column("reference", sa.String(100), nullable=False, unique=True),
        sa.Column("channel", sa.String(30), nullable=False, server_default="agentic"),
        sa.Column("merchant_city", sa.String(100)),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("direction IN ('debit','credit')", name="ck_transactions_direction"),
        sa.CheckConstraint("amount_sar > 0", name="ck_transactions_amount"),
    )
    op.create_index("ix_transactions_user_created", "transactions", ["user_uuid", "createdat"])
    op.create_index("ix_transactions_account_created", "transactions", ["account_number", "createdat"])

    op.create_table(
        "investment_assets",
        sa.Column("symbol", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("asset_class", sa.String(30), nullable=False, server_default="equity"),
        sa.Column("exchange", sa.String(40), nullable=False, server_default="Tadawul"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="SAR"),
        sa.Column("price_sar", MONEY, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price_sar > 0", name="ck_assets_price"),
    )
    op.create_table(
        "investment_holdings",
        sa.Column("uuid", UUID, primary_key=True),
        sa.Column("user_uuid", UUID, sa.ForeignKey("users.uuid"), nullable=False),
        sa.Column("symbol", sa.String(20), sa.ForeignKey("investment_assets.symbol"), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("average_cost_sar", MONEY, nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 0 AND average_cost_sar >= 0", name="ck_holdings_values"),
        sa.UniqueConstraint("user_uuid", "symbol", name="uq_holding_user_symbol"),
    )
    op.create_index("ix_investment_holdings_user", "investment_holdings", ["user_uuid"])

    op.create_table(
        "interaction_sessions",
        sa.Column("session_id", UUID, primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.String(200), nullable=False),
        sa.Column("tenant_id", sa.String(200), nullable=False),
        sa.Column("language", sa.String(5), nullable=False),
        sa.Column("scopes_json", JSONB, nullable=False),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_interaction_sessions_identity", "interaction_sessions", ["tenant_id", "user_id", "created_at"])
    op.create_table(
        "interaction_requests",
        sa.Column("request_id", UUID, primary_key=True),
        sa.Column("session_id", UUID, sa.ForeignKey("interaction_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interaction_requests_session", "interaction_requests", ["session_id", "created_at"])
    op.create_table(
        "interaction_tasks",
        sa.Column("task_id", UUID, primary_key=True),
        sa.Column("request_id", UUID, sa.ForeignKey("interaction_requests.request_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("session_id", UUID, sa.ForeignKey("interaction_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("pending_event_json", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interaction_tasks_session", "interaction_tasks", ["session_id", "updated_at"])
    op.create_table(
        "interaction_events",
        sa.Column("event_hash", sa.String(64), primary_key=True),
        sa.Column("task_id", UUID, sa.ForeignKey("interaction_tasks.task_id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID, sa.ForeignKey("interaction_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_interaction_events_session", "interaction_events", ["session_id", "created_at"])
    op.create_table(
        "voice_turns",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("session_id", UUID, sa.ForeignKey("interaction_sessions.session_id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("encrypted_text", sa.LargeBinary(), nullable=False),
        sa.Column("provenance", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_voice_turn_role"),
    )
    op.create_index("ix_voice_turns_session", "voice_turns", ["session_id", "role", "created_at"])


def downgrade() -> None:
    for table in (
        "voice_turns", "interaction_events", "interaction_tasks", "interaction_requests",
        "interaction_sessions", "investment_holdings", "investment_assets", "transactions",
        "fatoorahs", "qatta_bills", "qattas", "beneficiaries", "users", "platform_users",
    ):
        op.drop_table(table)
