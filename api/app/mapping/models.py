from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class TenantKey(Base):
    """Stores one DEK per tenant, encrypted with the global KEK (ENCRYPTION_KEY env var).

    Self-hosted deployments (tenant_id=None) never write here — the KEK is used
    directly as the DEK for backward compatibility.
    """
    __tablename__ = "tenant_keys"

    tenant_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    dek_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PiiMapping(Base):
    __tablename__ = "pii_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "context_id", "context_type", "token", name="uq_mapping_tenant_context_token"),
        Index("ix_pii_mappings_tenant_context", "tenant_id", "context_id", "context_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_id: Mapped[str] = mapped_column(String(255), nullable=False)
    context_type: Mapped[str] = mapped_column(String(50), nullable=False)
    token: Mapped[str] = mapped_column(String(100), nullable=False)
    original_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    pii_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
