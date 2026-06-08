"""fix DATE_BORN context_pattern: require 'il' immediately before the date entity

Revision ID: 026
Revises: 025
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None

# The context window ends right before the date entity.
# Pattern: "nato/nata a <Città> il" at the end of the window.
# \s*$ ensures "il" is the last word before the date (possibly followed by a space).
OLD_PATTERN = r"nat[ao]\s+a\s+[A-ZÀÁÈÉÌÍÒÓÙÚ]"
NEW_PATTERN = (
    r"nat[ao]\s+a\s+"
    r"[A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]+"
    r"(?:\s+[A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]+)*"
    r"\s+il\s*$"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE reclassification_rules SET context_pattern = :new"
            " WHERE from_type = 'DATE' AND to_type = 'DATE_BORN'"
        ),
        {"new": NEW_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE reclassification_rules SET context_pattern = :old"
            " WHERE from_type = 'DATE' AND to_type = 'DATE_BORN'"
        ),
        {"old": OLD_PATTERN},
    )
