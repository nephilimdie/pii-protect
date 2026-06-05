"""fix regex patterns: PHONE, IDENTITY_CARD, PASSPORT, BIC, TICKET_ID

Revision ID: 009
Revises: 008
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # PHONE: limit landline subscriber to 6 digits (prevent matching 11-digit PIVA)
    conn.execute(sa.text(
        "UPDATE regex_patterns SET pattern = :p WHERE pii_type = 'PHONE'"
    ), {"p": r"(?<!\d)(?:\+39\s*|0039\s*)?(?:0\d[\s./\-]?\d{7,8}|0\d{2,3}[\s./\-]?\d{6}|3\d{2}[\s.\-]?\d{6,7})(?!\d)"})

    # IDENTITY_CARD: exactly 2+5+2 chars (excludes passport format 2+7)
    conn.execute(sa.text(
        "UPDATE regex_patterns SET pattern = :p, description = :d WHERE pii_type = 'IDENTITY_CARD'"
    ), {"p": r"\b[A-Z]{2}\d{5}[A-Z]{2}\b", "d": "Italian identity card (2 letters + 5 digits + 2 letters)"})

    # TICKET_ID: allow dashes in number part (TCK-2026-445566)
    conn.execute(sa.text(
        "UPDATE regex_patterns SET pattern = :p WHERE pii_type = 'TICKET_ID'"
    ), {"p": r"\bTCK-[\d\-]{4,20}\b"})

    # PASSPORT
    conn.execute(sa.text(
        "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
        " VALUES (gen_random_uuid(), 'PASSPORT', :p, '', 0, 'Italian passport (2 letters + 7 digits)', true)"
    ), {"p": r"\b[A-Z]{2}\d{7}\b"})

    # BIC/SWIFT
    conn.execute(sa.text(
        "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
        " VALUES (gen_random_uuid(), 'BIC', :p, '', 0, 'BIC/SWIFT code (8 or 11 chars)', true)"
    ), {"p": r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"})

    # Denylist: User-Agent OS tokens falsely tagged as PERSON
    for word in ["macintosh", "windows", "intel", "android"]:
        conn.execute(sa.text(
            "INSERT INTO entity_denylist (id, pii_type, value, match_type, description, enabled)"
            " VALUES (CAST(:id AS uuid), 'PERSON', :w, 'exact_word', 'User-Agent token — not a person name', true)"
        ), {"id": str(uuid.uuid4()), "w": word})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type IN ('PASSPORT', 'BIC')"))
    conn.execute(sa.text("DELETE FROM entity_denylist WHERE value IN ('macintosh','windows','intel','android')"))
