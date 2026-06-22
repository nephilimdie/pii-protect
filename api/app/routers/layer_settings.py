"""GET/PUT/DELETE /v1/admin/layer-settings — per-tenant ML layer configuration."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.detection import layer_config as lc
from app.detection.layer_settings_repository import LayerSettingsRepository
from app.identity.dependencies import require_admin
from app.identity.tenant import get_tenant_id

router = APIRouter()


class LayerConfigIn(BaseModel):
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    min_chars: int | None = Field(default=None, ge=0, le=100_000)
    enabled_types: list[str] | None = None
    location_enabled: bool | None = None

    @model_validator(mode="after")
    def at_least_one(self) -> "LayerConfigIn":
        if all(v is None for v in [self.min_score, self.min_chars, self.enabled_types, self.location_enabled]):
            raise ValueError("Provide at least one field to update")
        return self


def _to_storable(layer: str, body: LayerConfigIn) -> dict:
    """Build a partial dict with only the fields that are valid for this layer."""
    allowed = set(lc.SCHEMA.get(layer, []))
    out: dict[str, Any] = {}
    if "min_score" in allowed and body.min_score is not None:
        out["min_score"] = body.min_score
    if "min_chars" in allowed and body.min_chars is not None:
        out["min_chars"] = body.min_chars
    if "enabled_types" in allowed and body.enabled_types is not None:
        out["enabled_types"] = body.enabled_types
    if "location_enabled" in allowed and body.location_enabled is not None:
        out["location_enabled"] = body.location_enabled
    return out


@router.get("/layer-settings")
async def get_layer_settings(
    db: AsyncSession = Depends(get_db),
    tenant_id: str | None = Depends(get_tenant_id),
    _admin: None = Depends(require_admin),
) -> dict:
    repo = LayerSettingsRepository(db)
    global_rows = await repo.get_all_global()
    tenant_rows = await repo.get_all_tenant(tenant_id) if tenant_id else {}

    layers = {}
    for layer in lc.ALL_LAYERS:
        defaults = lc.DEFAULTS[layer]
        global_override = global_rows.get(layer)
        tenant_override = tenant_rows.get(layer)
        effective = lc.effective(layer, tenant_override, global_override)
        layers[layer] = {
            "defaults": defaults,
            "global_override": global_override,
            "tenant_override": tenant_override,
            "effective": effective,
            "schema": lc.SCHEMA[layer],
            "all_types": lc.ALL_TYPES[layer],
        }
    return {"ok": True, "data": layers}


@router.put("/layer-settings/{layer}")
async def put_layer_settings(
    layer: str,
    body: LayerConfigIn,
    scope: str = "tenant",
    db: AsyncSession = Depends(get_db),
    tenant_id: str | None = Depends(get_tenant_id),
    _admin: None = Depends(require_admin),
) -> dict:
    if layer not in lc.ALL_LAYERS:
        raise HTTPException(status_code=404, detail=f"Unknown layer: {layer}")

    storable = _to_storable(layer, body)
    if not storable:
        raise HTTPException(status_code=422, detail="No valid fields for this layer")

    target_tenant = tenant_id if scope == "tenant" else None
    repo = LayerSettingsRepository(db)
    await repo.upsert(target_tenant, layer, storable)
    return {"ok": True, "data": storable}


@router.delete("/layer-settings/{layer}")
async def delete_layer_settings(
    layer: str,
    scope: str = "tenant",
    db: AsyncSession = Depends(get_db),
    tenant_id: str | None = Depends(get_tenant_id),
    _admin: None = Depends(require_admin),
) -> dict:
    if layer not in lc.ALL_LAYERS:
        raise HTTPException(status_code=404, detail=f"Unknown layer: {layer}")

    target_tenant = tenant_id if scope == "tenant" else None
    repo = LayerSettingsRepository(db)
    deleted = await repo.delete(target_tenant, layer)
    return {"ok": True, "deleted": deleted}
