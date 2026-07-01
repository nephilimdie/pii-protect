"""Add VAT_NUMBER and HEALTH_DATA to pii_type_registry.

Revision ID: 045
Revises: 044
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None

NEW_TYPES = [
    ("VAT_NUMBER", "FINANCIAL", "Partita IVA", "protect", "vat_number", True),
    ("HEALTH_DATA", "IDENTITY", "Dati Sanitari", "protect", None, False),
]


def upgrade() -> None:
    conn = op.get_bind()
    for code, category, display_name, action, strategy, reversible in NEW_TYPES:
        conn.execute(
            sa.text(
                "INSERT INTO pii_type_registry"
                " (code, category, display_name, default_action, faker_strategy, reversible)"
                " VALUES (:code, :category, :display_name, :action, :strategy, :reversible)"
                " ON CONFLICT (code) DO NOTHING"
            ),
            {
                "code": code,
                "category": category,
                "display_name": display_name,
                "action": action,
                "strategy": strategy,
                "reversible": reversible,
            },
        )


def downgrade() -> None:
    op.execute("DELETE FROM pii_type_registry WHERE code IN ('VAT_NUMBER', 'HEALTH_DATA')")
