"""Add per-type confidence thresholds and value allow-lists to policies."""

from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE domain_policies ADD COLUMN IF NOT EXISTS "
        "confidence_thresholds JSONB NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE domain_policies ADD COLUMN IF NOT EXISTS "
        "allowlist JSONB NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE domain_policies DROP COLUMN IF EXISTS allowlist")
    op.execute("ALTER TABLE domain_policies DROP COLUMN IF EXISTS confidence_thresholds")
