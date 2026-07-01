from __future__ import annotations

from pydantic import BaseModel, Field

from app.routers._anonymize_models import MAX_TEXT_CHARS


class MaskRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_CHARS)
    context_type: str = "default"
    language: str | None = None
    policy: dict | None = None
    mask_char: str = Field(default="█", max_length=4)
    mask_style: str = "fill"  # "fill" | "label" | "partial"


class MaskedEntity(BaseModel):
    type: str
    start: int
    end: int
    value: str
    confidence: float


class MaskResponse(BaseModel):
    masked_text: str
    entity_count: int
    pii_types_found: list[str]
    entities: list[MaskedEntity]
