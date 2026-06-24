from __future__ import annotations
import hashlib
import time
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.tenant import get_tenant_id
from app.identity.models import ApiKey
from app.anonymization.deanonymizer import PiiDeanonymizer
from app.mapping.repository import MappingRepository
from app.mapping.key_provider import KeyProvider
from app.mapping.dependencies import get_key_provider
from app.audit.audit_service import AuditService
from app.surrogates.policy_service import PolicyService
from app.usage.service import UsageService

router = APIRouter()


class DeanonymizeRequest(BaseModel):
    text: str
    context_id: str
    context_type: str
    reason: str | None = None


class DeanonymizeResponse(BaseModel):
    restored_text: str


@router.post("/deanonymize", response_model=DeanonymizeResponse)
async def deanonymize(
    body: DeanonymizeRequest,
    request: Request,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    tenant_id: str | None = Depends(get_tenant_id),
    key_provider: KeyProvider = Depends(get_key_provider),
):
    started_at = time.perf_counter()
    request_id = uuid.uuid4()
    usage_service = UsageService(db)
    await usage_service.ensure_within_limits(api_key, len(body.text))
    policy = await PolicyService(db, tenant_id=tenant_id).resolve(body.context_type, None, None)

    repo = MappingRepository(db, key_provider)
    mappings = await repo.find_by_context(body.context_id, body.context_type, tenant_id)

    restored = PiiDeanonymizer().deanonymize(body.text, mappings)

    audit = AuditService(db)
    await audit.log(
        api_key_id=api_key.id,
        action="deanonymize",
        context_id=body.context_id,
        char_count=len(body.text),
        tenant_id=tenant_id,
        document_hash=hashlib.sha256(body.text.encode("utf-8")).hexdigest(),
        ip=request.client.host if request.client else None,
        reason=body.reason,
    )

    policy_hash = policy["policy_hash"]
    try:
        await usage_service.record(
            api_key_id=api_key.id,
            request_id=request_id,
            policy_id=policy["policy_id"],
            policy_version=policy["policy_version"],
            policy_hash=policy_hash,
            chars_in=len(body.text),
            chars_out=len(restored),
            entities_count=len(mappings),
            entity_types_summary=sorted({m.pii_type for m in mappings}),
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            status="ok",
            tenant_id=tenant_id,
        )
    except Exception:
        pass

    return DeanonymizeResponse(restored_text=restored)
