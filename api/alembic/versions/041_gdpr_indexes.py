"""GDPR query indexes on audit_logs

Revision ID: 041
Revises: 040
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_audit_logs_context_id", "audit_logs", ["context_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_context_id", table_name="audit_logs")
