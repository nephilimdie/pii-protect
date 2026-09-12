"""Scope surrogate caches by tenant.

Revision ID: 048
Revises: 047
"""

from alembic import op
import sqlalchemy as sa


revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("surrogate_mappings", "surrogate_profiles"):
        op.add_column(table, sa.Column("tenant_id", sa.String(100), nullable=True))

    op.drop_constraint("uq_surrogate_mapping", "surrogate_mappings", type_="unique")
    op.create_index(
        "uq_surrogate_mapping_tenant",
        "surrogate_mappings",
        ["tenant_id", "context_id", "pii_type", "real_hash"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.drop_constraint("uq_surrogate_profile", "surrogate_profiles", type_="unique")
    op.create_index(
        "uq_surrogate_profile_tenant",
        "surrogate_profiles",
        ["tenant_id", "context_id", "real_hash"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_surrogate_mapping_self_hosted",
        "surrogate_mappings",
        ["context_id", "pii_type", "real_hash"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "uq_surrogate_profile_self_hosted",
        "surrogate_profiles",
        ["context_id", "real_hash"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "ix_surrogate_mappings_tenant_context",
        "surrogate_mappings",
        ["tenant_id", "context_id", "pii_type"],
    )
    op.create_index(
        "ix_surrogate_profiles_tenant_context",
        "surrogate_profiles",
        ["tenant_id", "context_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_surrogate_profiles_tenant_context", "surrogate_profiles")
    op.drop_index("ix_surrogate_mappings_tenant_context", "surrogate_mappings")
    op.drop_index("uq_surrogate_profile_self_hosted", "surrogate_profiles")
    op.drop_index("uq_surrogate_mapping_self_hosted", "surrogate_mappings")
    op.drop_index("uq_surrogate_profile_tenant", "surrogate_profiles")
    op.create_unique_constraint(
        "uq_surrogate_profile", "surrogate_profiles", ["context_id", "real_hash"]
    )
    op.drop_index("uq_surrogate_mapping_tenant", "surrogate_mappings")
    op.create_unique_constraint(
        "uq_surrogate_mapping",
        "surrogate_mappings",
        ["context_id", "pii_type", "real_hash"],
    )
    for table in ("surrogate_profiles", "surrogate_mappings"):
        op.drop_column(table, "tenant_id")
