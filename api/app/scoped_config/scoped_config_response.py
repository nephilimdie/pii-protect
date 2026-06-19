from typing import Any

from pydantic import BaseModel


class ScopedConfigResponse(BaseModel):
    items: list[dict[str, Any]]
