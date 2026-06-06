"""add SALARY regex pattern for RAL detection

Revision ID: 010
Revises: 009
Create Date: 2026-06-06
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None

SALARY_PATTERN = r"(?i)\bral\b[\s\w]{0,20}[€£$]?\s*[\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
            " VALUES (gen_random_uuid(), 'SALARY', :p, 'IGNORECASE', 0,"
            " 'RAL / reddito annuo lordo (es. RAL dichiarata € 64.000)', true)"
        ),
        {"p": SALARY_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'SALARY'"))
