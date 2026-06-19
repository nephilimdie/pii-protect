from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, Settings
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.audit.audit_service import AuditService
from app.scoped_config.collections import ensure_collection
from app.scoped_config.scoped_config_response import ScopedConfigResponse
from app.scoped_config.service import ScopedConfigService
from app.scoped_config.upsert_request import UpsertScopedConfigRequest

router = APIRouter()


def require_multitenancy(settings: Settings = Depends(get_settings)) -> None:
    if not settings.multitenancy_enabled:
        raise HTTPException(status_code=404, detail="scoped_config_not_available_in_self_hosted_mode")


def authorize_scope(api_key: ApiKey, scope_type: str, scope_key: str) -> None:
    if scope_type not in ("tenant", "user"):
        raise HTTPException(status_code=422, detail="invalid_scope_type")
    if api_key.tenant_id is not None and (scope_type != "tenant" or scope_key != api_key.tenant_id):
        raise HTTPException(status_code=403, detail="scope_not_allowed")


@router.get("/scoped-config/{collection}", response_model=ScopedConfigResponse)
async def list_effective_config(
    collection: str,
    scope_type: str = Query("tenant"),
    scope_key: str = Query(...),
    q: str | None = Query(None),
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _mt: None = Depends(require_multitenancy),
):
    ensure_collection(collection)
    authorize_scope(api_key, scope_type, scope_key)
    items = await ScopedConfigService(db).effective_items(collection, scope_type, scope_key, q)

    return {"items": items}


@router.post("/scoped-config/{collection}")
async def create_scoped_config(
    collection: str,
    body: UpsertScopedConfigRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _mt: None = Depends(require_multitenancy),
):
    ensure_collection(collection)
    authorize_scope(api_key, body.scope_type, body.scope_key)

    return await ScopedConfigService(db).create(
        collection,
        body.scope_type,
        body.scope_key,
        body.action,
        body.data,
        body.item_key,
    )


@router.put("/scoped-config/{collection}/{item_key}")
async def update_scoped_config(
    collection: str,
    item_key: str,
    body: UpsertScopedConfigRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _mt: None = Depends(require_multitenancy),
):
    ensure_collection(collection)
    authorize_scope(api_key, body.scope_type, body.scope_key)

    result = await ScopedConfigService(db).upsert(
        collection,
        item_key,
        body.scope_type,
        body.scope_key,
        body.action,
        body.data,
    )
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="config.update",
        context_id=f"{collection}/{item_key}",
        tenant_id=body.scope_key if body.scope_type == "tenant" else None,
    )
    return result


@router.delete("/scoped-config/{collection}/{item_key}")
async def hide_scoped_config(
    collection: str,
    item_key: str,
    scope_type: str = Query("tenant"),
    scope_key: str = Query(...),
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _mt: None = Depends(require_multitenancy),
):
    ensure_collection(collection)
    authorize_scope(api_key, scope_type, scope_key)

    result = await ScopedConfigService(db).hide(collection, item_key, scope_type, scope_key)
    await AuditService(db).log(
        api_key_id=api_key.id,
        action="config.delete",
        context_id=f"{collection}/{item_key}",
        tenant_id=scope_key if scope_type == "tenant" else None,
    )
    return result
