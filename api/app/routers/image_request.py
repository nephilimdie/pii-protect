from __future__ import annotations

from pydantic import BaseModel


class ImageAnonymizeRequest(BaseModel):
    image_base64: str
    content_type: str
