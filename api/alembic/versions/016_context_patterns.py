"""context-anchored patterns: IDENTITY_CARD, POLICY_NUMBER, LOYALTY_ID; rename SOCIAL_HANDLE to ACCOUNT

Revision ID: 016
Revises: 015
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

NEW_PATTERNS = [
    (
        "IDENTITY_CARD",
        # Triggered only when preceded by "carta d'identità / CI / C.I." context
        r"(?i:carta\s+d.identit[àa]|C\.?I\.?)\s*[:\s]\s*([A-Z]{2}\d{7})\b",
        "IGNORECASE",
        1,
        "Carta d'identità elettronica (formato 2 lettere + 7 cifre, richiede contesto)",
    ),
    (
        "POLICY_NUMBER",
        # Triggered by "contratto assicurativo / polizza / sinistro" context
        r"(?i:contratto\s+assicurativo|polizza|sinistro)\s+(?:[\w]+\s+){0,2}(?:n\.?\s*|numero\s*)?([A-Z][A-Z0-9][\w\-]{4,})\b",
        "IGNORECASE",
        1,
        "Numero polizza / contratto assicurativo / sinistro (richiede contesto)",
    ),
    (
        "LOYALTY_ID",
        # Triggered by "frequent flyer / loyalty / mileage / carta fedeltà" context
        r"(?i:frequent\s+flyer|loyalty|mileage|carta\s+fedelt[àa])\b[\s\w]{0,20}?([A-Z]{2}\d{6,12}|[A-Z0-9]{7,15})\b",
        "IGNORECASE",
        1,
        "Numero fedeltà / frequent flyer (richiede contesto)",
    ),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Rename SOCIAL_HANDLE → ACCOUNT
    conn.execute(sa.text("UPDATE regex_patterns SET pii_type = 'ACCOUNT' WHERE pii_type = 'SOCIAL_HANDLE'"))

    for pii_type, pattern, flags, cg, description in NEW_PATTERNS:
        conn.execute(
            sa.text(
                "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
                " VALUES (gen_random_uuid(), :pii_type, :pattern, :flags, :cg, :desc, true)"
            ),
            {"pii_type": pii_type, "pattern": pattern, "flags": flags, "cg": cg, "desc": description},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE regex_patterns SET pii_type = 'SOCIAL_HANDLE' WHERE pii_type = 'ACCOUNT'"))
    for pii_type, *_ in NEW_PATTERNS:
        conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = :t"), {"t": pii_type})
