"""reclassification_rules table

Revision ID: 018
Revises: 017
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None

DEFAULT_RULES = [
    {
        "from_type": "PERSON",
        "to_type": "ACCOUNT",
        "context_pattern": r"(?i)(?:username|login)\s*:\s*$",
        "context_window": 60,
        "description": "PERSON dopo 'username:' o 'login:' → ACCOUNT",
    },
    {
        "from_type": "PERSON",
        "to_type": "ORGANIZATION",
        "context_pattern": r"(?i)(?:scuola|istituto|liceo|plesso|istituzione|college|università|accademia)\s+(?:\w+\s+){0,3}$",
        "context_window": 80,
        "description": "PERSON dopo nome istituzione scolastica → ORGANIZATION",
    },
]


def upgrade() -> None:
    op.create_table(
        "reclassification_rules",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_type", sa.String(50), nullable=False),
        sa.Column("to_type", sa.String(50), nullable=True),  # NULL = discard entity
        sa.Column("context_pattern", sa.Text, nullable=False),
        sa.Column("context_window", sa.Integer, nullable=False, server_default="60"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reclassification_from_type", "reclassification_rules", ["from_type"])

    conn = op.get_bind()
    for rule in DEFAULT_RULES:
        conn.execute(
            sa.text(
                "INSERT INTO reclassification_rules"
                " (id, from_type, to_type, context_pattern, context_window, description, enabled)"
                " VALUES (CAST(:id AS uuid), :from_type, :to_type, :context_pattern, :context_window, :description, true)"
            ),
            {"id": str(uuid.uuid4()), **rule},
        )


def downgrade() -> None:
    op.drop_index("ix_reclassification_from_type", "reclassification_rules")
    op.drop_table("reclassification_rules")
