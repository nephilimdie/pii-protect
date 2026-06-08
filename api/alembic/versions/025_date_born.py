"""add DATE_BORN to pii_type_registry and reclassification rule DATE -> DATE_BORN

Revision ID: 025
Revises: 024
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

# Matches "nato a Roma il", "nata a Milano, il", "nato a San Giovanni il", etc.
# Looks back up to 80 chars before the DATE entity for the "nat[ao] a <City>" pattern.
CONTEXT_PATTERN = r"nat[ao]\s+a\s+[A-ZÀÁÈÉÌÍÒÓÙÚ]"


def upgrade() -> None:
    conn = op.get_bind()

    # Register DATE_BORN as a sub-type of DATE in the registry
    conn.execute(
        sa.text(
            "INSERT INTO pii_type_registry"
            " (code, category, display_name, default_action, faker_strategy, reversible, enabled)"
            " VALUES ('DATE_BORN', 'IDENTITY', 'Data di Nascita', 'protect', 'date_shift', true, true)"
            " ON CONFLICT (code) DO NOTHING"
        )
    )

    # Reclassification rule: DATE -> DATE_BORN when preceded by "nato/nata a <City>"
    conn.execute(
        sa.text(
            "INSERT INTO reclassification_rules"
            " (id, from_type, to_type, context_pattern, entity_pattern, context_window, description, enabled)"
            " VALUES (gen_random_uuid(), 'DATE', 'DATE_BORN', :ctx, NULL, 80,"
            " 'Data preceduta da \"nato/nata a <Città>\" → DATE_BORN', true)"
        ),
        {"ctx": CONTEXT_PATTERN},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM reclassification_rules WHERE from_type = 'DATE' AND to_type = 'DATE_BORN'"
    ))
    conn.execute(sa.text("DELETE FROM pii_type_registry WHERE code = 'DATE_BORN'"))
