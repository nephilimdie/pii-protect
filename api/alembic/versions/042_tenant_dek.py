"""Per-tenant DEK table for DEK/KEK encryption isolation

Revision ID: 042
Revises: 041
Create Date: 2026-06-24

Each row stores one Data Encryption Key (DEK) per tenant, encrypted with the
global KEK (ENCRYPTION_KEY env var). MappingRepository uses the tenant-specific
DEK instead of the global key, so compromising one tenant's DEK does not expose
other tenants' data.

Self-hosted deployments (tenant_id=None) are unaffected: the KeyProvider
returns the KEK directly for None tenant_id, bypassing this table.
"""

from alembic import op
import sqlalchemy as sa

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_keys",
        sa.Column("tenant_id", sa.String(100), primary_key=True),
        sa.Column("dek_encrypted", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("tenant_keys")
