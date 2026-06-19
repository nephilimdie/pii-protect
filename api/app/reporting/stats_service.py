from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.audit.models import AuditLog
from app.mapping.models import PiiMapping
from app.usage.models import UsageEvent


class StatsService:
    def __init__(self, db: AsyncSession, tenant_id: str | None = None):
        self._db = db
        self._tenant_id = tenant_id

    async def get_summary(self) -> dict:
        total_anon = await self._count_action("anonymize")
        total_tokens = await self._count_tokens()
        pii_breakdown = await self._pii_breakdown()
        requests_24h = await self._requests_last_24h()
        usage_events = await self._usage_events_total()
        chars_in = await self._usage_chars_in_total()
        return {
            "total_anonymizations": total_anon,
            "total_tokens_created": total_tokens,
            "pii_types_breakdown": pii_breakdown,
            "requests_last_24h": requests_24h,
            "usage_events_total": usage_events,
            "usage_chars_in_total": chars_in,
        }

    async def _count_action(self, action: str) -> int:
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        if self._tenant_id is not None:
            stmt = stmt.where(AuditLog.tenant_id == self._tenant_id)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _count_tokens(self) -> int:
        stmt = select(func.count()).select_from(PiiMapping)
        if self._tenant_id is not None:
            stmt = stmt.where(PiiMapping.tenant_id == self._tenant_id)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _pii_breakdown(self) -> dict:
        stmt = select(PiiMapping.pii_type, func.count().label("cnt")).group_by(PiiMapping.pii_type)
        if self._tenant_id is not None:
            stmt = stmt.where(PiiMapping.tenant_id == self._tenant_id)
        result = await self._db.execute(stmt)
        return {row.pii_type: row.cnt for row in result}

    async def _requests_last_24h(self) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        stmt = select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= cutoff)
        if self._tenant_id is not None:
            stmt = stmt.where(AuditLog.tenant_id == self._tenant_id)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _usage_events_total(self) -> int:
        stmt = select(func.count()).select_from(UsageEvent)
        if self._tenant_id is not None:
            stmt = stmt.where(UsageEvent.tenant_id == self._tenant_id)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def _usage_chars_in_total(self) -> int:
        stmt = select(func.coalesce(func.sum(UsageEvent.chars_in), 0)).select_from(UsageEvent)
        if self._tenant_id is not None:
            stmt = stmt.where(UsageEvent.tenant_id == self._tenant_id)
        result = await self._db.execute(stmt)
        return result.scalar_one()
