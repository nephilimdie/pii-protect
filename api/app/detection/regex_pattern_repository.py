from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.detection.models import RegexPattern


class RegexPatternRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def find_enabled(self) -> list[RegexPattern]:
        result = await self._db.execute(
            select(RegexPattern).where(RegexPattern.enabled == True).order_by(RegexPattern.pii_type)
        )
        return list(result.scalars().all())

    async def find_all(self) -> list[RegexPattern]:
        result = await self._db.execute(
            select(RegexPattern).order_by(RegexPattern.pii_type)
        )
        return list(result.scalars().all())

    async def find_by_id(self, pattern_id) -> RegexPattern | None:
        result = await self._db.execute(
            select(RegexPattern).where(RegexPattern.id == pattern_id)
        )
        return result.scalar_one_or_none()

    async def save(self, pattern: RegexPattern) -> RegexPattern:
        self._db.add(pattern)
        await self._db.commit()
        await self._db.refresh(pattern)
        return pattern

    async def delete(self, pattern: RegexPattern) -> None:
        await self._db.delete(pattern)
        await self._db.commit()
