from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.detection.presidio_context_repository import PresidioContextRepository
from app.detection.layers.presidio_layer import PresidioDetector

router = APIRouter()


class ContextWordResponse(BaseModel):
    id: int
    entity_type: str
    word: str
    description: str
    enabled: bool
    created_at: datetime


class CreateContextWordRequest(BaseModel):
    entity_type: str
    word: str
    description: str = ""


class UpdateContextWordRequest(BaseModel):
    entity_type: str | None = None
    word: str | None = None
    description: str | None = None
    enabled: bool | None = None


async def _reload_context(request: Request, db: AsyncSession) -> None:
    repo = PresidioContextRepository(db)
    entries = await repo.find_enabled()
    context_map: dict[str, list[str]] = {}
    for e in entries:
        context_map.setdefault(e["entity_type"], []).append(e["word"])
    request.app.state.presidio_context = context_map
    PresidioDetector.set_context(context_map)


@router.get("/presidio-context", response_model=list[ContextWordResponse])
async def list_context_words(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PresidioContextRepository(db).find_all()


@router.post("/presidio-context", response_model=ContextWordResponse)
async def create_context_word(
    body: CreateContextWordRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await PresidioContextRepository(db).create(body.entity_type, body.word, body.description)
    await _reload_context(request, db)
    return row


@router.put("/presidio-context/{entry_id}", response_model=ContextWordResponse)
async def update_context_word(
    entry_id: int,
    body: UpdateContextWordRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "word" in updates:
        updates["word"] = updates["word"].lower().strip()
    row = await PresidioContextRepository(db).update(entry_id, **updates)
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    await _reload_context(request, db)
    return row


@router.delete("/presidio-context/{entry_id}", status_code=204)
async def delete_context_word(
    entry_id: int,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    deleted = await PresidioContextRepository(db).delete(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not_found")
    await _reload_context(request, db)
