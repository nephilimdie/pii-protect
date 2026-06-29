from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.tenant import get_tenant_id
from app.identity.models import ApiKey
from app.anonymization.anonymizer import PiiAnonymizer
from app.audit.audit_service import AuditService
from app.usage.service import UsageService
from app.routers._anonymize_logic import (
    get_anonymizer,
    _client_ip,
    _document_hash,
    run_detection,
    filter_detected_entities,
)
from app.routers._detect_models import DetectRequest, DetectResponse, DetectedEntity

router = APIRouter()


@router.post("/detect", response_model=DetectResponse)
async def detect(
    body: DetectRequest,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
    tenant_id: str | None = Depends(get_tenant_id),
):
    lang = body.language or getattr(request.app.state, "default_language", "it")
    request_id = uuid.uuid4()
    started_at = time.perf_counter()
    usage_service = UsageService(db)

    await usage_service.ensure_within_limits(api_key, len(body.text))

    entities = await run_detection(
        anonymizer=anonymizer,
        text=body.text,
        context_id=str(request_id),
        context_type=body.context_type,
        language=lang,
    )

    # Optional policy-based filtering (same protect/keep semantics as /anonymize)
    if body.policy:
        protect = body.policy.get("protect")
        entities = filter_detected_entities(
            entities=entities,
            keep_types=set(body.policy.get("keep") or []),
            protect_types=set(protect) if protect is not None else None,
        )

    pii_types = sorted({e.pii_type for e in entities})
    entities_out = [
        DetectedEntity(
            type=e.pii_type,
            start=e.start,
            end=e.end,
            value=e.text,
            confidence=round(e.score, 4),
        )
        for e in sorted(entities, key=lambda e: e.start)
    ]

    ip_anon = getattr(request.app.state, "ip_anonymization_enabled", True)
    audit = AuditService(db, ip_anonymization=ip_anon)
    await audit.log(
        api_key_id=api_key.id,
        action="detect",
        context_id=str(request_id),
        pii_types_found=pii_types,
        char_count=len(body.text),
        tenant_id=tenant_id,
        document_hash=_document_hash(body.text),
        ip=_client_ip(request),
    )

    try:
        await usage_service.record(
            api_key_id=api_key.id,
            request_id=request_id,
            policy_id=body.context_type,
            policy_version=None,
            policy_hash=None,
            chars_in=len(body.text),
            chars_out=0,
            entities_count=len(entities_out),
            entity_types_summary=pii_types,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            status="ok",
            tenant_id=tenant_id,
        )
    except Exception:
        pass

    return DetectResponse(
        entity_count=len(entities_out),
        pii_types_found=pii_types,
        entities=entities_out,
    )
