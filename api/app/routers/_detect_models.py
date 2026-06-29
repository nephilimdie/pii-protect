from __future__ import annotations

from pydantic import BaseModel, Field

from app.routers._anonymize_models import MAX_TEXT_CHARS


class DetectRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_CHARS)
    context_type: str = "default"
    language: str | None = None
    # Optional policy filter — same format as /anonymize {"protect": [...], "keep": [...]}
    # If omitted, all detected PII types are returned regardless of policy.
    policy: dict | None = None


class DetectedEntity(BaseModel):
    type: str
    start: int
    end: int
    value: str
    confidence: float


class DetectResponse(BaseModel):
    entity_count: int
    pii_types_found: list[str]
    entities: list[DetectedEntity]
