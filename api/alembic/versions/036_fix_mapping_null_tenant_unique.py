"""replace composite unique on pii_mappings with two partial unique indexes

The original UNIQUE(tenant_id, context_id, context_type, token) does NOT
enforce uniqueness when tenant_id IS NULL because NULL != NULL in SQL.
Replace it with two partial indexes so both tenant-mode and platform-mode
rows are correctly deduplicated.

Revision ID: 036
Revises: 035
Create Date: 2026-06-18
"""

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_mapping_tenant_context_token", "pii_mappings", type_="unique")

    op.execute(
        "CREATE UNIQUE INDEX uix_mapping_tenant_not_null"
        " ON pii_mappings (tenant_id, context_id, context_type, token)"
        " WHERE tenant_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uix_mapping_tenant_null"
        " ON pii_mappings (context_id, context_type, token)"
        " WHERE tenant_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uix_mapping_tenant_not_null")
    op.execute("DROP INDEX IF EXISTS uix_mapping_tenant_null")

    op.create_unique_constraint(
        "uq_mapping_tenant_context_token",
        "pii_mappings",
        ["tenant_id", "context_id", "context_type", "token"],
    )
