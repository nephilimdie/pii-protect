"""add USERNAME regex pattern

Revision ID: 008
Revises: 007
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

USERNAME_PATTERN = r"(?:username|login)\s*:\s*(\S{3,})"


def upgrade() -> None:
    conn = op.get_bind()
    # Remove any existing USERNAME patterns (cleanup from API-added versions)
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'USERNAME'"))
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'USERNAME', :pattern, 'IGNORECASE', 1, "
            "'Username (requires explicit username: or login: label)', true)"
        ),
        {"pattern": USERNAME_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'USERNAME'"))
