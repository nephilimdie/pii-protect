import uuid
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.detection.models import RegexPattern
from app.detection.regex_pattern_repository import RegexPatternRepository
from app.detection.layers.regex_layer import ItalianRegexDetector

router = APIRouter()


class PatternResponse(BaseModel):
    id: uuid.UUID
    pii_type: str
    pattern: str
    flags: str
    capture_group: int
    description: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CreatePatternRequest(BaseModel):
    pii_type: str
    pattern: str
    flags: str = ""
    capture_group: int = 0
    description: str = ""

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex: {e}")
        return v


class UpdatePatternRequest(BaseModel):
    pii_type: str | None = None
    pattern: str | None = None
    flags: str | None = None
    capture_group: int | None = None
    description: str | None = None
    enabled: bool | None = None

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex: {e}")
        return v


async def _reload(request: Request, db: AsyncSession) -> None:
    repo = RegexPatternRepository(db)
    patterns = await repo.find_enabled()
    detector = request.app.state.regex_detector
    if isinstance(detector, ItalianRegexDetector):
        detector.reload(patterns)


@router.get("/regex-patterns", response_model=list[PatternResponse])
async def list_patterns(
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await RegexPatternRepository(db).find_all()


@router.post("/regex-patterns", response_model=PatternResponse)
async def create_pattern(
    body: CreatePatternRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    pattern = RegexPattern(
        id=uuid.uuid4(),
        pii_type=body.pii_type,
        pattern=body.pattern,
        flags=body.flags,
        capture_group=body.capture_group,
        description=body.description,
        enabled=True,
    )
    repo = RegexPatternRepository(db)
    saved = await repo.save(pattern)
    await _reload(request, db)
    return saved


@router.put("/regex-patterns/{pattern_id}", response_model=PatternResponse)
async def update_pattern(
    pattern_id: uuid.UUID,
    body: UpdatePatternRequest,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = RegexPatternRepository(db)
    pattern = await repo.find_by_id(pattern_id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="not_found")

    if body.pii_type is not None:
        pattern.pii_type = body.pii_type
    if body.pattern is not None:
        pattern.pattern = body.pattern
    if body.flags is not None:
        pattern.flags = body.flags
    if body.capture_group is not None:
        pattern.capture_group = body.capture_group
    if body.description is not None:
        pattern.description = body.description
    if body.enabled is not None:
        pattern.enabled = body.enabled

    saved = await repo.save(pattern)
    await _reload(request, db)
    return saved


@router.delete("/regex-patterns/{pattern_id}", status_code=204)
async def delete_pattern(
    pattern_id: uuid.UUID,
    request: Request,
    api_key: ApiKey = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = RegexPatternRepository(db)
    pattern = await repo.find_by_id(pattern_id)
    if pattern is None:
        raise HTTPException(status_code=404, detail="not_found")
    await repo.delete(pattern)
    await _reload(request, db)
