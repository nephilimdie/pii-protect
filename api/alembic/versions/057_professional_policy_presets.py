"""Professional policy presets for Italian HR, tax, real-estate/insurance and generic use.

Adds the PII types and checksum-gated regex patterns those presets need, a
DATE -> DATE_BORN rule for "data di nascita"/"nato il", and four domain
policies (plus same-named context types, like 022 does for fine_appeal):
hr_payroll, tax_accounting, real_estate_insurance, generic_professional.

The legacy `PIVA` pattern is consolidated into `VAT_NUMBER` (the registry code
since 045) with a Luhn check, so policies listing VAT_NUMBER actually match it.

Revision ID: 057
Revises: 056
Create Date: 2026-10-24
"""

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None

# (code, category, display_name, default_action, faker_strategy, reversible)
NEW_TYPES = [
    ("EMPLOYEE_ID", "IDENTITY", "Matricola dipendente", "protect", "alphanumeric", True),
    ("SOCIAL_SECURITY_ID", "IDENTITY", "Posizione INPS / INAIL", "protect", "alphanumeric", True),
    ("UNION_MEMBERSHIP", "IDENTITY", "Appartenenza sindacale", "protect", None, False),
    ("CADASTRAL_REF", "IDENTITY", "Dati catastali", "protect", "alphanumeric", True),
    ("TAX_DOCUMENT_ID", "LEGAL", "Protocollo / atto fiscale", "protect", "alphanumeric", True),
]

# Optional "n." / "nr." / "numero" / "n°" between a label and its value.
_NUM = r"\s*(?i:(?:n\.|nr\.|num\.|numero|n°)\s*)?:?\s*"
_UNIONS = r"(?:CGIL|CISL|UIL|UGL|USB|FIOM|FIM|UILM|FILCAMS|FISASCAT|UILTUCS|COBAS|CUB|CONFSAL)"

PIVA_OLD_PATTERN = r"(?:p\.?\s?iva|partita\s+iva)[^\d]*(\d{11})"
PIVA_OLD_DESCRIPTION = "Partita IVA italiana (richiede prefisso testuale)"
VAT_LABELED_PATTERN = (
    r"(?i:\bp\.?\s?iva|\bpartita\s+iva|\bvat(?:\s+(?:no|number|n)\.?)?)" + _NUM + r"(?:IT\s?)?(\d{11})\b"
)
VAT_LABELED_FLAGS = "VALIDATE:partita_iva"
VAT_LABELED_DESCRIPTION = "Partita IVA dopo etichetta (P.IVA / partita IVA / VAT), con controllo Luhn"

