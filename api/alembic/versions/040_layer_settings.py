"""layer_settings table for per-tenant ML layer configuration

Revision ID: 040
Revises: 039
Create Date: 2026-06-21
"""

from __future__ import annotations

import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "layer_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", sa.String(100), nullable=True),
        sa.Column("layer", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_layer_settings_tenant_layer",
        "layer_settings",
        ["tenant_id", "layer"],
    )
    op.create_index("ix_layer_settings_tenant_id", "layer_settings", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_layer_settings_tenant_id", table_name="layer_settings")
    op.drop_constraint("uq_layer_settings_tenant_layer", "layer_settings")
    op.drop_table("layer_settings")
