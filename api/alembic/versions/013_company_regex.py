"""add COMPANY regex pattern for Italian company names

Revision ID: 013
Revises: 012
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None

# Matches: NovaTech S.r.l. / Rossi & Figli S.n.c. / Acme SpA / Mario Bianchi Srl
COMPANY_PATTERN = (
    r"\b([A-Z][A-Za-z0-9&']{0,30}"
    r"(?:\s+(?:&|e|di|del|della|dei|[A-Z][A-Za-z0-9&']{0,25})){0,4}"
    r"\s+(?:S\.r\.l\.s\.|S\.r\.l\.|S\.p\.A\.|S\.n\.c\.|S\.a\.s\.|S\.c\.r\.l\.|SpA|Srl|Snc|Sas|SRL|SPA|SNC|SAS)\.?)"
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'COMPANY', :p, '', 1,"
            " 'Ragione sociale italiana (es. NovaTech S.r.l., Acme SpA)', true)"
        ),
        {"p": COMPANY_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'COMPANY'"))
