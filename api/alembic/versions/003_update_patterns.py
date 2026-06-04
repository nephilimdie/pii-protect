"""update phone regex + add MAC, UUID, CVV, PIN patterns

Revision ID: 003
Revises: 002
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

NEW_PHONE_PATTERN = r"(?<!\d)(?:\+39\s*|0039\s*)?(?:0\d[\s./\-]?\d{7,8}|0\d{2,3}[\s./\-]?\d{6,7}|3\d{2}[\s.\-]?\d{6,7})(?!\d)"

NEW_PATTERNS = [
    {
        "pii_type": "MAC_ADDRESS",
        "pattern": r"\b(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b",
        "flags": "",
        "capture_group": 0,
        "description": "Indirizzo MAC (formato IEEE 802)",
    },
    {
        "pii_type": "UUID",
        "pattern": r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "flags": "",
        "capture_group": 0,
        "description": "UUID / GUID standard",
    },
    {
        "pii_type": "CVV",
        "pattern": r"(?:cvv|cvc|codice\s+di\s+verifica)[^\d]{0,10}(\d{3,4})",
        "flags": "IGNORECASE",
        "capture_group": 1,
        "description": "CVV/CVC carta di credito (richiede prefisso testuale)",
    },
    {
        "pii_type": "PIN",
        "pattern": r"(?:pin|codice\s+pin|codice\s+segreto)[^\d]{0,10}(\d{4,6})",
        "flags": "IGNORECASE",
        "capture_group": 1,
        "description": "PIN / codice segreto (richiede prefisso testuale)",
    },
]

regex_patterns = sa.table(
    "regex_patterns",
    sa.column("id", PG_UUID(as_uuid=True)),
    sa.column("pii_type", sa.String),
    sa.column("pattern", sa.Text),
    sa.column("flags", sa.String),
    sa.column("capture_group", sa.Integer),
    sa.column("description", sa.Text),
    sa.column("enabled", sa.Boolean),
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE regex_patterns SET pattern = :pattern WHERE pii_type = 'PHONE'"),
        {"pattern": NEW_PHONE_PATTERN},
    )
    for p in NEW_PATTERNS:
        conn.execute(
            sa.text(
                "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled)"
                " VALUES (CAST(:id AS uuid), :pii_type, :pattern, :flags, :capture_group, :description, :enabled)"
            ),
            {
                "id": str(uuid.uuid4()),
                "pii_type": p["pii_type"],
                "pattern": p["pattern"],
                "flags": p["flags"],
                "capture_group": p["capture_group"],
                "description": p["description"],
                "enabled": True,
            },
        )


def downgrade() -> None:
    old_phone = r"(?:\+39|0039)?\s*(?:0\d[\d\s\-]{6,9}|3\d{2}[\s\-]?\d{6,7})"
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE regex_patterns SET pattern = :pattern WHERE pii_type = 'PHONE'"),
        {"pattern": old_phone},
    )
    for p in NEW_PATTERNS:
        conn.execute(
            sa.text("DELETE FROM regex_patterns WHERE pii_type = :pii_type"),
            {"pii_type": p["pii_type"]},
        )
