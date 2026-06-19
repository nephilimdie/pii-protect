from __future__ import annotations
from typing import Any

from pydantic import BaseModel, Field


class UpsertScopedConfigRequest(BaseModel):
    scope_type: str = "tenant"
    scope_key: str
    item_key: str | None = None
    action: str = "override"
    data: dict[str, Any] = Field(default_factory=dict)
