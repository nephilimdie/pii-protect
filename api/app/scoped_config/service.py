from __future__ import annotations
import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.scoped_config.collections import ensure_collection
from app.scoped_config.repository import ScopedConfigRepository


class ScopedConfigService:
    def __init__(self, db: AsyncSession) -> None:
        self._repository = ScopedConfigRepository(db)

    async def effective_items(
        self,
        collection: str,
        scope_type: str,
        scope_key: str,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        ensure_collection(collection)

        items = {item["_item_key"]: item for item in await self._repository.base_items(collection)}
        for override in await self._repository.overrides(collection, scope_type, scope_key):
            key = override["item_key"]
            if override["action"] == "hidden":
                items.pop(key, None)
                continue

            merged = {**items.get(key, {}), **(override["data"] or {})}
            merged["_item_key"] = key
            merged["_origin"] = override["action"]
            merged["_scope"] = f"{override['scope_type']}:{override['scope_key']}"
            items[key] = merged

        output = list(items.values())
        if not q:
            return output

        needle = q.lower()
        return [item for item in output if needle in json.dumps(item, default=str).lower()]

    async def create(
        self,
        collection: str,
        scope_type: str,
        scope_key: str,
        action: str,
        data: dict[str, Any],
        item_key: str | None = None,
    ) -> dict[str, Any]:
        return await self.upsert(collection, item_key or f"local_{uuid.uuid4().hex}", scope_type, scope_key, action, data)

    async def upsert(
        self,
        collection: str,
        item_key: str,
        scope_type: str,
        scope_key: str,
        action: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        ensure_collection(collection)
        if action not in ("override", "custom", "hidden"):
            raise HTTPException(status_code=422, detail="invalid_action")

        return await self._repository.upsert(collection, item_key, scope_type, scope_key, action, data)

    async def hide(self, collection: str, item_key: str, scope_type: str, scope_key: str) -> dict[str, Any]:
        return await self.upsert(collection, item_key, scope_type, scope_key, "hidden", {})
