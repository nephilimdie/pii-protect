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


@router.get("/stats")
async def get_stats(
    api_key: ApiKey = Depends(require_auditor),
    db: AsyncSession = Depends(get_db),
):
    service = StatsService(db)
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
    items, total = await service.list_paginated(page, per_page, action)
    return AuditLogResponse(items=items, total=total, page=page)


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup(
    body: CleanupRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = MappingRepository(db)
    deleted = await repo.delete_expired(body.ttl_days)
    return CleanupResponse(deleted_count=deleted)
