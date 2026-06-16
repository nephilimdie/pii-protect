"""add max_requests_per_hour to api_keys

Revision ID: 032
Revises: 031
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("max_requests_per_hour", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "max_requests_per_hour")
