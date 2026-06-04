import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.detection.models import DenylistEntry
from app.detection.denylist_repository import DenylistRepository

router = APIRouter()


class DenylistEntryResponse(BaseModel):
    id: uuid.UUID
    pii_type: str
    value: str
    match_type: str
    description: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CreateDenylistEntryRequest(BaseModel):
    pii_type: str
    value: str
    match_type: str = "exact_word"  # "exact_word" | "contains"
    description: str = ""


class UpdateDenylistEntryRequest(BaseModel):
    pii_type: str | None = None
    value: str | None = None
    match_type: str | None = None
    description: str | None = None
    enabled: bool | None = None


async def _reload(request: Request, db: AsyncSession) -> None:
    repo = DenylistRepository(db)
    entries = await repo.find_enabled()
    # denylist structure: {pii_type: {"exact": set[str], "contains": list[str]}}
    denylist: dict[str, dict] = {}
    for e in entries:
        bucket = denylist.setdefault(e.pii_type, {"exact": set(), "contains": []})
        if e.match_type == "contains":
            bucket["contains"].append(e.value.lower())
        else:
            bucket["exact"].add(e.value.lower())
    request.app.state.denylist = denylist


@router.get("/denylist", response_model=list[DenylistEntryResponse])
async def list_entries(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await DenylistRepository(db).find_all()


@router.post("/denylist", response_model=DenylistEntryResponse)
async def create_entry(
    body: CreateDenylistEntryRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    entry = DenylistEntry(
        id=uuid.uuid4(),
        pii_type=body.pii_type,
        value=body.value.lower().strip(),
        match_type=body.match_type,
        description=body.description,
        enabled=True,
    )
    saved = await DenylistRepository(db).save(entry)
    await _reload(request, db)
    return saved


@router.put("/denylist/{entry_id}", response_model=DenylistEntryResponse)
async def update_entry(
    entry_id: uuid.UUID,
    body: UpdateDenylistEntryRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = DenylistRepository(db)
    entry = await repo.find_by_id(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="not_found")
    if body.pii_type is not None:
        entry.pii_type = body.pii_type
    if body.value is not None:
        entry.value = body.value.lower().strip()
    if body.match_type is not None:
        entry.match_type = body.match_type
    if body.description is not None:
        entry.description = body.description
    if body.enabled is not None:
        entry.enabled = body.enabled
    saved = await repo.save(entry)
    await _reload(request, db)
    return saved


@router.delete("/denylist/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: uuid.UUID,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = DenylistRepository(db)
    entry = await repo.find_by_id(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="not_found")
    await repo.delete(entry)
    await _reload(request, db)
