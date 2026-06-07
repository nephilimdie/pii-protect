"""add CITY_BORN regex pattern

Revision ID: 014
Revises: 013
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

# Captures only the city name after "nato/nata a"
# IGNORECASE applied only to nat[ao] prefix via inline flag (?i:...)
CITY_BORN_PATTERN = (
    r"(?i:nat[ao])\s+a\s+"
    r"([A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]+"
    r"(?:\s+[A-ZÀÁÈÉÌÍÒÓÙÚ][a-zàáèéìíòóùú]+){0,3})"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'CITY_BORN', :p, '', 1,"
            " 'Città di nascita (nato/nata a <Città>)', true)"
        ),
        {"p": CITY_BORN_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'CITY_BORN'"))
