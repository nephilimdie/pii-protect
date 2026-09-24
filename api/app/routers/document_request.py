from __future__ import annotations

from pydantic import BaseModel


class DocumentAnonymizeRequest(BaseModel):
    document_base64: str
    content_type: str
