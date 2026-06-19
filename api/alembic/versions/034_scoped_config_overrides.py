"""scoped config overrides for cloud tenants and users

Revision ID: 034
Revises: 033
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scoped_config_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("collection", sa.String(80), nullable=False),
        sa.Column("item_key", sa.String(200), nullable=False),
        sa.Column("action", sa.String(24), nullable=False, server_default="override"),
        sa.Column("data", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope_type", "scope_key", "collection", "item_key", name="uq_scoped_config_item"),
    )
    op.create_index("ix_scoped_config_scope", "scoped_config_overrides", ["scope_type", "scope_key"])
    op.create_index("ix_scoped_config_collection", "scoped_config_overrides", ["collection", "item_key"])


def downgrade() -> None:
    op.drop_index("ix_scoped_config_collection", table_name="scoped_config_overrides")
    op.drop_index("ix_scoped_config_scope", table_name="scoped_config_overrides")
    op.drop_table("scoped_config_overrides")
