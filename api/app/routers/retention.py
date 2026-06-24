from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit_service import AuditService
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.mapping.repository import MappingRepository
from app.mapping.key_provider import KeyProvider
from app.mapping.dependencies import get_key_provider
from app.settings_repository import SettingsRepository
from app.usage.models import UsageEvent

router = APIRouter()

_DEFAULTS = {
    "mapping_ttl_days":        "30",
    "audit_log_ttl_days":      "365",
    "usage_event_ttl_days":    "395",
    "ip_anonymization_enabled": "true",
}


class RetentionSettings(BaseModel):
    mapping_ttl_days:         int  = Field(default=30,  ge=1,  le=3650)
    audit_log_ttl_days:       int  = Field(default=365, ge=1,  le=3650)
    usage_event_ttl_days:     int  = Field(default=395, ge=1,  le=3650)
    ip_anonymization_enabled: bool = Field(default=True)


class CleanupResult(BaseModel):
    mappings_deleted:     int
    audit_logs_deleted:   int
    usage_events_deleted: int
    ran_at:               datetime


class ErasureRequest(BaseModel):
    context_id: str = Field(..., min_length=1)


class ErasureResult(BaseModel):
    context_id:       str
    mappings_deleted: int
    audit_logs_deleted: int


class ExportResult(BaseModel):
    context_id:       str
    page:             int
    per_page:         int
    total_mappings:   int
    total_audit_logs: int
    mappings:         list[dict]
    audit_logs:       list[dict]
    exported_at:      str


async def _load(repo: SettingsRepository) -> RetentionSettings:
    all_settings = await repo.all()
    return RetentionSettings(
        mapping_ttl_days        = int(all_settings.get("mapping_ttl_days",        _DEFAULTS["mapping_ttl_days"])),
        audit_log_ttl_days      = int(all_settings.get("audit_log_ttl_days",      _DEFAULTS["audit_log_ttl_days"])),
        usage_event_ttl_days    = int(all_settings.get("usage_event_ttl_days",    _DEFAULTS["usage_event_ttl_days"])),
        ip_anonymization_enabled = all_settings.get("ip_anonymization_enabled",   _DEFAULTS["ip_anonymization_enabled"]) == "true",
    )


@router.get("/retention", response_model=RetentionSettings)
async def get_retention(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _load(SettingsRepository(db))


@router.put("/retention", response_model=RetentionSettings)
async def update_retention(
    body: RetentionSettings,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = SettingsRepository(db)
    await repo.set("mapping_ttl_days",         str(body.mapping_ttl_days))
    await repo.set("audit_log_ttl_days",       str(body.audit_log_ttl_days))
    await repo.set("usage_event_ttl_days",     str(body.usage_event_ttl_days))
    await repo.set("ip_anonymization_enabled", "true" if body.ip_anonymization_enabled else "false")
    request.app.state.ip_anonymization_enabled = body.ip_anonymization_enabled
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="retention_config_updated",
        tenant_id=api_key.tenant_id,
        event_category="admin",
        reason=(
            f"mapping_ttl={body.mapping_ttl_days}d "
            f"audit_ttl={body.audit_log_ttl_days}d "
            f"usage_ttl={body.usage_event_ttl_days}d "
            f"ip_anon={body.ip_anonymization_enabled}"
        ),
    )
    return body


@router.post("/retention/cleanup", response_model=CleanupResult)
async def run_cleanup(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    key_provider: KeyProvider = Depends(get_key_provider),
):
    repo = SettingsRepository(db)
    cfg = await _load(repo)
    tenant_id = api_key.tenant_id

    # Mappings
    mapping_repo = MappingRepository(db, key_provider)
    mappings_deleted = await mapping_repo.delete_expired(cfg.mapping_ttl_days, tenant_id=tenant_id)

    # Audit logs
    audit_svc = AuditService(db)
    audit_deleted = await audit_svc.delete_expired(cfg.audit_log_ttl_days, tenant_id=tenant_id)

    # Usage events
    cutoff = datetime.utcnow() - timedelta(days=cfg.usage_event_ttl_days)
    stmt = delete(UsageEvent).where(UsageEvent.created_at < cutoff)
    if tenant_id is not None:
        stmt = stmt.where(UsageEvent.tenant_id == tenant_id)
    result = await db.execute(stmt)
    await db.commit()
    usage_deleted = result.rowcount

    result = CleanupResult(
        mappings_deleted=mappings_deleted,
        audit_logs_deleted=audit_deleted,
        usage_events_deleted=usage_deleted,
        ran_at=datetime.utcnow(),
    )
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="cleanup_executed",
        tenant_id=tenant_id,
        event_category="admin",
        reason=(
            f"mappings={mappings_deleted} audit={audit_deleted} usage={usage_deleted}"
        ),
    )
    return result


