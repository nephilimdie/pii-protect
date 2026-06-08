"""context_types — named contexts with linked domain policy and default mode

Revision ID: 022
Revises: 021
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None

DEFAULT_CONTEXTS = [
    ("default",           "Default",             "default",           "tag",       "Contesto generico"),
    ("fine_appeal",       "Ricorso Multa",        "fine_appeal",       "tag",       "Ricorso per sanzione amministrativa"),
    ("contract_analysis", "Analisi Contratto",    "contract_analysis", "tag",       "Revisione e analisi di contratti"),
    ("medical",           "Documenti Medici",     "medical",           "tag",       "Referti, cartelle cliniche"),
    ("hr",                "HR / Lavoro",          "default",           "tag",       "Documenti risorse umane e contratti di lavoro"),
    ("legal_brief",       "Atto Legale",          "contract_analysis", "tag",       "Atti, memorie, istanze"),
    ("embedding",         "Embedding Esterno",    "default",           "surrogate", "Testo da inviare a embedder esterno — usa surrogati"),
]


def upgrade() -> None:
    op.create_table(
        "context_types",
        sa.Column("code",         sa.String(100), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("domain",       sa.String(100), sa.ForeignKey("domain_policies.domain",
                                                                  ondelete="SET NULL"), nullable=True),
        sa.Column("default_mode", sa.String(20),  nullable=False, server_default="tag"),
        sa.Column("description",  sa.Text,        nullable=True),
        sa.Column("enabled",      sa.Boolean,     nullable=False, server_default="true"),
        sa.Column("created_at",   sa.DateTime,    nullable=False, server_default=sa.func.now()),
    )

    conn = op.get_bind()
    for code, display_name, domain, mode, description in DEFAULT_CONTEXTS:
        conn.execute(
            sa.text(
                "INSERT INTO context_types (code, display_name, domain, default_mode, description)"
                " VALUES (:code, :display_name, :domain, :mode, :description)"
                " ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "display_name": display_name, "domain": domain,
             "mode": mode, "description": description},
        )


def downgrade() -> None:
    op.drop_table("context_types")
