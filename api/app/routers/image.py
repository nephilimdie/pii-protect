from __future__ import annotations

import asyncio
import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.anonymization.anonymizer import PiiAnonymizer
from app.config import settings
from app.detection.entities import PiiEntity
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.plugins.registry import plugin_registry
from app.routers._anonymize_logic import get_anonymizer
from app.identity.tenant import get_tenant_id

router = APIRouter()
_CONTENT_TYPES = {"image/jpeg", "image/png"}
logger = logging.getLogger(__name__)


class ImageAnonymizeResponse(BaseModel):
    content_type: str
    image_base64: str
    regions: list[dict[str, object]]
    safe: bool
    plugin: str


class ImageAnonymizeRequest(BaseModel):
    image_base64: str
    content_type: str


@router.post("/anonymize/image", response_model=ImageAnonymizeResponse)
async def anonymize_image(
    body: ImageAnonymizeRequest,
    context_id: str = Query("image-session"),
    context_type: str = Query("generic"),
    language: str = Query("it"),
    mode: str = Query("mask"),
    _api_key: ApiKey = Depends(require_service),
    tenant_id: str | None = Depends(get_tenant_id),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
) -> ImageAnonymizeResponse:
    if body.content_type not in _CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="unsupported_image_type")

    try:
        payload = base64.b64decode(body.image_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_image_base64") from exc
    if len(payload) > settings.image_max_bytes:
        raise HTTPException(status_code=413, detail="image_too_large")

    async def detect(text: str) -> list[PiiEntity]:
        result = await asyncio.to_thread(
            anonymizer.detect_only,
            text,
            context_id,
            context_type,
            language,
        )
        return result.entities

    try:
        result = await plugin_registry.anonymize_image(
            payload=payload,
            content_type=body.content_type,
            detect=detect,
            mode=mode,
            tenant_id=tenant_id,
            max_pixels=settings.image_max_pixels,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Image plugin failed closed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="image_processing_unavailable") from exc
    if result is None:
        raise HTTPException(status_code=503, detail="image_plugin_not_installed")

    return ImageAnonymizeResponse(
        content_type=result.content_type,
        image_base64=base64.b64encode(result.image).decode("ascii"),
        regions=result.regions,
        safe=True,
        plugin="plugin",
    )
