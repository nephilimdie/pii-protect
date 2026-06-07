"""add GPS_COORDINATE, IMEI, PNR, SOCIAL_HANDLE, API_KEY regex; fix PRACTICE_ID

Revision ID: 015
Revises: 014
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

NEW_PATTERNS = [
    (
        "GPS_COORDINATE",
        r"-?\d{1,3}\.\d{4,},\s*-?\d{1,3}\.\d{4,}",
        "",
        0,
        "Coordinate GPS (lat, lon) — batte il tag ADDRESS dei layer ML",
    ),
    (
        "IMEI",
        r"(?i)\bIMEI\s*:?\s*(\d{15,17})\b",
        "IGNORECASE",
        1,
        "Codice IMEI dispositivo (15-17 cifre, richiede prefisso IMEI)",
    ),
    (
        "PNR",
        r"\bPNR\s+([A-Z0-9]{5,8})\b",
        "",
        1,
        "Codice prenotazione volo PNR (5-8 caratteri alfanumerici maiuscoli)",
    ),
    (
        "SOCIAL_HANDLE",
        r"@([A-Za-z0-9_]{3,50})\b",
        "",
        1,
        "Social handle / username con @ (es. @marcobianchi84)",
    ),
    (
        "API_KEY",
        r"\b(?:sk|pk|rk|ghp|gho|ghu|ghs|ghr)-[A-Za-z0-9_\-]{20,}\b",
        "",
        0,
        "API key / token (Stripe sk-, GitHub ghp-, ecc.)",
    ),
]

PRACTICE_ID_PATTERN = (
    r"(?i)(?:pratica\s+(?:sanitaria|medica)|numero\s+pratica)"
    r"[\s\w.,#°]{0,20}?([A-Z]{2,5}-[\w\-]{4,}|\d{5,})"
)


def upgrade() -> None:
    conn = op.get_bind()

    # Fix PRACTICE_ID: replace old broad pattern with context-scoped one
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'PRACTICE_ID'"))
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'PRACTICE_ID', :p, 'IGNORECASE', 1,"
            " 'Numero pratica sanitaria/medica (es. SSR-2025-009871)', true)"
        ),
        {"p": PRACTICE_ID_PATTERN},
    )

    for pii_type, pattern, flags, capture_group, description in NEW_PATTERNS:
        conn.execute(
            sa.text(
                "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
                " VALUES (gen_random_uuid(), :pii_type, :pattern, :flags, :cg, :desc, true)"
            ),
            {
                "pii_type": pii_type,
                "pattern": pattern,
                "flags": flags,
                "cg": capture_group,
                "desc": description,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    types = [t for t, *_ in NEW_PATTERNS] + ["PRACTICE_ID"]
    conn.execute(
        sa.text("DELETE FROM regex_patterns WHERE pii_type = ANY(:types)"),
        {"types": types},
    )
