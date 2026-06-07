"""add DATE regex patterns (numeric and written Italian)

Revision ID: 024
Revises: 023
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

# dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy — 4-digit year avoids false positives on short numbers
DATE_NUMERIC = r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b"

# 14 marzo 1984 / 14 Marzo 1984 (IGNORECASE)
DATE_WRITTEN = (
    r"\b(\d{1,2}\s+"
    r"(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio"
    r"|agosto|settembre|ottobre|novembre|dicembre)"
    r"\s+\d{4})\b"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'DATE', :p, '', 1,"
            " 'Data in formato numerico (dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy)', true)"
        ),
        {"p": DATE_NUMERIC},
    )
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'DATE', :p, 'IGNORECASE', 1,"
            " 'Data scritta in italiano (14 marzo 1984)', true)"
        ),
        {"p": DATE_WRITTEN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'DATE'"))
