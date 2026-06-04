from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.detection.models import DenylistEntry


class DenylistRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def find_enabled(self) -> list[DenylistEntry]:
        result = await self._db.execute(
            select(DenylistEntry).where(DenylistEntry.enabled == True)
        )
        return list(result.scalars().all())

    async def find_all(self) -> list[DenylistEntry]:
        result = await self._db.execute(select(DenylistEntry))
        return list(result.scalars().all())

    async def find_by_id(self, entry_id) -> DenylistEntry | None:
        result = await self._db.execute(
            select(DenylistEntry).where(DenylistEntry.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def save(self, entry: DenylistEntry) -> DenylistEntry:
        self._db.add(entry)
        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def delete(self, entry: DenylistEntry) -> None:
        await self._db.delete(entry)
        await self._db.commit()
