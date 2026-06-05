"""presidio_context table

Revision ID: 007
Revises: 006
Create Date: 2026-06-05
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None

DEFAULT_CONTEXT = [
    # PERSON boost words
    ("PERSON", "coniuge",      "Relazione familiare"),
    ("PERSON", "padre",        "Relazione familiare"),
    ("PERSON", "madre",        "Relazione familiare"),
    ("PERSON", "marito",       "Relazione familiare"),
    ("PERSON", "moglie",       "Relazione familiare"),
    ("PERSON", "figlio",       "Relazione familiare"),
    ("PERSON", "figlia",       "Relazione familiare"),
    ("PERSON", "fratello",     "Relazione familiare"),
    ("PERSON", "sorella",      "Relazione familiare"),
    ("PERSON", "nonno",        "Relazione familiare"),
    ("PERSON", "nonna",        "Relazione familiare"),
    ("PERSON", "paziente",     "Contesto medico-legale"),
    ("PERSON", "cliente",      "Contesto legale"),
    ("PERSON", "committente",  "Contesto legale"),
    ("PERSON", "ricorrente",   "Contesto legale"),
    ("PERSON", "convenuto",    "Contesto legale"),
    ("PERSON", "difensore",    "Contesto legale"),
    ("PERSON", "nome",         "Etichetta documento"),
    ("PERSON", "cognome",      "Etichetta documento"),
    ("PERSON", "intestatario", "Contesto contrattuale"),
    # PHONE boost words
    ("PHONE", "telefono",   "Etichetta contatto"),
    ("PHONE", "cellulare",  "Etichetta contatto"),
    ("PHONE", "tel",        "Etichetta contatto"),
    ("PHONE", "cell",       "Etichetta contatto"),
    ("PHONE", "fax",        "Etichetta contatto"),
    # EMAIL boost words
    ("EMAIL", "email",    "Etichetta contatto"),
    ("EMAIL", "pec",      "Etichetta contatto"),
    ("EMAIL", "e-mail",   "Etichetta contatto"),
]


def upgrade() -> None:
    t = op.create_table(
        "presidio_context",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("word", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_presidio_context_entity_type", "presidio_context", ["entity_type"])
    op.bulk_insert(t, [
        {"entity_type": et, "word": w, "description": d, "enabled": True}
        for et, w, d in DEFAULT_CONTEXT
    ])


def downgrade() -> None:
    op.drop_index("ix_presidio_context_entity_type", "presidio_context")
    op.drop_table("presidio_context")