@router.delete("/retention/erasure", response_model=ErasureResult)
async def erase_by_context(
    body: ErasureRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Art. 17 GDPR — right to erasure: delete all data tied to a context_id."""
    tenant_id = api_key.tenant_id

    from app.mapping.models import PiiMapping
    from app.audit.models import AuditLog

    # Delete mappings for this context
    m_stmt = delete(PiiMapping).where(PiiMapping.context_id == body.context_id)
    if tenant_id is not None:
        m_stmt = m_stmt.where(PiiMapping.tenant_id == tenant_id)
    m_result = await db.execute(m_stmt)

    # Delete audit logs for this context, but preserve admin-category records
    # (e.g. prior erasure_executed entries) so the GDPR audit trail survives re-erasure.
    a_stmt = delete(AuditLog).where(
        AuditLog.context_id == body.context_id,
        AuditLog.event_category != "admin",
    )
    if tenant_id is not None:
        a_stmt = a_stmt.where(AuditLog.tenant_id == tenant_id)
    a_result = await db.execute(a_stmt)

    await db.commit()

    await AuditService(db).log(
        api_key_id=api_key.id,
        action="erasure_executed",
        context_id=body.context_id,
        tenant_id=tenant_id,
        event_category="admin",
        reason=f"mappings={m_result.rowcount} audit_logs={a_result.rowcount}",
    )
    return ErasureResult(
        context_id=body.context_id,
        mappings_deleted=m_result.rowcount,
        audit_logs_deleted=a_result.rowcount,
    )


@router.get("/retention/export")
async def export_by_context(
    context_id: str = Query(..., min_length=1),
    format: str = Query(default="json", pattern="^(json|csv)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=100, ge=1, le=500),
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    key_provider: KeyProvider = Depends(get_key_provider),
):
    """Art. 20 GDPR — data portability: export paginated data for a context_id as JSON or CSV."""
    tenant_id = api_key.tenant_id
    offset = (page - 1) * per_page

    mappings, total_mappings = await MappingRepository(db, key_provider).find_all_by_context_id(
        context_id, tenant_id, offset=offset, limit=per_page,
    )
    audit_entries, total_audit_logs = await AuditService(db).find_by_context(
        context_id, tenant_id, offset=offset, limit=per_page,
    )
    audit_data = [
        {
            "id": str(entry.id),
            "action": entry.action,
            "pii_types_found": entry.pii_types_found,
            "event_category": entry.event_category,
            "reason": entry.reason,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in audit_entries
    ]

    await AuditService(db).log(
        api_key_id=api_key.id,
        action="export_accessed",
        context_id=context_id,
        tenant_id=tenant_id,
        event_category="admin",
        reason=f"page={page} per_page={per_page}",
    )

    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["section", "id", "token_or_action", "pii_type_or_types", "context_type_or_category", "created_at"])
        for m in mappings:
            w.writerow(["mapping", m["id"], m["token"], m["pii_type"], m["context_type"], m["created_at"]])
        for a in audit_data:
            types_str = ",".join(a["pii_types_found"] or [])
            w.writerow(["audit", a["id"], a["action"], types_str, a["event_category"], a["created_at"]])
        headers = {
            "Content-Disposition": f'attachment; filename="gdpr_export_{context_id}_p{page}.csv"',
            "X-Total-Mappings": str(total_mappings),
            "X-Total-Audit-Logs": str(total_audit_logs),
            "X-Page": str(page),
            "X-Per-Page": str(per_page),
        }
        return Response(content=buf.getvalue(), media_type="text/csv", headers=headers)

    return ExportResult(
        context_id=context_id,
        page=page,
        per_page=per_page,
        total_mappings=total_mappings,
        total_audit_logs=total_audit_logs,
        mappings=mappings,
        audit_logs=audit_data,
        exported_at=datetime.utcnow().isoformat(),
    )
