"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "pii_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("context_id", sa.String(255), nullable=False),
        sa.Column("context_type", sa.String(50), nullable=False),
        sa.Column("token", sa.String(100), nullable=False),
        sa.Column("original_encrypted", sa.Text(), nullable=False),
        sa.Column("pii_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("context_id", "context_type", "token", name="uq_mapping_context_token"),
    )
    op.create_index("ix_pii_mappings_context", "pii_mappings", ["context_id", "context_type"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("api_key_id", UUID(as_uuid=True), sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column("action", sa.String(50), nullable=True),
        sa.Column("context_id", sa.String(255), nullable=True),
        sa.Column("pii_types_found", JSON(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index("ix_pii_mappings_context", table_name="pii_mappings")
    op.drop_table("pii_mappings")
    op.drop_table("api_keys")
