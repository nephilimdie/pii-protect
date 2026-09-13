from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.plugins.registry import PluginRegistry

router = APIRouter()


class PluginInfo(BaseModel):
    name: str
    version: str


class PluginAction(BaseModel):
    name: str


@router.get("/plugins", response_model=list[PluginInfo])
async def list_plugins(
    api_key: ApiKey = Depends(require_admin),
) -> list[PluginInfo]:
    return [PluginInfo(**p.metadata()) for p in PluginRegistry.all()]


@router.post("/plugins/disable", response_model=dict[str, bool])
async def disable_plugin(
    body: PluginAction,
    api_key: ApiKey = Depends(require_admin),
) -> dict[str, bool]:
    if not PluginRegistry.unregister(body.name):
        raise HTTPException(status_code=404, detail="plugin_not_found")
    return {"disabled": True}
