"""surrogate_mappings + surrogate_profiles

Revision ID: 023
Revises: 022
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-value cache: real_hash → fake_value, keyed by (context_id, pii_type)
    op.create_table(
        "surrogate_mappings",
        sa.Column("id",          UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("context_id",  sa.String(255),     nullable=False),
        sa.Column("pii_type",    sa.String(50),      nullable=False),
        sa.Column("real_hash",   sa.String(64),      nullable=False),  # sha256(real_value)
        sa.Column("fake_value",  sa.Text,            nullable=False),
        sa.Column("created_at",  sa.DateTime,        nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("context_id", "pii_type", "real_hash", name="uq_surrogate_mapping"),
    )
    op.create_index("ix_surrogate_mappings_context", "surrogate_mappings", ["context_id", "pii_type"])

    # Coherent fake persona profiles (for PERSON / FISCAL_CODE)
    op.create_table(
        "surrogate_profiles",
        sa.Column("id",              UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("context_id",      sa.String(255),     nullable=False),
        sa.Column("real_hash",       sa.String(64),      nullable=False),  # sha256(normalised key)
        sa.Column("fake_first_name", sa.String(100),     nullable=False),
        sa.Column("fake_last_name",  sa.String(100),     nullable=False),
        sa.Column("fake_birth_date", sa.Date,            nullable=False),
        sa.Column("fake_gender",     sa.String(1),       nullable=False),
        sa.Column("fake_city",       sa.String(100),     nullable=False),
        sa.Column("fake_belfiore",   sa.String(4),       nullable=False),
        sa.Column("fake_cf",         sa.String(16),      nullable=False),
        sa.Column("created_at",      sa.DateTime,        nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("context_id", "real_hash", name="uq_surrogate_profile"),
    )
    op.create_index("ix_surrogate_profiles_context", "surrogate_profiles", ["context_id"])


def downgrade() -> None:
    op.drop_index("ix_surrogate_profiles_context", "surrogate_profiles")
    op.drop_table("surrogate_profiles")
    op.drop_index("ix_surrogate_mappings_context", "surrogate_mappings")
    op.drop_table("surrogate_mappings")
