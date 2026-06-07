from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.detection.reclassification_repository import ReclassificationRepository
from app.anonymization.anonymizer import set_reclassify_rules

router = APIRouter()


class RuleResponse(BaseModel):
    id: str
    from_type: str
    to_type: str | None
    context_pattern: str | None
    entity_pattern: str | None
    context_window: int
    description: str
    enabled: bool
    created_at: datetime


class CreateRuleRequest(BaseModel):
    from_type: str
    to_type: str | None = None
    context_pattern: str | None = None
    entity_pattern: str | None = None
    context_window: int = 60
    description: str = ""


class UpdateRuleRequest(BaseModel):
    from_type: str | None = None
    to_type: str | None = None
    context_pattern: str | None = None
    entity_pattern: str | None = None
    context_window: int | None = None
    description: str | None = None
    enabled: bool | None = None


async def _reload(request: Request, db: AsyncSession) -> None:
    repo = ReclassificationRepository(db)
    rules = await repo.find_enabled()
    set_reclassify_rules(rules)
    request.app.state.reclassification_rules = rules


@router.get("/reclassification-rules", response_model=list[RuleResponse])
async def list_rules(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await ReclassificationRepository(db).find_all()


@router.post("/reclassification-rules", response_model=RuleResponse)
async def create_rule(
    body: CreateRuleRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = ReclassificationRepository(db)
    row = await repo.create(
        body.from_type, body.to_type, body.context_pattern,
        body.entity_pattern, body.context_window, body.description,
    )
    await _reload(request, db)
    return row


@router.put("/reclassification-rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: str,
    body: UpdateRuleRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    row = await ReclassificationRepository(db).update(rule_id, **updates)
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    await _reload(request, db)
    return row


@router.delete("/reclassification-rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    deleted = await ReclassificationRepository(db).delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")
    await _reload(request, db)
