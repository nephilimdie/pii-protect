from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PresidioContextRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def find_enabled(self) -> list[dict]:
        result = await self._db.execute(
            text("SELECT id, entity_type, word, description, enabled FROM presidio_context WHERE enabled = true")
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def find_all(self) -> list[dict]:
        result = await self._db.execute(
            text("SELECT id, entity_type, word, description, enabled, created_at FROM presidio_context ORDER BY entity_type, word")
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def create(self, entity_type: str, word: str, description: str) -> dict:
        result = await self._db.execute(
            text("INSERT INTO presidio_context (entity_type, word, description, enabled) VALUES (:et, :w, :d, true) RETURNING id, entity_type, word, description, enabled, created_at"),
            {"et": entity_type, "w": word.lower().strip(), "d": description},
        )
        await self._db.commit()
        return dict(result.fetchone()._mapping)

    async def update(self, entry_id: int, **kwargs) -> dict:
        sets = ", ".join(f"{k} = :{k}" for k in kwargs)
        result = await self._db.execute(
            text(f"UPDATE presidio_context SET {sets} WHERE id = :id RETURNING id, entity_type, word, description, enabled, created_at"),
            {"id": entry_id, **kwargs},
        )
        await self._db.commit()
        row = result.fetchone()
        if row is None:
            return {}
        return dict(row._mapping)

    async def delete(self, entry_id: int) -> bool:
        result = await self._db.execute(
            text("DELETE FROM presidio_context WHERE id = :id"),
            {"id": entry_id},
        )
        await self._db.commit()
        return result.rowcount > 0
