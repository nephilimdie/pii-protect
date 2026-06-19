import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.scoped_config.collections import BASE_QUERIES, item_key, normalize


class ScopedConfigRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def base_items(self, collection: str) -> list[dict[str, Any]]:
        result = await self._db.execute(text(BASE_QUERIES[collection]))
        items = []

        for row in result.fetchall():
            data = normalize(dict(row._mapping))
            data["_item_key"] = item_key(collection, data)
            data["_origin"] = "platform"
            data["_scope"] = "platform"
            items.append(data)

        return items

    async def overrides(self, collection: str, scope_type: str, scope_key: str) -> list[dict[str, Any]]:
        result = await self._db.execute(
            text(
                "SELECT item_key, action, data, scope_type, scope_key"
                " FROM scoped_config_overrides"
                " WHERE collection = :collection AND scope_type = :scope_type AND scope_key = :scope_key"
                " ORDER BY updated_at"
            ),
            {"collection": collection, "scope_type": scope_type, "scope_key": scope_key},
        )

        return [dict(row._mapping) for row in result.fetchall()]

    async def upsert(
        self,
        collection: str,
        item_key_value: str,
        scope_type: str,
        scope_key: str,
        action: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        result = await self._db.execute(
            text(
                "INSERT INTO scoped_config_overrides"
                " (id, scope_type, scope_key, collection, item_key, action, data, updated_at)"
                " VALUES (:id, :scope_type, :scope_key, :collection, :item_key, :action, CAST(:data AS jsonb), now())"
                " ON CONFLICT (scope_type, scope_key, collection, item_key) DO UPDATE SET"
                " action = :action, data = CAST(:data AS jsonb), updated_at = now()"
                " RETURNING id, scope_type, scope_key, collection, item_key, action, data, created_at, updated_at"
            ),
            {
                "id": str(uuid.uuid4()),
                "scope_type": scope_type,
                "scope_key": scope_key,
                "collection": collection,
                "item_key": item_key_value,
                "action": action,
                "data": json.dumps(data),
            },
        )
        await self._db.commit()

        return normalize(dict(result.fetchone()._mapping))
