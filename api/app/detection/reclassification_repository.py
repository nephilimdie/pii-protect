import uuid
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ReclassificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    _SELECT_COLS = (
        "id, from_type, to_type, context_pattern, entity_pattern, context_window, description, enabled"
    )
    _SELECT_COLS_FULL = (
        "id, from_type, to_type, context_pattern, entity_pattern, context_window, description, enabled, created_at"
    )

    async def find_enabled(self) -> list[dict]:
        result = await self._db.execute(
            text(
                f"SELECT {self._SELECT_COLS}"
                " FROM reclassification_rules WHERE enabled = true ORDER BY from_type"
            )
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def find_all(self) -> list[dict]:
        result = await self._db.execute(
            text(
                f"SELECT {self._SELECT_COLS_FULL}"
                " FROM reclassification_rules ORDER BY from_type, created_at"
            )
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def create(self, from_type: str, to_type: str | None, context_pattern: str | None,
                     entity_pattern: str | None, context_window: int, description: str) -> dict:
        result = await self._db.execute(
            text(
                "INSERT INTO reclassification_rules"
                " (id, from_type, to_type, context_pattern, entity_pattern, context_window, description, enabled)"
                " VALUES (CAST(:id AS uuid), :from_type, :to_type, :context_pattern, :entity_pattern, :context_window, :description, true)"
                f" RETURNING {self._SELECT_COLS_FULL}"
            ),
            {
                "id": str(uuid.uuid4()),
                "from_type": from_type,
                "to_type": to_type,
                "context_pattern": context_pattern,
                "entity_pattern": entity_pattern,
                "context_window": context_window,
                "description": description,
            },
        )
        await self._db.commit()
        return dict(result.fetchone()._mapping)

    async def update(self, rule_id: str, **kwargs) -> dict | None:
        sets = ", ".join(f"{k} = :{k}" for k in kwargs)
        result = await self._db.execute(
            text(
                f"UPDATE reclassification_rules SET {sets} WHERE id = CAST(:id AS uuid)"
                f" RETURNING {self._SELECT_COLS_FULL}"
            ),
            {"id": rule_id, **kwargs},
        )
        await self._db.commit()
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def delete(self, rule_id: str) -> bool:
        result = await self._db.execute(
            text("DELETE FROM reclassification_rules WHERE id = CAST(:id AS uuid)"),
            {"id": rule_id},
        )
        await self._db.commit()
        return result.rowcount > 0
