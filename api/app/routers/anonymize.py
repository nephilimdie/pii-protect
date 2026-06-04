from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.detection.detector_registry import DetectorRegistry
from app.anonymization.anonymizer import PiiAnonymizer
from app.mapping.repository import MappingRepository
from app.audit.audit_service import AuditService

router = APIRouter()


class AnonymizeRequest(BaseModel):
    text: str
    context_id: str
    context_type: str


class EntityDetail(BaseModel):
    type: str
    value: str
    start: int
    end: int
    confidence: float
    replacement: str


class AnonymizeResponse(BaseModel):
    anonymized_text: str
    entity_count: int
    pii_types_found: list[str]
    entities: list[EntityDetail]


def get_registry(request: Request) -> DetectorRegistry:
    return request.app.state.registry


def get_denylist(request: Request) -> dict[str, set[str]]:
    return getattr(request.app.state, "denylist", {})


def get_anonymizer(
    registry: DetectorRegistry = Depends(get_registry),
    denylist: dict[str, set[str]] = Depends(get_denylist),
) -> PiiAnonymizer:
    return PiiAnonymizer(registry, denylist)


@router.post("/anonymize", response_model=AnonymizeResponse)
async def anonymize(
    body: AnonymizeRequest,
    api_key: ApiKey = Depends(require_service),
    db: AsyncSession = Depends(get_db),
    anonymizer: PiiAnonymizer = Depends(get_anonymizer),
):
    result = anonymizer.anonymize(body.text, body.context_id, body.context_type)

    repo = MappingRepository(db)
    await repo.save_many(result.mappings, body.context_id, body.context_type)

    pii_types = list({m.pii_type for m in result.mappings})
    audit = AuditService(db)
    await audit.log(
        api_key_id=api_key.id,
        action="anonymize",
        context_id=body.context_id,
        pii_types_found=pii_types,
        char_count=len(body.text),
    )

    entities = [
        EntityDetail(
            type=m.pii_type,
            value=m.original,
            start=m.start,
            end=m.end,
            confidence=round(m.score, 4),
            replacement=m.token,
        )
        for m in result.mappings
    ]

    return AnonymizeResponse(
        anonymized_text=result.anonymized_text,
        entity_count=len(result.mappings),
        pii_types_found=pii_types,
        entities=entities,
    )
