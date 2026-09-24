from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.plugins.registry import PluginRegistry
from app.plugins.marketplace import MarketplaceClient
from app.config import settings

router = APIRouter()


class PluginInfo(BaseModel):
    name: str
    version: str


class PluginAction(BaseModel):
    name: str


class MarketplaceInstall(BaseModel):
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


@router.get("/marketplace/plugins")
async def marketplace_plugins(
    api_key: ApiKey = Depends(require_admin),
) -> dict[str, list[dict[str, object]]]:
    client = _marketplace_client()
    entries = await client.catalog()
    return {"plugins": [entry.__dict__ for entry in entries]}


@router.post("/marketplace/plugins/install", status_code=status.HTTP_201_CREATED)
async def install_marketplace_plugin(
    body: MarketplaceInstall,
    api_key: ApiKey = Depends(require_admin),
) -> dict[str, str]:
    client = _marketplace_client()
    target = await client.install(body.name, settings.plugin_dir)
    return {"name": body.name, "path": str(target), "autoload": "restart_required"}


def _marketplace_client() -> MarketplaceClient:
    if not settings.marketplace_url:
        raise HTTPException(status_code=503, detail="marketplace_not_configured")
    public_key = settings.marketplace_public_key.encode() or None
    return MarketplaceClient(
        settings.marketplace_url,
        token=settings.marketplace_token,
        public_key=public_key,
        timeout=settings.marketplace_timeout_seconds,
        max_package_bytes=settings.marketplace_max_package_bytes,
    )
