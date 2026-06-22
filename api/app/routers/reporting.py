from __future__ import annotations
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin, require_auditor
from app.identity.models import ApiKey
from app.reporting.stats_service import StatsService
from app.audit.audit_service import AuditService
from app.mapping.repository import MappingRepository
from app.config import settings

router = APIRouter()


class AuditLogEntry(BaseModel):
    id: uuid.UUID
    api_key_id: uuid.UUID | None
    action: str | None
    context_id: str | None
    pii_types_found: list[str] | None
    char_count: int | None
    document_hash: str | None = None
    ip: str | None = None
    reason: str | None = None
    event_category: str = "engine"
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    items: list[AuditLogEntry]
    total: int
    page: int


class CleanupRequest(BaseModel):
    ttl_days: int = 30


class CleanupResponse(BaseModel):
    deleted_count: int


class StatsResponse(BaseModel):
    total_anonymizations: int
    total_tokens_created: int
    pii_types_breakdown: dict[str, int]
    requests_last_24h: int
    usage_events_total: int
    usage_chars_in_total: int


class BulkDeleteRequest(BaseModel):
    ids: list[uuid.UUID]


class MappingItem(BaseModel):
    id: str
    context_id: str
    context_type: str
    token: str
    pii_type: str
    original: str
    created_at: datetime


class MappingListResponse(BaseModel):
    items: list[MappingItem]
    total: int
    page: int


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    api_key: ApiKey = Depends(require_auditor),
    db: AsyncSession = Depends(get_db),
):
    # Platform admin (no tenant on key) sees global stats; tenant-scoped key sees only its tenant
    service = StatsService(db, tenant_id=api_key.tenant_id)
    return await service.get_summary()


@router.get("/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    api_key: ApiKey = Depends(require_auditor),
    db: AsyncSession = Depends(get_db),
):
    service = AuditService(db)
    items, total = await service.list_paginated(page, per_page, action, tenant_id=api_key.tenant_id)
    return AuditLogResponse(items=items, total=total, page=page)


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup(
    body: CleanupRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = MappingRepository(db)
    deleted = await repo.delete_expired(body.ttl_days, tenant_id=api_key.tenant_id)
    return CleanupResponse(deleted_count=deleted)


@router.delete("/audit-log/bulk", response_model=CleanupResponse)
async def delete_audit_log_bulk(
    body: BulkDeleteRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AuditService(db)
    deleted = await service.delete_by_ids(body.ids, tenant_id=api_key.tenant_id)
    return CleanupResponse(deleted_count=deleted)


@router.get("/mappings", response_model=MappingListResponse)
async def list_mappings(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = MappingRepository(db)
    items, total = await repo.list_paginated(page, per_page, tenant_id=api_key.tenant_id)
    return MappingListResponse(items=items, total=total, page=page)


@router.delete("/mappings/bulk", response_model=CleanupResponse)
async def delete_mappings_bulk(
    body: BulkDeleteRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = MappingRepository(db)
    deleted = await repo.delete_by_ids(body.ids, tenant_id=api_key.tenant_id)
    return CleanupResponse(deleted_count=deleted)


class AnomalyEntry(BaseModel):
    type: str
    description: str


class AnomalyStats(BaseModel):
    checked_at: str
    last_hour_events: int
    hourly_avg_7d: float
    threshold: float
    anomalies_detected: bool
    anomalies: list[AnomalyEntry]


@router.get("/audit/anomalies", response_model=AnomalyStats)
async def get_anomaly_stats(
    threshold: float = Query(default=3.0, ge=1.0, le=100.0),
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Art. 33 GDPR — breach notification base: surface anomalous activity patterns."""
    svc = AuditService(db)
    return await svc.get_anomaly_stats(tenant_id=api_key.tenant_id, threshold=threshold)
