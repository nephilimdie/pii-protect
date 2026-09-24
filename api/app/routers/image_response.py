from __future__ import annotations

from pydantic import BaseModel


class ImageAnonymizeResponse(BaseModel):
    content_type: str
    image_base64: str
    regions: list[dict[str, object]]
    safe: bool
    plugin: str
