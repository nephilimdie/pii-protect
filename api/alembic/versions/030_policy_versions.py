"""policy versions for domain and context policies

Revision ID: 030
Revises: 029
Create Date: 2026-06-16
"""

from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domain_policies", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("context_types", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("context_types", "version")
    op.drop_column("domain_policies", "version")