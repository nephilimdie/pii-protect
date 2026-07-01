"""Add remove_types and block_types to domain_policies.

Revision ID: 043
Revises: 042
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # JSONB columns — default to empty array so existing rows are valid immediately
    op.execute(
        "ALTER TABLE domain_policies"
        " ADD COLUMN IF NOT EXISTS remove_types JSONB NOT NULL DEFAULT '[]'::jsonb,"
        " ADD COLUMN IF NOT EXISTS block_types  JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.drop_column("domain_policies", "remove_types")
    op.drop_column("domain_policies", "block_types")
