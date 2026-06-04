from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.audit.models import AuditLog
from app.mapping.models import PiiMapping


class StatsService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_summary(self) -> dict:
        total_anon = await self._count_action("anonymize")
        total_tokens = await self._count_tokens()
        pii_breakdown = await self._pii_breakdown()
        requests_24h = await self._requests_last_24h()
        return {
            "total_anonymizations": total_anon,
            "total_tokens_created": total_tokens,
            "pii_types_breakdown": pii_breakdown,
            "requests_last_24h": requests_24h,
        }

    async def _count_action(self, action: str) -> int:
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _count_tokens(self) -> int:
        stmt = select(func.count()).select_from(PiiMapping)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _pii_breakdown(self) -> dict:
        stmt = select(PiiMapping.pii_type, func.count().label("cnt")).group_by(PiiMapping.pii_type)
        result = await self._db.execute(stmt)
        return {row.pii_type: row.cnt for row in result}

    async def _requests_last_24h(self) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= cutoff)
        result = await self._db.execute(stmt)
        return result.scalar_one()
