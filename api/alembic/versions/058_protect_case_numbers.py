"""Protect court case numbers (PRACTICE_ID) in the generic professional preset.

R.G. / N.R.G. numbers identify a proceeding and, through court records, its parties: the
code-level recognizer now emits them as PRACTICE_ID, and the generic preset must protect them.
Only the system row is touched, and only if PRACTICE_ID is not already listed.

Revision ID: 058
Revises: 057
Create Date: 2026-11-01
"""

from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None

_WHERE = "domain = 'generic_professional' AND tenant_id IS NULL"


def upgrade() -> None:
    op.execute(f"UPDATE domain_policies SET protect_types = protect_types || '[\"PRACTICE_ID\"]'::jsonb "
               f"WHERE {_WHERE} AND NOT protect_types ? 'PRACTICE_ID'")


def downgrade() -> None:
    op.execute(f"UPDATE domain_policies SET protect_types = protect_types - 'PRACTICE_ID' WHERE {_WHERE}")
