from __future__ import annotations

from pydantic import BaseModel


class DocumentAnonymizeResponse(BaseModel):
    content_type: str
    document_base64: str
    pages: int
    regions: list[dict[str, object]]
    safe: bool
    plugin: str
