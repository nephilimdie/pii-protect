"""add tenant_id to pii_mappings and make unique constraint tenant-scoped

Revision ID: 035
Revises: 034
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pii_mappings", sa.Column("tenant_id", sa.String(100), nullable=True))

    op.drop_constraint("uq_mapping_context_token", "pii_mappings", type_="unique")

    op.create_unique_constraint(
        "uq_mapping_tenant_context_token",
        "pii_mappings",
        ["tenant_id", "context_id", "context_type", "token"],
    )

    op.create_index("ix_pii_mappings_tenant_context", "pii_mappings", ["tenant_id", "context_id", "context_type"])


def downgrade() -> None:
    op.drop_index("ix_pii_mappings_tenant_context", "pii_mappings")

    op.drop_constraint("uq_mapping_tenant_context_token", "pii_mappings", type_="unique")

    op.create_unique_constraint(
        "uq_mapping_context_token",
        "pii_mappings",
        ["context_id", "context_type", "token"],
    )

    op.drop_column("pii_mappings", "tenant_id")