# (pii_type, pattern, flags, capture_group, description)
PATTERNS = [
    ("VAT_NUMBER", VAT_LABELED_PATTERN, VAT_LABELED_FLAGS, 1, VAT_LABELED_DESCRIPTION),
    ("VAT_NUMBER", r"\b(IT\d{11})\b", "VALIDATE:partita_iva", 1,
     "Partita IVA con prefisso IT (es. IT01234567897), con controllo Luhn"),
    ("FISCAL_CODE",
     r"(?<![A-Z0-9])([A-Z]{6}[0-9LMNPQRSTUV]{2}[A-EHLMPR-T][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z])(?![A-Z0-9])",
     "VALIDATE:codice_fiscale", 1, "Codice fiscale incl. omocodia, con carattere di controllo"),
    ("FISCAL_CODE", r"(?:(?i:\bcodice\s+fiscale|\bcod\.\s?fisc\.)|\bC\.?F\.?)" + _NUM + r"(\d{11})\b",
     "VALIDATE:partita_iva", 1, "Codice fiscale numerico (soggetti diversi da persone fisiche)"),
    ("IBAN", r"(?<![A-Z0-9])([A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?)(?![A-Z0-9])",
     "VALIDATE:iban", 1, "IBAN anche con spazi e non italiano, con controllo mod 97"),
    ("IDENTITY_CARD", r"(?i:\bcarta\s+d.identit[àa](?:\s+elettronica)?|\bC\.?I\.?E\.?)" + _NUM + r"([A-Z]{2}\d{5}[A-Z]{2})\b",
     "", 1, "Carta d'identità elettronica CIE 3.0 (2 lettere + 5 cifre + 2 lettere) dopo etichetta"),
    ("DRIVER_LICENSE", r"(?i:\bpatente(?:\s+di\s+guida)?)" + _NUM + r"([A-Z]{2}\d{7}[A-Z]|U1[A-Z0-9]{7}[A-Z])\b",
     "", 1, "Numero patente dopo etichetta"),
    ("EMPLOYEE_ID",
     r"(?i:\bmatricola(?:\s+(?:dipendente|aziendale|personale))?|\bcod(?:ice|\.)\s*dipendente|\bID\s+dipendente|\bbadge)"
     + _NUM + r"(?!INPS|INAIL)((?=[A-Z0-9/\-]*\d)[A-Z0-9][A-Z0-9/\-]{2,14})\b",
     "", 1, "Matricola / codice dipendente dopo etichetta"),
    ("SOCIAL_SECURITY_ID",
     r"(?:(?i:\bmatricola\s+(?:aziendale\s+)?INPS|\bposizione\s+(?:contributiva\s+)?INPS|\bcodice\s+INPS"
     r"|\bcodice\s+(?:ditta|cliente)\s+INAIL|\bposizione\s+assicurativa\s+territoriale)|\bPAT(?:\s+INAIL)?)"
     + _NUM + r"(\d{6,10}(?:[/\-]\d{2})?)\b",
     "", 1, "Matricola INPS, codice ditta INAIL, PAT dopo etichetta"),
    ("UNION_MEMBERSHIP",
     r"\b((?:iscritt[oa]|aderente)\s+(?:(?:al\s+|ad\s+un\s+)?sindacato(?:\s+" + _UNIONS + r")?|all[a']\s*" + _UNIONS + r")"
     r"|(?:trattenut[ae]|quota|delega|contributo|tessera)\s+sindacale(?:\s+" + _UNIONS + r")?)\b",
     "IGNORECASE", 1, "Appartenenza sindacale (art. 9 GDPR)"),
    ("HEALTH_DATA",
     r"\b((?:assenz[ae]|congedo|certificat[oi](?:\s+medic[oi])?|period[oi]|stato|giorni|indennit[àa])\s+(?:di|per)\s+malattia"
     r"|in\s+malattia|malattia\s+professionale|infortunio\s+(?:sul\s+lavoro|in\s+itinere)"
     r"|invalidit[àa]\s+(?:civile|permanente)(?:\s+(?:al|del|pari\s+al)\s+\d{1,3}\s?%)?"
     r"|(?:portatore|portatrice)\s+di\s+handicap|disabilit[àa]\s+grave|stato\s+di\s+gravidanza"
     r"|maternit[àa]\s+(?:obbligatoria|anticipata|a\s+rischio)|(?:diagnosi|patologia)\s*:\s*[^\n.;,]{3,60}"
     r"|ricover(?:o|at[oa])\s+(?:ospedalier[oa]|presso\s+l'ospedale))",
     "IGNORECASE", 1, "Dati relativi alla salute in testi HR/assicurativi (art. 9 GDPR)"),
    ("CADASTRAL_REF",
     r"\b((?:foglio|fg\.?)\s*(?:n\.\s*)?\d{1,4}[\s,;\-]*(?:particella|part\.|p\.lla|mappale|mapp?\.)\s*(?:n\.\s*)?\d{1,5}"
     r"(?:[\s,;\-]*(?:subalterno|sub\.?)\s*(?:n\.\s*)?\d{1,4})?)",
     "IGNORECASE", 1, "Dati catastali: foglio + particella/mappale [+ subalterno]"),
    ("TAX_DOCUMENT_ID", r"(?<!\d)(\d{17}-\d{6})(?!\d)", "", 1,
     "Protocollo telematico Agenzia Entrate (17 cifre - 6 cifre)"),
    ("TAX_DOCUMENT_ID", r"(?i:\bcartell[ae](?:\s+di\s+pagamento)?)" + _NUM + r"(\d{3} ?\d{4} ?\d{10} ?\d{3})\b",
     "", 1, "Numero cartella di pagamento (20 cifre)"),
    ("TAX_DOCUMENT_ID",
     r"(?i:\bavviso\s+di\s+(?:accertamento|liquidazione|irregolarit[àa])|\batto\s+di\s+(?:accertamento|contestazione))"
     + _NUM + r"((?=[A-Z0-9/\-]*\d{4})[A-Z0-9][A-Z0-9/\-]{5,24})\b",
     "", 1, "Numero avviso/atto di accertamento o liquidazione"),
    ("POLICY_NUMBER", r"(?i:\bsinistro|\bpolizza)" + _NUM + r"(\d{2,4}/\d{4,12}|\d{6,15})\b", "", 1,
     "Numero sinistro/polizza numerico (anche anno/progressivo)"),
]

