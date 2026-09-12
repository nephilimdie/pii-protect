"""Allow settings to be overridden per tenant.

Revision ID: 050
Revises: 049
"""

from alembic import op
import sqlalchemy as sa


revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("id", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE settings SET id = gen_random_uuid() WHERE id IS NULL"))
    op.alter_column("settings", "id", nullable=False, server_default=sa.text("gen_random_uuid()"))
    op.add_column("settings", sa.Column("tenant_id", sa.String(100), nullable=True))
    op.drop_constraint("settings_pkey", "settings", type_="primary")
    op.create_primary_key("settings_pkey", "settings", ["id"])
    op.create_index("uq_settings_global_key", "settings", ["key"], unique=True, postgresql_where=sa.text("tenant_id IS NULL"))
    op.create_index("uq_settings_tenant_key", "settings", ["tenant_id", "key"], unique=True, postgresql_where=sa.text("tenant_id IS NOT NULL"))
    op.create_index("ix_settings_tenant_id", "settings", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_settings_tenant_id", table_name="settings")
    op.drop_index("uq_settings_tenant_key", table_name="settings")
    op.drop_index("uq_settings_global_key", table_name="settings")
    op.drop_constraint("settings_pkey", "settings", type_="primary")
    op.create_primary_key("settings_pkey", "settings", ["key"])
    op.drop_column("settings", "tenant_id")
    op.drop_column("settings", "id")
