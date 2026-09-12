"""Use correct partial uniqueness for tenant and self-hosted mappings.

Revision ID: 052
Revises: 051
"""

from alembic import op
import sqlalchemy as sa


revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_mapping_tenant_project_context_token", "pii_mappings", type_="unique")
    op.create_index(
        "uix_mapping_tenant_project",
        "pii_mappings",
        ["tenant_id", "project_id", "context_id", "context_type", "token"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uix_mapping_self_hosted_project",
        "pii_mappings",
        ["project_id", "context_id", "context_type", "token"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uix_mapping_self_hosted_project", table_name="pii_mappings")
    op.drop_index("uix_mapping_tenant_project", table_name="pii_mappings")
    op.create_unique_constraint(
        "uq_mapping_tenant_project_context_token",
        "pii_mappings",
        ["tenant_id", "project_id", "context_id", "context_type", "token"],
    )
