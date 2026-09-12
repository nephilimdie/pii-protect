"""Add project scope to reversible mappings.

Revision ID: 051
Revises: 050
"""

from alembic import op
import sqlalchemy as sa


revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("pii_mappings", "surrogate_mappings", "surrogate_profiles"):
        op.add_column(table, sa.Column("project_id", sa.String(100), nullable=False, server_default="default"))
        op.alter_column(table, "project_id", server_default=None)

    # Migration 036 replaced this constraint with two partial indexes. Drop
    # either representation so upgrades remain valid from every supported DB.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'pii_mappings'::regclass
                  AND conname = 'uq_mapping_tenant_context_token'
            ) THEN
                ALTER TABLE pii_mappings
                DROP CONSTRAINT uq_mapping_tenant_context_token;
            END IF;
        END $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS uix_mapping_tenant_not_null")
    op.execute("DROP INDEX IF EXISTS uix_mapping_tenant_null")
    op.create_unique_constraint(
        "uq_mapping_tenant_project_context_token",
        "pii_mappings",
        ["tenant_id", "project_id", "context_id", "context_type", "token"],
    )
    for name, table in (
        ("uq_surrogate_mapping_tenant", "surrogate_mappings"),
        ("uq_surrogate_mapping_self_hosted", "surrogate_mappings"),
        ("uq_surrogate_profile_tenant", "surrogate_profiles"),
        ("uq_surrogate_profile_self_hosted", "surrogate_profiles"),
    ):
        op.drop_index(name, table_name=table)
    op.create_index(
        "uq_surrogate_mapping_tenant_project", "surrogate_mappings",
        ["tenant_id", "project_id", "context_id", "pii_type", "real_hash"], unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_surrogate_mapping_self_hosted_project", "surrogate_mappings",
        ["project_id", "context_id", "pii_type", "real_hash"], unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )
    op.create_index(
        "uq_surrogate_profile_tenant_project", "surrogate_profiles",
        ["tenant_id", "project_id", "context_id", "real_hash"], unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_surrogate_profile_self_hosted_project", "surrogate_profiles",
        ["project_id", "context_id", "real_hash"], unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )


def downgrade() -> None:
    for name, table in (
        ("uq_surrogate_mapping_tenant_project", "surrogate_mappings"),
        ("uq_surrogate_mapping_self_hosted_project", "surrogate_mappings"),
        ("uq_surrogate_profile_tenant_project", "surrogate_profiles"),
        ("uq_surrogate_profile_self_hosted_project", "surrogate_profiles"),
    ):
        op.drop_index(name, table_name=table)
    op.create_index("uq_surrogate_mapping_tenant", "surrogate_mappings", ["tenant_id", "context_id", "pii_type", "real_hash"], unique=True, postgresql_where=sa.text("tenant_id IS NOT NULL"))
    op.create_index("uq_surrogate_mapping_self_hosted", "surrogate_mappings", ["context_id", "pii_type", "real_hash"], unique=True, postgresql_where=sa.text("tenant_id IS NULL"))
    op.create_index("uq_surrogate_profile_tenant", "surrogate_profiles", ["tenant_id", "context_id", "real_hash"], unique=True, postgresql_where=sa.text("tenant_id IS NOT NULL"))
    op.create_index("uq_surrogate_profile_self_hosted", "surrogate_profiles", ["context_id", "real_hash"], unique=True, postgresql_where=sa.text("tenant_id IS NULL"))
    op.drop_constraint("uq_mapping_tenant_project_context_token", "pii_mappings", type_="unique")
    op.create_unique_constraint("uq_mapping_tenant_context_token", "pii_mappings", ["tenant_id", "context_id", "context_type", "token"])
    for table in ("surrogate_profiles", "surrogate_mappings", "pii_mappings"):
        op.drop_column(table, "project_id")
