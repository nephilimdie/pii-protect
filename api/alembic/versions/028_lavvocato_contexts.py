"""lavvocato context_types — register the context_type codes sent by lavvocato

Adds the `condominio` domain policy and maps every context_type that the lavvocato
backend sends (generation = tag, embedding = surrogate, domain-qualified variants for
fact_extraction and document_analysis) to the right domain policy.

Revision ID: 028
Revises: 027
Create Date: 2026-06-08
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None

# condominio mirrors the identity-protection of `default`; kept distinct so it can be
# tuned independently later. Keeps the usual legal facts.
CONDOMINIO_POLICY = {
    "domain": "condominio",
    "protect": ["PERSON", "FISCAL_CODE", "PASSPORT", "IDENTITY_CARD", "DRIVER_LICENSE",
                "HEALTH_CARD", "EMAIL", "PHONE", "ADDRESS", "ACCOUNT", "IBAN", "CREDIT_CARD",
                "TARGA", "BIC", "USERNAME", "CITY_BORN"],
    "keep": ["DATE", "MONEY", "LAW_REF", "URL"],
    "description": "Dispute condominiali: protegge identità/contatti, mantiene date, importi e riferimenti normativi.",
}

# (code, display_name, domain, default_mode, description)
CONTEXTS = [
    # ── Generazione chat / intake / ruoli multi-agente → default (tag) ──────────
    ("messaging.chat_case_qa",            "Chat — risposta caso",        "default", "tag", "Risposta principale della chat"),
    ("messaging.chat_answer_decision",    "Chat — decisione risposta",   "default", "tag", "Decide se/come rispondere"),
    ("messaging.intent_classify",         "Chat — classificazione intento", "default", "tag", "Classificazione intento utente"),
    ("messaging.dispute_safety_gateway",  "Chat — safety gateway",       "default", "tag", "Gate sicurezza/contestabilità"),
    ("intake.conversation",               "Intake — conversazione",      "default", "tag", "Intake conversazionale"),
    ("intake.journey_classification",     "Intake — classificazione percorso", "default", "tag", "Classificazione journey"),
    ("intake.legal_value_extraction",     "Intake — estrazione valori",  "default", "tag", "Estrazione valori legali"),
    ("intake.laj",                        "Intake — adjudication",       "default", "tag", "Legal adjudication judgement"),
    ("ai.role.critic",                    "AI ruolo — critic",           "default", "tag", "Ruolo critic (multi-agente)"),
    ("ai.role.adjudicator",               "AI ruolo — adjudicator",      "default", "tag", "Ruolo adjudicator (multi-agente)"),

    # ── Multe (Codice della Strada) → fine_appeal (tag) ─────────────────────────
    ("self_service.fine_appeal_extraction",        "Multa — estrazione",  "fine_appeal", "tag", "Estrazione dati verbale"),
    ("self_service.fine_appeal_drafting",          "Multa — ricorso",     "fine_appeal", "tag", "Bozza ricorso multa"),
    ("self_service.fine_appeal_strategy_analysis", "Multa — strategia",   "fine_appeal", "tag", "Analisi strategia ricorso"),
    ("casefacts.fact_extraction.codice_della_strada", "Fatti — multe",    "fine_appeal", "tag", "Estrazione fatti (codice della strada)"),
    ("messaging.document_analysis_artifact.codice_della_strada", "Analisi doc — multe", "fine_appeal", "tag", "Analisi documento (verbale)"),

    # ── Condominio → condominio (tag) ───────────────────────────────────────────
    ("self_service.condo_dispute_drafting",        "Condominio — bozza",  "condominio", "tag", "Bozza disputa condominiale"),
    ("casefacts.fact_extraction.condominio",       "Fatti — condominio",  "condominio", "tag", "Estrazione fatti condominio"),
    ("messaging.document_analysis_artifact.condominio", "Analisi doc — condominio", "condominio", "tag", "Analisi documento condominiale"),

    # ── Contratti → contract_analysis (tag) ─────────────────────────────────────
    ("messaging.document_analysis_artifact",          "Analisi documento",          "contract_analysis", "tag", "Analisi documento (default contratti)"),
    ("messaging.document_analysis_artifact.contratti", "Analisi doc — contratti",   "contract_analysis", "tag", "Analisi documento contrattuale"),
    ("casefacts.fact_extraction.contratti",           "Fatti — contratti",          "contract_analysis", "tag", "Estrazione fatti contratto"),

    # ── Altri domini di fact_extraction → default (tag) ─────────────────────────
    ("casefacts.fact_extraction",              "Fatti — generico",   "default", "tag", "Estrazione fatti (gruppo non specificato)"),
    ("casefacts.fact_extraction.incidenti",    "Fatti — incidenti",  "default", "tag", "Estrazione fatti incidenti"),
    ("casefacts.fact_extraction.consumatori",  "Fatti — consumatori", "default", "tag", "Estrazione fatti consumatori"),
    ("casefacts.fact_extraction.lavoro",       "Fatti — lavoro",     "default", "tag", "Estrazione fatti lavoro"),
    ("casefacts.fact_extraction.successioni",  "Fatti — successioni", "default", "tag", "Estrazione fatti successioni"),
    ("casefacts.fact_extraction.privacy",      "Fatti — privacy",    "default", "tag", "Estrazione fatti privacy/GDPR"),

    # ── Embedding documenti utente → surrogate ──────────────────────────────────
    ("case_file_document", "Embedding documento utente", "default", "surrogate", "Testo documento utente per embedding (surrogati)"),
]


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            "INSERT INTO domain_policies (domain, protect_types, keep_types, description)"
            " VALUES (:domain, CAST(:protect AS jsonb), CAST(:keep AS jsonb), :description)"
            " ON CONFLICT (domain) DO NOTHING"
        ),
        {
            "domain": CONDOMINIO_POLICY["domain"],
            "protect": json.dumps(CONDOMINIO_POLICY["protect"]),
            "keep": json.dumps(CONDOMINIO_POLICY["keep"]),
            "description": CONDOMINIO_POLICY["description"],
        },
    )

    for code, display_name, domain, mode, description in CONTEXTS:
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
    conn = op.get_bind()
    codes = [c[0] for c in CONTEXTS]
    conn.execute(
        sa.text("DELETE FROM context_types WHERE code = ANY(:codes)"),
        {"codes": codes},
    )
    conn.execute(sa.text("DELETE FROM domain_policies WHERE domain = 'condominio'"))
