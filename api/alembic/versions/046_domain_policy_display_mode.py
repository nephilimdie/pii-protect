"""Add display_name and default_mode to domain_policies.

Lets a domain policy be called directly (by slug) as a self-contained unit:
- display_name: human-readable label shown in the UI
- default_mode: tag | surrogate applied to the protect bucket when the
  policy is invoked without a context_type

Revision ID: 046
Revises: 045
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa


revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domain_policies", sa.Column("display_name", sa.Text(), nullable=True))
    op.add_column(
        "domain_policies",
        sa.Column("default_mode", sa.Text(), nullable=False, server_default="tag"),
    )
    # Backfill display_name from the existing domain slug so no row is left blank.
    op.execute("UPDATE domain_policies SET display_name = domain WHERE display_name IS NULL")


def downgrade() -> None:
    op.drop_column("domain_policies", "default_mode")
    op.drop_column("domain_policies", "display_name")
