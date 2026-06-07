"""fix SALARY capture group and pattern

Revision ID: 011
Revises: 010
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

SALARY_PATTERN = r"(?i)\bral\b[^\d]{0,25}(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE regex_patterns"
            " SET pattern = :p, capture_group = 1,"
            " description = 'RAL / reddito annuo lordo — cattura solo importo numerico'"
            " WHERE pii_type = 'SALARY'"
        ),
        {"p": SALARY_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM regex_patterns WHERE pii_type = 'SALARY'"))
