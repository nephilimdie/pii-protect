from __future__ import annotations
from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings, Settings
from app.database import get_db
from app.identity.api_key_service import ApiKeyService
from app.identity.models import ApiKey


async def get_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
    x_pii_tenant_id: str | None = Header(None, alias="X-Pii-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ApiKey:
    if x_api_key is None:
        raise HTTPException(status_code=401, detail="missing_api_key")
    service = ApiKeyService(db)
    api_key = await service.verify(x_api_key)
    if api_key is None:
        raise HTTPException(status_code=401, detail="invalid_api_key")
    # Internal key + tenant header model: when a key has no tenant_id and
    # the tenant header is accepted, use the header value as the tenant context.
    if (
        api_key.tenant_id is None
        and settings.accept_tenant_header
        and x_pii_tenant_id
    ):
        # Detach from session before mutating so SQLAlchemy doesn't track the change.
        db.expunge(api_key)
        api_key.tenant_id = x_pii_tenant_id
    return api_key


async def require_service(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    if api_key.role not in ("service", "admin"):
        raise HTTPException(status_code=403, detail="insufficient_role")
    return api_key


async def require_admin(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    if api_key.role != "admin":
        raise HTTPException(status_code=403, detail="insufficient_role")
    return api_key


async def require_auditor(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    if api_key.role not in ("auditor", "admin"):
        raise HTTPException(status_code=403, detail="insufficient_role")
    return api_key
