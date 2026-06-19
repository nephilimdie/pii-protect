from __future__ import annotations

from pydantic import BaseModel, Field

MAX_TEXT_CHARS = 500_000  # ~400 pages; hard limit enforced before ML layers


class AnonymizeRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT_CHARS)
    context_id: str
    context_type: str
    language: str | None = None
    mode: str | None = None          # tag | surrogate — overrides context_type default
    policy: dict | None = None       # {"protect": [...], "keep": [...]} — inline override
    detection_mode: str = "permissive"  # permissive | strict
    include_entity_values: bool = False
    dry_run: bool = False


class PolicyMetadata(BaseModel):
    id: str | None = None
    version: str | None = None
    hash: str | None = None


class EntityDetail(BaseModel):
    type: str
    start: int
    end: int
    confidence: float
    replacement: str
    value: str | None = None


class AnonymizeResponse(BaseModel):
    anonymized_text: str
    entity_count: int
    pii_types_found: list[str]
    entities: list[EntityDetail]
    mode: str
    policy: PolicyMetadata
    safe: bool = True
    dry_run: bool = False
    warnings: list[str] | None = None


class BatchItemResult(BaseModel):
    id: str
    status: str
    output: str | None = None
    error_code: str | None = None
    warnings: list[str] | None = None


class BatchItemRequest(BaseModel):
    id: str
    text: str = Field(max_length=MAX_TEXT_CHARS)
    context_type: str | None = None
    language: str | None = None
    mode: str | None = None
    policy: dict | None = None
    dry_run: bool | None = None


class BatchAnonymizeRequest(BaseModel):
    items: list[BatchItemRequest]
    context_type: str = "default"
    language: str | None = None
    mode: str | None = None
    policy: dict | None = None
    dry_run: bool = True


class BatchAnonymizeResponse(BaseModel):
    items: list[BatchItemResult]
