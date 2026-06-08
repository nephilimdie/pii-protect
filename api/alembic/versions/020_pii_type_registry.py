"""pii_type_registry — source of truth for PII types

Revision ID: 020
Revises: 019
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None

# (code, category, display_name, default_action, faker_strategy, reversible)
# faker_strategy maps to a function in surrogates/generators.py
TYPES = [
    # IDENTITY
    ("PERSON",          "IDENTITY",   "Persona",              "protect", "person",       True),
    ("FISCAL_CODE",     "IDENTITY",   "Codice Fiscale",       "protect", "fiscal_code",  True),
    ("PASSPORT",        "IDENTITY",   "Passaporto",           "protect", "passport",     True),
    ("IDENTITY_CARD",   "IDENTITY",   "Carta d'Identità",     "protect", "identity_card",True),
    ("DRIVER_LICENSE",  "IDENTITY",   "Patente",              "protect", "driver_license",True),
    ("HEALTH_CARD",     "IDENTITY",   "Tessera Sanitaria",    "protect", "health_card",  True),
    # CONTACT
    ("EMAIL",           "CONTACT",    "Email",                "protect", "email",        True),
    ("PHONE",           "CONTACT",    "Telefono",             "protect", "phone",        True),
    ("ADDRESS",         "CONTACT",    "Indirizzo",            "protect", "address",      True),
    ("CITY_BORN",       "CONTACT",    "Città di Nascita",     "protect", "city",         True),
    ("ACCOUNT",         "CONTACT",    "Account / Handle",     "protect", "username",     True),
    # FINANCIAL
    ("IBAN",            "FINANCIAL",  "IBAN",                 "protect", "iban",         True),
    ("CREDIT_CARD",     "FINANCIAL",  "Carta di Credito",     "protect", "credit_card",  True),
    ("SALARY",          "FINANCIAL",  "RAL / Stipendio",      "protect", "salary",       True),
    ("MONEY",           "FINANCIAL",  "Importo",              "keep",    None,            False),
    # LEGAL
    ("DATE",            "LEGAL",      "Data",                 "keep",    "date_shift",   False),
    ("LAW_REF",         "LEGAL",      "Riferimento Normativo","keep",    None,            False),
    ("PRACTICE_ID",     "LEGAL",      "Numero Pratica",       "protect", "practice_id",  True),
    ("POLICY_NUMBER",   "LEGAL",      "Numero Polizza",       "protect", "policy_number",True),
    ("LOYALTY_ID",      "LEGAL",      "Codice Fedeltà",       "protect", "loyalty_id",   True),
    ("PNR",             "LEGAL",      "PNR",                  "protect", "pnr",          True),
    ("TICKET_ID",       "LEGAL",      "Ticket ID",            "protect", "ticket_id",    True),
    # VEHICLE
    ("TARGA",           "VEHICLE",    "Targa",                "protect", "targa",        True),
    ("IMEI",            "VEHICLE",    "IMEI",                 "protect", "imei",         True),
    # NETWORK
    ("IP_ADDRESS",      "NETWORK",    "Indirizzo IP",         "protect", "ip",           True),
    ("MAC_ADDRESS",     "NETWORK",    "MAC Address",          "protect", "mac",          True),
    ("URL",             "NETWORK",    "URL",                  "protect", "url",          True),
    ("GPS_COORDINATE",  "NETWORK",    "Coordinate GPS",       "protect", "gps",          True),
    ("API_KEY",         "NETWORK",    "API Key",              "protect", "api_key",      True),
    # CREDENTIAL
    ("SECRET",          "CREDENTIAL", "Password / Segreto",   "protect", "password",     False),
    ("USERNAME",        "CREDENTIAL", "Username",             "protect", "username",     True),
    ("BIC",             "FINANCIAL",  "BIC / SWIFT",          "protect", "bic",          True),
    # ORGANIZATION
    ("ORGANIZATION",    "IDENTITY",   "Organizzazione",       "protect", "organization", True),
    ("COMPANY",         "IDENTITY",   "Azienda",              "protect", "company",      True),
]


def upgrade() -> None:
    op.create_table(
        "pii_type_registry",
        sa.Column("code",           sa.String(50),  primary_key=True),
        sa.Column("category",       sa.String(50),  nullable=False),
        sa.Column("display_name",   sa.String(100), nullable=False),
        sa.Column("default_action", sa.String(20),  nullable=False, server_default="protect"),
        sa.Column("faker_strategy", sa.String(50),  nullable=True),
        sa.Column("reversible",     sa.Boolean,     nullable=False, server_default="true"),
        sa.Column("enabled",        sa.Boolean,     nullable=False, server_default="true"),
        sa.Column("description",    sa.Text,        nullable=True),
    )
    op.create_index("ix_pii_type_registry_category", "pii_type_registry", ["category"])

    conn = op.get_bind()
    for code, category, display_name, action, strategy, reversible in TYPES:
        conn.execute(
            sa.text(
                "INSERT INTO pii_type_registry (code, category, display_name, default_action, faker_strategy, reversible)"
                " VALUES (:code, :category, :display_name, :action, :strategy, :reversible)"
                " ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "category": category, "display_name": display_name,
             "action": action, "strategy": strategy, "reversible": reversible},
        )


def downgrade() -> None:
    op.drop_index("ix_pii_type_registry_category", "pii_type_registry")
    op.drop_table("pii_type_registry")
