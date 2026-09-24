"""Persisted asynchronous anonymization jobs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "anonymization_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("request_encrypted", sa.Text(), nullable=False),
        sa.Column("result_encrypted", sa.Text(), nullable=True),
        sa.Column("webhook_url", sa.String(2048), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"]),
    )
    op.create_index("ix_anonymization_jobs_tenant_id", "anonymization_jobs", ["tenant_id"])
    op.create_index("ix_anonymization_jobs_status", "anonymization_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_anonymization_jobs_status", table_name="anonymization_jobs")
    op.drop_index("ix_anonymization_jobs_tenant_id", table_name="anonymization_jobs")
    op.drop_table("anonymization_jobs")
