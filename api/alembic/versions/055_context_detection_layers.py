"""Allow context types to select a subset of detection layers."""

from alembic import op
import sqlalchemy as sa

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "context_types",
        sa.Column("detection_layers", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("context_types", "detection_layers")
