from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin, get_api_key
from app.identity.models import ApiKey
from app.identity.api_key_service import ApiKeyService
from app.audit.audit_service import AuditService
from app.config import Settings, get_settings
from datetime import datetime

router = APIRouter()


@router.get("/me")
async def me(api_key: ApiKey = Depends(get_api_key)):
    """Validate the current API key and return its metadata. Useful for connection testing."""
    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "role": api_key.role,
        "tenant_id": str(api_key.tenant_id) if api_key.tenant_id else None,
        "can_anonymize": api_key.role in ("service", "admin"),
    }


class CreateKeyRequest(BaseModel):
    name: str
    role: str
    tenant_id: str | None = None
    max_requests_per_minute: int | None = None
    max_requests_per_hour: int | None = None
    max_requests_per_day: int | None = None
    max_chars_per_request: int | None = None
    max_chars_per_month: int | None = None
    expires_at: datetime | None = None


class CreateKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    key: str
    tenant_id: str | None = None
    max_requests_per_minute: int | None = None
    max_requests_per_hour: int | None = None
    max_requests_per_day: int | None = None
    max_chars_per_request: int | None = None
    max_chars_per_month: int | None = None
    expires_at: datetime | None = None


class ApiKeyListItem(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    active: bool
    tenant_id: str | None
    max_requests_per_minute: int | None
    max_requests_per_hour: int | None
    max_requests_per_day: int | None
    max_chars_per_request: int | None
    max_chars_per_month: int | None
    expires_at: datetime | None
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


def _strip_commercial_quota_if_self_hosted(
    body: CreateKeyRequest,
    settings: Settings = Depends(get_settings),
) -> CreateKeyRequest:
    """In self-hosted mode (MULTITENANCY_ENABLED=false) rate-limit quota fields
    are cloud-only: silently ignore any values supplied by the caller."""
    if not settings.multitenancy_enabled:
        body.max_requests_per_minute = None
        body.max_requests_per_hour = None
        body.max_requests_per_day = None
        body.max_chars_per_request = None
        body.max_chars_per_month = None
    return body


@router.post("/api-keys", response_model=CreateKeyResponse)
async def create_api_key(
    body: CreateKeyRequest = Depends(_strip_commercial_quota_if_self_hosted),
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in ("admin", "service", "auditor"):
        raise HTTPException(status_code=422, detail="invalid_role")

    # Tenant admins can only create keys for their own tenant.
    target_tenant_id = body.tenant_id
    if api_key.tenant_id is not None:
        if body.tenant_id is not None and body.tenant_id != api_key.tenant_id:
            raise HTTPException(status_code=403, detail="tenant_scope_violation")
        target_tenant_id = api_key.tenant_id

    service = ApiKeyService(db)
    created, plain_key = await service.create(
        name=body.name,
        role=body.role,
        tenant_id=target_tenant_id,
        max_requests_per_minute=body.max_requests_per_minute,
        max_requests_per_hour=body.max_requests_per_hour,
        max_requests_per_day=body.max_requests_per_day,
        max_chars_per_request=body.max_chars_per_request,
        max_chars_per_month=body.max_chars_per_month,
        expires_at=body.expires_at,
    )
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="api_key.create",
        context_id=str(created.id),
        tenant_id=target_tenant_id,
    )
    return CreateKeyResponse(
        id=created.id,
        name=created.name,
        role=created.role,
        key=plain_key,
        tenant_id=created.tenant_id,
        max_requests_per_minute=created.max_requests_per_minute,
        max_requests_per_hour=created.max_requests_per_hour,
        max_requests_per_day=created.max_requests_per_day,
        max_chars_per_request=created.max_chars_per_request,
        max_chars_per_month=created.max_chars_per_month,
        expires_at=created.expires_at,
    )


@router.get("/api-keys", response_model=list[ApiKeyListItem])
async def list_api_keys(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ApiKeyService(db)
    if api_key.tenant_id is not None:
        return await service.list_for_tenant(api_key.tenant_id)
    return await service.list_all()


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ApiKeyService(db)
    if api_key.tenant_id is not None:
        try:
            await service.revoke_for_tenant(key_id, api_key.tenant_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="key_not_found")
        await AuditService(db).log(
            api_key_id=api_key.id,
            action="api_key.revoke",
            context_id=str(key_id),
            tenant_id=api_key.tenant_id,
        )
        return

    await service.revoke(key_id)
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="api_key.revoke",
        context_id=str(key_id),
        tenant_id=api_key.tenant_id,
    )


@router.post("/api-keys/{key_id}/rotate", response_model=CreateKeyResponse)
async def rotate_api_key(
    key_id: uuid.UUID,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke key and issue a replacement with the same metadata. The new plaintext key is returned once."""
    service = ApiKeyService(db)
    try:
        new_key, plain = await service.rotate(key_id, tenant_id=api_key.tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="key_not_found")

    return CreateKeyResponse(
        id=new_key.id,
        name=new_key.name,
        role=new_key.role,
        key=plain,
        tenant_id=new_key.tenant_id,
        max_requests_per_minute=new_key.max_requests_per_minute,
        max_requests_per_hour=new_key.max_requests_per_hour,
        max_requests_per_day=new_key.max_requests_per_day,
        max_chars_per_request=new_key.max_chars_per_request,
        max_chars_per_month=new_key.max_chars_per_month,
        expires_at=new_key.expires_at,
    )
