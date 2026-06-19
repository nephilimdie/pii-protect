from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.plugins.registry import PluginRegistry

router = APIRouter()


class PluginInfo(BaseModel):
    name: str
    version: str


@router.get("/plugins", response_model=list[PluginInfo])
async def list_plugins(
    api_key: ApiKey = Depends(require_admin),
) -> list[PluginInfo]:
    return [PluginInfo(**p.metadata()) for p in PluginRegistry.all()]
