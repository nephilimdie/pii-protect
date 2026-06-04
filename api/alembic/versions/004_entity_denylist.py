"""entity_denylist table with default entries

Revision ID: 004
Revises: 003
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

DEFAULT_ENTRIES = [
    # Kinship / family roles
    ("PERSON", "coniuge",   "Ruolo familiare"),
    ("PERSON", "padre",     "Ruolo familiare"),
    ("PERSON", "madre",     "Ruolo familiare"),
    ("PERSON", "fratello",  "Ruolo familiare"),
    ("PERSON", "sorella",   "Ruolo familiare"),
    ("PERSON", "figlio",    "Ruolo familiare"),
    ("PERSON", "figlia",    "Ruolo familiare"),
    ("PERSON", "nonno",     "Ruolo familiare"),
    ("PERSON", "nonna",     "Ruolo familiare"),
    ("PERSON", "nipote",    "Ruolo familiare"),
    ("PERSON", "zio",       "Ruolo familiare"),
    ("PERSON", "zia",       "Ruolo familiare"),
    ("PERSON", "marito",    "Ruolo familiare"),
    ("PERSON", "moglie",    "Ruolo familiare"),
    # Contact / document labels
    ("PERSON", "telefono",  "Etichetta documento"),
    ("PERSON", "cellulare", "Etichetta documento"),
    ("PERSON", "fax",       "Etichetta documento"),
    ("PERSON", "email",     "Etichetta documento"),
    ("PERSON", "pec",       "Etichetta documento"),
    ("PERSON", "indirizzo", "Etichetta documento"),
    ("PERSON", "nome",      "Etichetta documento"),
    ("PERSON", "cognome",   "Etichetta documento"),
    # Generic labels that confuse NER
    ("PERSON", "data",       "Termine generico"),
    ("PERSON", "luogo",      "Termine generico"),
    ("PERSON", "comune",     "Termine generico"),
    ("PERSON", "stato",      "Termine generico"),
    ("PERSON", "paese",      "Termine generico"),
    ("PERSON", "via",        "Termine generico"),
    ("PERSON", "piazza",     "Termine generico"),
    ("PERSON", "corso",      "Termine generico"),
    ("PERSON", "viale",      "Termine generico"),
    ("PERSON", "numero",     "Termine generico"),
    ("PERSON", "codice",     "Termine generico"),
    ("PERSON", "tipo",       "Termine generico"),
    ("PERSON", "categoria",  "Termine generico"),
    ("PERSON", "nota",       "Termine generico"),
    ("PERSON", "note",       "Termine generico"),
    ("PERSON", "sede",       "Termine generico"),
    ("PERSON", "ufficio",    "Termine generico"),
    ("PERSON", "azienda",    "Termine generico"),
    ("PERSON", "studio",     "Termine generico"),
    ("PERSON", "signore",    "Termine generico"),
    ("PERSON", "signora",    "Termine generico"),
    ("PERSON", "sig",        "Termine generico"),
    ("PERSON", "gentile",    "Termine generico"),
    ("PERSON", "spett",      "Termine generico"),
    ("PERSON", "latitudine", "Termine geografico"),
    ("PERSON", "longitudine","Termine geografico"),
    ("PERSON", "coordinate", "Termine geografico"),
]


def upgrade() -> None:
    t = op.create_table(
        "entity_denylist",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pii_type", sa.String(50), nullable=False),
        sa.Column("value", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_entity_denylist_pii_type", "entity_denylist", ["pii_type"])

    conn = op.get_bind()
    for pii_type, value, description in DEFAULT_ENTRIES:
        conn.execute(
            sa.text(
                "INSERT INTO entity_denylist (id, pii_type, value, description, enabled)"
                " VALUES (CAST(:id AS uuid), :pii_type, :value, :description, true)"
            ),
            {"id": str(uuid.uuid4()), "pii_type": pii_type, "value": value, "description": description},
        )


def downgrade() -> None:
    op.drop_index("ix_entity_denylist_pii_type", "entity_denylist")
    op.drop_table("entity_denylist")
