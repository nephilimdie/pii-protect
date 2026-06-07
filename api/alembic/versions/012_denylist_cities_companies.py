"""denylist: Italian cities and company suffixes falsely tagged as PERSON

Revision ID: 012
Revises: 011
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

# match_type=contains → entity.text.lower() contains this substring
CONTAINS_ENTRIES = [
    # Company legal forms (multi-word entity, need substring match)
    ("PERSON", "s.r.l",      "Suffisso societario — non è una persona"),
    ("PERSON", "s.p.a",      "Suffisso societario — non è una persona"),
    ("PERSON", "s.n.c",      "Suffisso societario — non è una persona"),
    ("PERSON", "s.a.s",      "Suffisso societario — non è una persona"),
    ("PERSON", "s.c.r.l",    "Suffisso societario — non è una persona"),
    ("PERSON", " spa",       "Suffisso societario — non è una persona"),
    ("PERSON", " srl",       "Suffisso societario — non è una persona"),
    ("PERSON", " snc",       "Suffisso societario — non è una persona"),
    # Administrative context
    ("PERSON", "comune di",    "Ente amministrativo — non è una persona"),
    ("PERSON", "provincia di", "Ente amministrativo — non è una persona"),
    ("PERSON", "regione ",     "Ente amministrativo — non è una persona"),
]

# match_type=exact_word → entity is exactly this single word
CITY_ENTRIES = [
    "roma", "milano", "napoli", "torino", "palermo", "genova", "bologna",
    "firenze", "bari", "catania", "venezia", "verona", "messina", "padova",
    "trieste", "brescia", "taranto", "prato", "modena", "cagliari", "foggia",
    "reggio", "perugia", "livorno", "ravenna", "rimini", "salerno", "ferrara",
    "sassari", "latina", "monza", "bergamo", "trento", "vicenza", "terni",
    "novara", "bolzano", "piacenza", "ancona", "arezzo", "udine", "cesena",
    "lecce", "pescara", "alessandria", "como", "brindisi", "siracusa",
    "agrigento", "pesaro", "mestre", "siena",
]


def upgrade() -> None:
    conn = op.get_bind()

    for pii_type, value, description in CONTAINS_ENTRIES:
        conn.execute(
            sa.text(
                "INSERT INTO entity_denylist (id, pii_type, value, match_type, description, enabled)"
                " VALUES (CAST(:id AS uuid), :pii_type, :value, 'contains', :description, true)"
                " ON CONFLICT DO NOTHING"
            ),
            {"id": str(uuid.uuid4()), "pii_type": pii_type, "value": value, "description": description},
        )

    for city in CITY_ENTRIES:
        conn.execute(
            sa.text(
                "INSERT INTO entity_denylist (id, pii_type, value, match_type, description, enabled)"
                " VALUES (CAST(:id AS uuid), 'PERSON', :value, 'exact_word',"
                " 'Città italiana — spaCy la classifica erroneamente come PERSON', true)"
                " ON CONFLICT DO NOTHING"
            ),
            {"id": str(uuid.uuid4()), "value": city},
        )


def downgrade() -> None:
    conn = op.get_bind()
    values = [v for _, v, _ in CONTAINS_ENTRIES] + CITY_ENTRIES
    conn.execute(
        sa.text("DELETE FROM entity_denylist WHERE value = ANY(:vals) AND pii_type = 'PERSON'"),
        {"vals": values},
    )
