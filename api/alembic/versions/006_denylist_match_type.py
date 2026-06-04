"""add match_type to entity_denylist

Revision ID: 006
Revises: 005
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entity_denylist",
        sa.Column("match_type", sa.String(20), nullable=False, server_default="exact_word"),
    )


def downgrade() -> None:
    op.drop_column("entity_denylist", "match_type")
