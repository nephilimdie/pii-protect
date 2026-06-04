"""regex_patterns table

Revision ID: 002
Revises: 001
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

DEFAULT_PATTERNS = [
    {
        "pii_type": "FISCAL_CODE",
        "pattern": r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b",
        "flags": "",
        "capture_group": 0,
        "description": "Codice fiscale italiano (16 caratteri alfanumerici)",
    },
    {
        "pii_type": "IBAN",
        "pattern": r"\bIT\d{2}[A-Z0-9]{23}\b",
        "flags": "",
        "capture_group": 0,
        "description": "IBAN italiano (27 caratteri)",
    },
    {
        "pii_type": "EMAIL",
        "pattern": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "flags": "",
        "capture_group": 0,
        "description": "Indirizzo email",
    },
    {
        "pii_type": "PHONE",
        "pattern": r"(?:\+39|0039)?\s*(?:0\d[\d\s\-]{6,9}|3\d{2}[\s\-]?\d{6,7})",
        "flags": "",
        "capture_group": 0,
        "description": "Numero di telefono italiano (fisso e mobile)",
    },
    {
        "pii_type": "TARGA",
        "pattern": r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
        "flags": "",
        "capture_group": 0,
        "description": "Targa veicolo italiano",
    },
    {
        "pii_type": "PIVA",
        "pattern": r"(?:p\.?\s?iva|partita\s+iva)[^\d]*(\d{11})",
        "flags": "IGNORECASE",
        "capture_group": 1,
        "description": "Partita IVA italiana (richiede prefisso testuale)",
    },
]


def upgrade() -> None:
    t = op.create_table(
        "regex_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pii_type", sa.String(50), nullable=False),
        sa.Column("pattern", sa.Text, nullable=False),
        sa.Column("flags", sa.String(100), nullable=False, server_default=""),
        sa.Column("capture_group", sa.Integer, nullable=False, server_default="0"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.bulk_insert(t, [
        {
            "id": uuid.uuid4(),
            "pii_type": p["pii_type"],
            "pattern": p["pattern"],
            "flags": p["flags"],
            "capture_group": p["capture_group"],
            "description": p["description"],
            "enabled": True,
        }
        for p in DEFAULT_PATTERNS
    ])


def downgrade() -> None:
    op.drop_table("regex_patterns")
