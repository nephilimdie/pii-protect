from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, key: str, default: str = "", tenant_id: str | None = None) -> str:
        result = await self._db.execute(
            text("SELECT value FROM settings WHERE key = :key "
                 "AND (tenant_id IS NOT DISTINCT FROM :tenant OR tenant_id IS NULL) "
                 "ORDER BY (tenant_id IS NULL) ASC LIMIT 1"),
            {"key": key, "tenant": tenant_id},
        )
        row = result.fetchone()
        return row[0] if row else default

    async def set(self, key: str, value: str, tenant_id: str | None = None) -> None:
        params = {"key": key, "value": value, "tenant": tenant_id, "now": datetime.utcnow()}
        result = await self._db.execute(text(
            "UPDATE settings SET value = :value, updated_at = :now "
            "WHERE key = :key AND tenant_id IS NOT DISTINCT FROM :tenant"
        ), params)
        if not result.rowcount:
            await self._db.execute(text(
                "INSERT INTO settings (key, value, updated_at, tenant_id) "
                "VALUES (:key, :value, :now, :tenant)"
            ), params)
        await self._db.commit()

    async def all(self, tenant_id: str | None = None) -> dict[str, str]:
        result = await self._db.execute(text(
            "SELECT key, value FROM settings "
            "WHERE tenant_id IS NOT DISTINCT FROM :tenant OR tenant_id IS NULL "
            "ORDER BY (tenant_id IS NULL) ASC"
        ), {"tenant": tenant_id})
        return {row[0]: row[1] for row in result.fetchall()}
