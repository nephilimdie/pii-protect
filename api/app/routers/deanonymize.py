from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_service
from app.identity.models import ApiKey
from app.anonymization.deanonymizer import PiiDeanonymizer
from app.mapping.repository import MappingRepository
from app.audit.audit_service import AuditService

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

    return DeanonymizeResponse(restored_text=restored)
