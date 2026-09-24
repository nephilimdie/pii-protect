from __future__ import annotations

import asyncio
import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from app.anonymization.anonymizer import PiiAnonymizer
from app.config import settings
from app.detection.entities import PiiEntity
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.identity.tenant import get_tenant_id
from app.plugins.registry import plugin_registry
from app.routers._anonymize_logic import get_anonymizer
from app.routers.document_request import DocumentAnonymizeRequest
from app.routers.document_response import DocumentAnonymizeResponse

router = APIRouter()
logger = logging.getLogger(__name__)
_CONTENT_TYPES = {"application/pdf"}


@router.post("/anonymize/document", response_model=DocumentAnonymizeResponse)
async def anonymize_document(
    body: DocumentAnonymizeRequest,
    context_id: str = Query("document-session"),
    context_type: str = Query("generic"),
    language: str = Query("it"),
    mode: str = Query("mask"),
    _api_key: ApiKey = Depends(require_service),
    tenant_id: str | None = Depends(get_tenant_id),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
) -> DocumentAnonymizeResponse:
    if body.content_type not in _CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="unsupported_document_type")
    try:
        payload = base64.b64decode(body.document_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_document_base64") from exc
    if len(payload) > settings.document_max_bytes:
        raise HTTPException(status_code=413, detail="document_too_large")

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
        result = await plugin_registry.anonymize_document(
            payload=payload,
            content_type=body.content_type,
            detect=detect,
            mode=mode,
            tenant_id=tenant_id,
            max_pixels=settings.image_max_pixels,
            max_pages=settings.document_max_pages,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Document plugin failed closed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="document_processing_unavailable") from exc
    if result is None:
        raise HTTPException(status_code=503, detail="document_plugin_not_installed")
    return DocumentAnonymizeResponse(
        content_type=result.content_type,
        document_base64=base64.b64encode(result.document).decode("ascii"),
        pages=result.pages,
        regions=result.regions,
        safe=True,
        plugin="plugin",
    )
