"""Add per-type confidence thresholds and value allow-lists to policies."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domain_policies", sa.Column(
        "confidence_thresholds", JSONB, nullable=False, server_default="{}"
    ))
    op.add_column("domain_policies", sa.Column(
        "allowlist", JSONB, nullable=False, server_default="{}"
    ))


def downgrade() -> None:
    op.drop_column("domain_policies", "allowlist")
    op.drop_column("domain_policies", "confidence_thresholds")