DATE_BORN_RULE = {
    "from_type": "DATE",
    "to_type": "DATE_BORN",
    "context_pattern": (
        r"(?i)(?:data\s+di\s+nascita|nat[ao]\s+il"
        r"|nat[ao]\s+a\s+[A-ZÀ-Ý][\w'À-ÿ]*(?:\s+[A-ZÀ-Ý][\w'À-ÿ]*){0,3}\s*(?:\([A-Z]{2}\)\s*)?,?\s*il)\s*:?\s*$"
    ),
    "context_window": 80,
    "description": "Data dopo \"data di nascita\" / \"nato il\" / \"nato a X (PR) il\" → DATE_BORN",
}

_IDENTITY = ["PERSON", "FISCAL_CODE", "EMAIL", "PHONE", "ADDRESS", "IBAN", "CREDIT_CARD",
             "DATE_BORN", "CITY_BORN", "IDENTITY_CARD", "PASSPORT", "DRIVER_LICENSE", "ACCOUNT"]
_FACTS = ["DATE", "MONEY", "LAW_REF", "COMPANY", "ORGANIZATION"]

POLICIES = [
    {
        "domain": "hr_payroll",
        "display_name": "HR e paghe (consulenti del lavoro)",
        "protect": _IDENTITY + ["VAT_NUMBER", "HEALTH_CARD", "EMPLOYEE_ID", "SOCIAL_SECURITY_ID",
                                "HEALTH_DATA", "UNION_MEMBERSHIP", "USERNAME"],
        "keep": _FACTS + ["SALARY"],
        "description": "Cedolini, contratti e pratiche del personale: redazione forte di identità, "
                       "matricole, posizioni INPS/INAIL e dati art. 9 (salute, sindacato). Mantiene importi e date.",
    },
    {
        "domain": "tax_accounting",
        "display_name": "Fiscale e contabilità (commercialisti)",
        "protect": _IDENTITY + ["VAT_NUMBER", "TAX_DOCUMENT_ID", "CADASTRAL_REF", "HEALTH_DATA"],
        "keep": _FACTS + ["SALARY"],
        "description": "Dichiarazioni, F24, avvisi e cartelle: protegge CF, P.IVA, IBAN e protocolli "
                       "che identificano il contribuente. Mantiene importi, date e riferimenti normativi.",
    },
    {
        "domain": "real_estate_insurance",
        "display_name": "Immobiliare e assicurazioni",
        "protect": _IDENTITY + ["VAT_NUMBER", "TARGA", "CADASTRAL_REF", "POLICY_NUMBER",
                                "HEALTH_DATA", "HEALTH_CARD"],
        "keep": _FACTS,
        "description": "Compravendite, locazioni, polizze e sinistri: protegge documenti d'identità, "
                       "targhe, dati catastali e numeri polizza/sinistro. Mantiene importi e date.",
    },
    {
        "domain": "generic_professional",
        "display_name": "Studio professionale (generico)",
        "protect": _IDENTITY + ["VAT_NUMBER", "HEALTH_CARD", "HEALTH_DATA", "UNION_MEMBERSHIP", "TARGA",
                                "EMPLOYEE_ID", "SOCIAL_SECURITY_ID", "CADASTRAL_REF", "POLICY_NUMBER",
                                "TAX_DOCUMENT_ID", "SALARY", "USERNAME", "SECRET", "API_KEY", "IP_ADDRESS",
                                "IMEI", "MAC_ADDRESS", "GPS_COORDINATE",
                                "DE_TAX_ID", "FR_SIRET", "FR_SIREN", "ES_DNI_NIE", "UK_NI_NUMBER", "NL_BSN"],
        "keep": _FACTS + ["URL"],
        "description": "Default prudente per qualsiasi testo professionale: protegge identità, contatti, "
                       "identificativi e dati art. 9. Mantiene importi, date e riferimenti normativi.",
    },
]


