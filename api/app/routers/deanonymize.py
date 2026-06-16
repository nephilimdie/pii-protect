import time
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.anonymization.deanonymizer import PiiDeanonymizer
from app.mapping.repository import MappingRepository
from app.audit.audit_service import AuditService
from app.surrogates.policy_service import PolicyService
from app.usage.service import UsageService

router = APIRouter()


class DeanonymizeRequest(BaseModel):
    text: str
    context_id: str
    context_type: str


class DeanonymizeResponse(BaseModel):
    restored_text: str


@router.post("/deanonymize", response_model=DeanonymizeResponse)
async def deanonymize(
    body: DeanonymizeRequest,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
):
    started_at = time.perf_counter()
    request_id = uuid.uuid4()
    usage_service = UsageService(db)
    await usage_service.ensure_within_limits(api_key, len(body.text))
    policy = await PolicyService(db).resolve(body.context_type, None, None)

    repo = MappingRepository(db)
    mappings = await repo.find_by_context(body.context_id, body.context_type)

    restored = PiiDeanonymizer().deanonymize(body.text, mappings)

    audit = AuditService(db)
    await audit.log(
        api_key_id=api_key.id,
        action="deanonymize",
        context_id=body.context_id,
        char_count=len(body.text),
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
        )
    except Exception:
        pass

    return DeanonymizeResponse(restored_text=restored)
