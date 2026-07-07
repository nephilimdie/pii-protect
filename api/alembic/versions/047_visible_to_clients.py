"""Add visible_to_clients to domain_policies and context_types.

Lets an admin restrict which client apps (browser_extension, mcp_server, …) may
see/use a given policy or context type. NULL or empty array = visible to all
clients (backward compatible).

Revision ID: 047
Revises: 046
Create Date: 2026-07-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("domain_policies", "context_types"):
        op.add_column(
            table,
            sa.Column("visible_to_clients", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    for table in ("domain_policies", "context_types"):
        op.drop_column(table, "visible_to_clients")
