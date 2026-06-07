"""fix POLICY_NUMBER regex (split into two context patterns); add CLAIM_ID

Revision ID: 017
Revises: 016
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None

POLICY_PATTERN = (
    r"(?i:contratto\s+assicurativo|polizza)\s+"
    r"(?:[\w]+\s+){0,2}(?:n\.?\s*|numero\s*)?"
    r"([A-Z0-9]{2,}-[\w\-]{2,}|[A-Z]{2,}\d{3,}[\w\-]*|\d{5,})\b"
)

CLAIM_PATTERN = (
    r"(?i:sinistro|pratica|caso)\b.{0,40}?\bcodice\s+"
    r"([A-Z0-9]{2,}-[\w\-]{2,}|[A-Z]{2,}\d{3,}[\w\-]*|\d{5,})\b"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'POLICY_NUMBER'"))
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'POLICY_NUMBER', :p, 'IGNORECASE', 1,"
            " 'Numero polizza assicurativa (richiede contesto: contratto/polizza)', true)"
        ),
        {"p": POLICY_PATTERN},
    )
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'POLICY_NUMBER', :p, 'IGNORECASE|DOTALL', 1,"
            " 'Codice sinistro (richiede contesto: sinistro ... codice)', true)"
        ),
        {"p": CLAIM_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'POLICY_NUMBER'"))
