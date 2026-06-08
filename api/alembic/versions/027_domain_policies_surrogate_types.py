"""add surrogate_types to domain_policies

Revision ID: 027
Revises: 026
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE domain_policies ADD COLUMN IF NOT EXISTS surrogate_types JSONB NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE domain_policies DROP COLUMN IF EXISTS surrogate_types")
