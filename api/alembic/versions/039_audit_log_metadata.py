"""add metadata fields to audit logs

Revision ID: 039
Revises: 038
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("document_hash", sa.String(64), nullable=True))
    op.add_column("audit_logs", sa.Column("ip", sa.String(64), nullable=True))
    op.add_column("audit_logs", sa.Column("reason", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_logs", "reason")
    op.drop_column("audit_logs", "ip")
    op.drop_column("audit_logs", "document_hash")
