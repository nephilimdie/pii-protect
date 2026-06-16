"""policy history tables

Revision ID: 031
Revises: 030
Create Date: 2026-06-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domain_policy_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("domain", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("domain", "version", name="uq_domain_policy_versions_domain_version"),
    )
    op.create_table(
        "context_type_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", "version", name="uq_context_type_versions_code_version"),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO domain_policy_versions (domain, version, snapshot) "
            "SELECT domain, version, jsonb_build_object("
            "'domain', domain, "
            "'version', version, "
            "'protect_types', protect_types, "
            "'keep_types', keep_types, "
            "'surrogate_types', surrogate_types, "
            "'description', description, "
            "'enabled', enabled, "
            "'updated_at', updated_at"
            ") "
            "FROM domain_policies"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO context_type_versions (code, version, snapshot) "
            "SELECT code, version, jsonb_build_object("
            "'code', code, "
            "'version', version, "
            "'display_name', display_name, "
            "'domain', domain, "
            "'default_mode', default_mode, "
            "'description', description, "
            "'enabled', enabled, "
            "'created_at', created_at"
            ") "
            "FROM context_types"
        )
    )


def downgrade() -> None:
    op.drop_table("context_type_versions")
    op.drop_table("domain_policy_versions")