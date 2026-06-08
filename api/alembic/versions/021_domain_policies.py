"""domain_policies — per-domain protect/keep rules

Revision ID: 021
Revises: 020
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None

DEFAULT_POLICIES = [
    {
        "domain": "default",
        "protect": ["PERSON","FISCAL_CODE","PASSPORT","IDENTITY_CARD","DRIVER_LICENSE",
                    "HEALTH_CARD","EMAIL","PHONE","ADDRESS","ACCOUNT","IBAN","CREDIT_CARD",
                    "SALARY","PRACTICE_ID","POLICY_NUMBER","LOYALTY_ID","PNR","TICKET_ID",
                    "TARGA","IMEI","IP_ADDRESS","MAC_ADDRESS","API_KEY","SECRET","USERNAME",
                    "BIC","ORGANIZATION","COMPANY","CITY_BORN"],
        "keep": ["DATE","MONEY","LAW_REF","URL","GPS_COORDINATE"],
        "description": "Policy di default: protegge identità e dati di contatto, mantiene date e importi.",
    },
    {
        "domain": "fine_appeal",
        "protect": ["PERSON","FISCAL_CODE","EMAIL","PHONE","ADDRESS","IBAN","IDENTITY_CARD",
                    "DRIVER_LICENSE","ACCOUNT","CITY_BORN"],
        "keep": ["DATE","MONEY","LAW_REF","TARGA","PRACTICE_ID","TICKET_ID"],
        "description": "Ricorso multa: mantiene targa, importo, data, articolo e numero verbale.",
    },
    {
        "domain": "contract_analysis",
        "protect": ["PERSON","FISCAL_CODE","EMAIL","PHONE","ADDRESS","IBAN","CREDIT_CARD",
                    "TARGA","IDENTITY_CARD","ACCOUNT","CITY_BORN","COMPANY","ORGANIZATION"],
        "keep": ["DATE","MONEY","LAW_REF","POLICY_NUMBER"],
        "description": "Analisi contratti: protegge anche targa e ragione sociale.",
    },
    {
        "domain": "medical",
        "protect": ["PERSON","FISCAL_CODE","EMAIL","PHONE","ADDRESS","HEALTH_CARD",
                    "ACCOUNT","CITY_BORN"],
        "keep": ["DATE","MONEY","LAW_REF","PRACTICE_ID"],
        "description": "Documenti medici: protegge tessera sanitaria, mantiene date e ID pratica.",
    },
]


def upgrade() -> None:
    op.create_table(
        "domain_policies",
        sa.Column("domain",       sa.String(100), primary_key=True),
        sa.Column("protect_types",JSONB,           nullable=False, server_default="[]"),
        sa.Column("keep_types",   JSONB,           nullable=False, server_default="[]"),
        sa.Column("description",  sa.Text,         nullable=True),
        sa.Column("enabled",      sa.Boolean,      nullable=False, server_default="true"),
        sa.Column("updated_at",   sa.DateTime,     nullable=False, server_default=sa.func.now()),
    )

    conn = op.get_bind()
    import json
    for p in DEFAULT_POLICIES:
        conn.execute(
            sa.text(
                "INSERT INTO domain_policies (domain, protect_types, keep_types, description)"
                " VALUES (:domain, CAST(:protect AS jsonb), CAST(:keep AS jsonb), :description)"
            ),
            {"domain": p["domain"],
             "protect": json.dumps(p["protect"]),
             "keep": json.dumps(p["keep"]),
             "description": p["description"]},
        )


def downgrade() -> None:
    op.drop_table("domain_policies")
