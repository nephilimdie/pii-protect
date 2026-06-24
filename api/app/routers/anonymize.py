from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.tenant import get_tenant_id
from app.identity.models import ApiKey
from app.config import settings
from app.anonymization.anonymizer import PiiAnonymizer
from app.routers._anonymize_models import (
    AnonymizeRequest,
    AnonymizeResponse,
    BatchAnonymizeRequest,
    BatchAnonymizeResponse,
    BatchItemRequest,
    BatchItemResult,
    EntityDetail,
    PolicyMetadata,
)
from app.mapping.key_provider import KeyProvider
from app.mapping.dependencies import get_key_provider
from app.routers._anonymize_logic import (
    get_anonymizer,
    get_registry,
    _process_anonymization,
)

router = APIRouter()


@router.post("/anonymize", response_model=AnonymizeResponse, response_model_exclude_none=True)
async def anonymize(
    body: AnonymizeRequest,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
    tenant_id: str | None = Depends(get_tenant_id),
    key_provider: KeyProvider = Depends(get_key_provider),
):
    return await _process_anonymization(body, request, api_key, db, anonymizer, tenant_id, key_provider)


@router.post("/anonymize/batch", response_model=BatchAnonymizeResponse)
async def anonymize_batch(
    body: BatchAnonymizeRequest,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
    tenant_id: str | None = Depends(get_tenant_id),
    key_provider: KeyProvider = Depends(get_key_provider),
):
    if len(body.items) > settings.batch_max_items:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "BATCH_LIMIT_EXCEEDED",
                "message": f"Batch requests are limited to {settings.batch_max_items} items.",
            },
        )

    results: list[BatchItemResult] = []
    for item in body.items:
        try:
            item_body = AnonymizeRequest.model_validate({
                "text": item.text,
                "context_id": item.id,
                "context_type": item.context_type or body.context_type,
                "language": item.language or body.language,
                "mode": item.mode or body.mode,
                "policy": item.policy or body.policy,
                "dry_run": body.dry_run if item.dry_run is None else item.dry_run,
            })
            response = await _process_anonymization(item_body, request, api_key, db, anonymizer, tenant_id, key_provider)
            results.append(
                BatchItemResult(
                    id=item.id,
                    status="processed",
                    output=response.anonymized_text,
                    warnings=response.warnings,
                )
            )
        except HTTPException as exc:
            results.append(BatchItemResult(id=item.id, status="failed", error_code=str(exc.detail)))
    return BatchAnonymizeResponse(items=results)