def _insert_pattern(conn, pii_type: str, pattern: str, flags: str, capture_group: int, description: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO regex_patterns (id, pii_type, pattern, flags, capture_group, description, enabled) "
            "SELECT :id, :pii_type, :pattern, :flags, :cg, :description, true "
            "WHERE NOT EXISTS (SELECT 1 FROM regex_patterns WHERE pii_type = :pii_type2 AND pattern = :pattern2)"
        ),
        {"id": uuid.uuid4(), "pii_type": pii_type, "pattern": pattern, "flags": flags, "cg": capture_group,
         "description": description, "pii_type2": pii_type, "pattern2": pattern},
    )


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

    # Consolidate the legacy, unregistered PIVA pattern into VAT_NUMBER (only if untouched).
    conn.execute(
        sa.text(
            "UPDATE regex_patterns SET pii_type = 'VAT_NUMBER', pattern = :new, flags = :flags, "
            "capture_group = 1, description = :d WHERE pii_type = 'PIVA' AND pattern = :old"
        ),
        {"new": VAT_LABELED_PATTERN, "flags": VAT_LABELED_FLAGS, "d": VAT_LABELED_DESCRIPTION,
         "old": PIVA_OLD_PATTERN},
    )
    for pattern in PATTERNS:
        _insert_pattern(conn, *pattern)

    conn.execute(
        sa.text(
            "INSERT INTO reclassification_rules "
            "(id, from_type, to_type, context_pattern, entity_pattern, context_window, description, enabled) "
            "VALUES (CAST(:id AS uuid), :from_type, :to_type, :context_pattern, NULL, :context_window, :description, true)"
        ),
        {"id": str(uuid.uuid4()), **DATE_BORN_RULE},
    )

    for policy in POLICIES:
        conn.execute(
            sa.text(
                "INSERT INTO domain_policies (domain, display_name, default_mode, protect_types, keep_types, description) "
                "VALUES (:domain, :display_name, 'tag', CAST(:protect AS jsonb), CAST(:keep AS jsonb), :description) "
                "ON CONFLICT (domain) DO NOTHING"
            ),
            {"domain": policy["domain"], "display_name": policy["display_name"],
             "protect": json.dumps(policy["protect"]), "keep": json.dumps(policy["keep"]),
             "description": policy["description"]},
        )
        conn.execute(
            sa.text(
                "INSERT INTO context_types (code, display_name, domain, default_mode, description) "
                "VALUES (:domain, :display_name, :domain, 'tag', :description) ON CONFLICT (code) DO NOTHING"
            ),
            {"domain": policy["domain"], "display_name": policy["display_name"],
             "description": policy["description"]},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM context_types WHERE code = ANY(:codes) AND domain = code AND tenant_id IS NULL"),
        {"codes": [p["domain"] for p in POLICIES]},
    )
    conn.execute(
        sa.text("DELETE FROM domain_policies WHERE domain = ANY(:domains) AND tenant_id IS NULL"),
        {"domains": [p["domain"] for p in POLICIES]},
    )
    conn.execute(
        sa.text("DELETE FROM reclassification_rules WHERE from_type = 'DATE' AND to_type = 'DATE_BORN' "
                "AND context_pattern = :p"),
        {"p": DATE_BORN_RULE["context_pattern"]},
    )
    conn.execute(
        sa.text(
            "UPDATE regex_patterns SET pii_type = 'PIVA', pattern = :old, flags = 'IGNORECASE', description = :d "
            "WHERE pii_type = 'VAT_NUMBER' AND pattern = :new"
        ),
        {"old": PIVA_OLD_PATTERN, "d": PIVA_OLD_DESCRIPTION, "new": VAT_LABELED_PATTERN},
    )
    for pii_type, pattern, *_ in PATTERNS:
        conn.execute(
            sa.text("DELETE FROM regex_patterns WHERE pii_type = :pii_type AND pattern = :pattern"),
            {"pii_type": pii_type, "pattern": pattern},
        )
    conn.execute(
        sa.text("DELETE FROM pii_type_registry WHERE code = ANY(:codes)"),
        {"codes": [t[0] for t in NEW_TYPES]},
    )
