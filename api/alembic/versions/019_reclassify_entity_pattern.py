"""reclassification_rules: add entity_pattern column + example rules

Revision ID: 019
Revises: 018
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

# context_pattern = regex searched in the N chars BEFORE the entity (None = skip)
# entity_pattern  = regex searched in the entity text itself            (None = skip)
# Both present → both must match (AND logic)
EXAMPLE_RULES = [
    {
        "from_type": "PERSON",
        "to_type": "ACCOUNT",
        "context_pattern": None,
        "entity_pattern": r"@",
        "context_window": 60,
        "description": "PERSON contenente '@' → quasi certamente un handle/account social",
    },
    {
        "from_type": "PERSON",
        "to_type": "ACCOUNT",
        "context_pattern": r"(?i)(?:telegram|instagram|twitter|facebook|linkedin|tiktok|social|handle|tag)\s*[:/]?\s*$",
        "entity_pattern": None,
        "context_window": 80,
        "description": "PERSON dopo label social network → ACCOUNT",
    },
    {
        "from_type": "PERSON",
        "to_type": "EMAIL",
        "context_pattern": r"(?i)(?:e[-\s]?mail|posta\s+elettronica|indirizzo\s+mail)\s*:?\s*$",
        "entity_pattern": None,
        "context_window": 60,
        "description": "PERSON dopo 'email:' o 'posta elettronica:' → EMAIL",
    },
    {
        "from_type": "PERSON",
        "to_type": "ORGANIZATION",
        "context_pattern": r"(?i)(?:datore\s+di\s+lavoro|azienda|società|impresa|studio\s+professionale)\s*:?\s*$",
        "entity_pattern": None,
        "context_window": 80,
        "description": "PERSON dopo 'datore di lavoro:' o 'azienda:' → ORGANIZATION",
    },
    {
        "from_type": "PERSON",
        "to_type": "ORGANIZATION",
        "context_pattern": None,
        "entity_pattern": r"(?i)\b(?:s\.?r\.?l\.?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?)\b",
        "context_window": 60,
        "description": "PERSON contenente forma giuridica (S.r.l., S.p.A., ecc.) → ORGANIZATION",
    },
]


def upgrade() -> None:
    # Add entity_pattern column (nullable — None means "don't check entity text")
    op.add_column(
        "reclassification_rules",
        sa.Column("entity_pattern", sa.Text, nullable=True),
    )
    # Allow context_pattern to be NULL (entity-only rules don't need context check)
    op.alter_column("reclassification_rules", "context_pattern", nullable=True)

    conn = op.get_bind()
    for rule in EXAMPLE_RULES:
        conn.execute(
            sa.text(
                "INSERT INTO reclassification_rules"
                " (id, from_type, to_type, context_pattern, entity_pattern, context_window, description, enabled)"
                " VALUES (CAST(:id AS uuid), :from_type, :to_type, :context_pattern, :entity_pattern, :context_window, :description, true)"
            ),
            {"id": str(uuid.uuid4()), **rule},
        )


def downgrade() -> None:
    op.drop_column("reclassification_rules", "entity_pattern")
    op.alter_column("reclassification_rules", "context_pattern", nullable=False)
