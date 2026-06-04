import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.identity.api_key_service import ApiKeyService
from datetime import datetime

router = APIRouter()


class CreateKeyRequest(BaseModel):
    name: str
    role: str


class CreateKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    key: str


class ApiKeyListItem(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    active: bool
    created_at: datetime
    last_used_at: datetime | None

    class Config:
        from_attributes = True


@router.post("/api-keys", response_model=CreateKeyResponse)
async def create_api_key(
    body: CreateKeyRequest,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in ("admin", "service", "auditor"):
        raise HTTPException(status_code=422, detail="invalid_role")
    service = ApiKeyService(db)
    created, plain_key = await service.create(body.name, body.role)
    return CreateKeyResponse(id=created.id, name=created.name, role=created.role, key=plain_key)


@router.get("/api-keys", response_model=list[ApiKeyListItem])
async def list_api_keys(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ApiKeyService(db)
    return await service.list_all()


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ApiKeyService(db)
    await service.revoke(key_id)
