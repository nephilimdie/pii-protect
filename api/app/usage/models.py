from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    api_key_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    policy_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chars_in: Mapped[int] = mapped_column(Integer, nullable=False)
    chars_out: Mapped[int] = mapped_column(Integer, nullable=False)
    entities_count: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_types_summary: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    engine_regex_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    engine_presidio_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    engine_privacy_filter_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    engine_ai4privacy_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
