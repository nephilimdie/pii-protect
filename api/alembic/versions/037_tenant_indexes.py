"""add tenant lookup indexes

Revision ID: 037
Revises: 036
Create Date: 2026-06-18
"""
from __future__ import annotations

from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ix_pii_mappings_tenant_context already created in 035 with (tenant_id, context_id, context_type)
    op.create_index("ix_pii_mappings_tenant_token", "pii_mappings", ["tenant_id", "token"])
    op.create_index("ix_audit_logs_tenant_created", "audit_logs", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_tenant_created", table_name="audit_logs")
    op.drop_index("ix_pii_mappings_tenant_token", table_name="pii_mappings")
