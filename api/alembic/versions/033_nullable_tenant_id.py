"""add nullable tenant_id to core tables for multi-tenancy support

Revision ID: 033
Revises: 032
Create Date: 2026-06-16

When multitenancy_enabled=false (self-hosted default) these columns remain NULL
and all queries behave exactly as before. No breaking change.
"""

from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("tenant_id", sa.String(100), nullable=True))
    op.add_column("domain_policies", sa.Column("tenant_id", sa.String(100), nullable=True))
    op.add_column("context_types", sa.Column("tenant_id", sa.String(100), nullable=True))
    op.add_column("audit_logs", sa.Column("tenant_id", sa.String(100), nullable=True))

    # Partial indexes: only index rows that actually have a tenant (cloud mode).
    # Self-hosted rows (NULL) are not indexed, keeping overhead zero.
    op.create_index(
        "ix_api_keys_tenant_id",
        "api_keys",
        ["tenant_id"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "ix_domain_policies_tenant_id",
        "domain_policies",
        ["tenant_id"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "ix_context_types_tenant_id",
        "context_types",
        ["tenant_id"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "ix_audit_logs_tenant_id",
        "audit_logs",
        ["tenant_id"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    # usage_events already has tenant_id — just add the same partial index
    op.create_index(
        "ix_usage_events_tenant_id",
        "usage_events",
        ["tenant_id"],
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_usage_events_tenant_id", table_name="usage_events")
    op.drop_index("ix_audit_logs_tenant_id", table_name="audit_logs")
    op.drop_index("ix_context_types_tenant_id", table_name="context_types")
    op.drop_index("ix_domain_policies_tenant_id", table_name="domain_policies")
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")

    op.drop_column("audit_logs", "tenant_id")
    op.drop_column("context_types", "tenant_id")
    op.drop_column("domain_policies", "tenant_id")
    op.drop_column("api_keys", "tenant_id")
