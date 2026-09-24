"""Add label-scoped European tax and national identifier patterns."""

import sqlalchemy as sa
from alembic import op

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None

NEW_TYPES = [
    ("DE_TAX_ID", "IDENTITY", "German tax ID", "protect", "alphanumeric", True),
    ("FR_SIRET", "IDENTITY", "French SIRET", "protect", "alphanumeric", True),
    ("FR_SIREN", "IDENTITY", "French SIREN", "protect", "alphanumeric", True),
    ("ES_DNI_NIE", "IDENTITY", "Spanish DNI / NIE", "protect", "alphanumeric", True),
    ("UK_NI_NUMBER", "IDENTITY", "UK National Insurance number", "protect", "alphanumeric", True),
    ("NL_BSN", "IDENTITY", "Dutch BSN", "protect", "alphanumeric", True),
]

PATTERNS = [
    ("DE_TAX_ID", r"(?i)\b(?:steuer[- ]?id|steueridentifikationsnummer)\s*[:#]?\s*(\d{11})\b", "German tax ID after an explicit label"),
    ("FR_SIRET", r"(?i)\bsiret\s*[:#]?\s*(\d{14})\b", "French SIRET after an explicit label"),
    ("FR_SIREN", r"(?i)\bsiren\s*[:#]?\s*(\d{9})\b", "French SIREN after an explicit label"),
    ("ES_DNI_NIE", r"(?i)\b(?:dni|nie)\s*[:#]?\s*([xyz]?\d{7,8}[a-z])\b", "Spanish DNI or NIE after an explicit label"),
    ("UK_NI_NUMBER", r"(?i)\b(?:national\s+insurance|ni\s+number)\s*[:#]?\s*([a-ceghj-pr-tw-z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[a-d])\b", "UK National Insurance number after an explicit label"),
    ("NL_BSN", r"(?i)\b(?:bsn|burgerservicenummer)\s*[:#]?\s*(\d{9})\b", "Dutch BSN after an explicit label"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for code, category, display_name, action, strategy, reversible in NEW_TYPES:
        conn.execute(
            sa.text(
                "INSERT INTO pii_type_registry "
                "(code, category, display_name, default_action, faker_strategy, reversible) "
                "VALUES (:code, :category, :display_name, :action, :strategy, :reversible) "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "category": category, "display_name": display_name,
             "action": action, "strategy": strategy, "reversible": reversible},
        )
    for pii_type, pattern, description in PATTERNS:
        conn.execute(
            sa.text(
                "INSERT INTO regex_patterns (pii_type, pattern, flags, capture_group, description, enabled) "
                "SELECT :pii_type, :pattern, '', 1, :description, true "
                "WHERE NOT EXISTS (SELECT 1 FROM regex_patterns WHERE pii_type = :pii_type AND pattern = :pattern)"
            ),
            {"pii_type": pii_type, "pattern": pattern, "description": description},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for pii_type, pattern, _ in PATTERNS:
        conn.execute(
            sa.text("DELETE FROM regex_patterns WHERE pii_type = :pii_type AND pattern = :pattern"),
            {"pii_type": pii_type, "pattern": pattern},
        )
    conn.execute(
        sa.text("DELETE FROM pii_type_registry WHERE code = ANY(:codes)"),
        {"codes": [item[0] for item in NEW_TYPES]},
    )
