"""usage_events plus api key limits

Revision ID: 029
Revises: 028
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("max_requests_per_minute", sa.Integer(), nullable=True))
    op.add_column("api_keys", sa.Column("max_requests_per_day", sa.Integer(), nullable=True))
    op.add_column("api_keys", sa.Column("max_chars_per_request", sa.Integer(), nullable=True))
    op.add_column("api_keys", sa.Column("max_chars_per_month", sa.Integer(), nullable=True))
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(), nullable=True))

    op.create_table(
        "usage_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("api_key_id", UUID(as_uuid=True), sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=True),
        sa.Column("policy_id", sa.String(100), nullable=True),
        sa.Column("policy_version", sa.String(50), nullable=True),
        sa.Column("policy_hash", sa.String(128), nullable=True),
        sa.Column("chars_in", sa.Integer(), nullable=False),
        sa.Column("chars_out", sa.Integer(), nullable=False),
        sa.Column("entities_count", sa.Integer(), nullable=False),
        sa.Column("entity_types_summary", JSONB, nullable=False, server_default="[]"),
        sa.Column("engine_regex_used", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("engine_presidio_used", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("engine_privacy_filter_used", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("engine_ai4privacy_used", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usage_events_api_key_created_at", "usage_events", ["api_key_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_api_key_created_at", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "max_chars_per_month")
    op.drop_column("api_keys", "max_chars_per_request")
    op.drop_column("api_keys", "max_requests_per_day")
    op.drop_column("api_keys", "max_requests_per_minute")