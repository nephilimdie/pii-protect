"""Add explicit expiry timestamps to reversible mapping stores.

Revision ID: 049
Revises: 048
"""

from alembic import op
import sqlalchemy as sa


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("pii_mappings", "surrogate_mappings", "surrogate_profiles"):
        op.add_column(table, sa.Column("expires_at", sa.DateTime(), nullable=True))
        op.create_index(f"ix_{table}_expires_at", table, ["expires_at"])


def downgrade() -> None:
    for table in ("pii_mappings", "surrogate_mappings", "surrogate_profiles"):
        op.drop_index(f"ix_{table}_expires_at", table_name=table)
        op.drop_column(table, "expires_at")
