"""settings table

Revision ID: 005
Revises: 004
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text("INSERT INTO settings (key, value) VALUES ('default_language', 'it')")
    )


def downgrade() -> None:
    op.drop_table("settings")
