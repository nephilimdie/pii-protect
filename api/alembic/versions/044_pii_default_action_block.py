"""Set default_action=block for CREDIT_CARD and SECRET.

Revision ID: 044
Revises: 043
Create Date: 2026-06-30
"""

from alembic import op

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE pii_type_registry"
        " SET default_action = 'block'"
        " WHERE code IN ('CREDIT_CARD', 'SECRET')"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE pii_type_registry"
        " SET default_action = 'protect'"
        " WHERE code IN ('CREDIT_CARD', 'SECRET')"
    )
