"""add event_category to audit_logs

Revision ID: 038
Revises: 037
Create Date: 2026-06-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("event_category", sa.String(32), nullable=True, server_default="engine"),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "event_category")
