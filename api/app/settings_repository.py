from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, key: str, default: str = "") -> str:
        result = await self._db.execute(
            text("SELECT value FROM settings WHERE key = :key"), {"key": key}
        )
        row = result.fetchone()
        return row[0] if row else default

    async def set(self, key: str, value: str) -> None:
        await self._db.execute(
            text("""
                INSERT INTO settings (key, value, updated_at)
                VALUES (:key, :value, :now)
                ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = :now
            """),
            {"key": key, "value": value, "now": datetime.utcnow()},
        )
        await self._db.commit()

    async def all(self) -> dict[str, str]:
        result = await self._db.execute(text("SELECT key, value FROM settings"))
        return {row[0]: row[1] for row in result.fetchall()}
