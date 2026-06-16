from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import ApiKey
from app.usage.models import UsageEvent


class UsageService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def ensure_within_limits(self, api_key: ApiKey, chars_in: int) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if api_key.expires_at and api_key.expires_at <= now:
            raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": "This API key has expired.", "retry_after_seconds": None})
        if api_key.max_chars_per_request is not None and chars_in > api_key.max_chars_per_request:
            raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": "This API key exceeded its allowed request size.", "retry_after_seconds": None})

        if api_key.max_requests_per_minute is not None:
            minute_start = now - timedelta(minutes=1)
            requests = await self._count_events(api_key.id, minute_start)
            if requests >= api_key.max_requests_per_minute:
                raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": "This API key exceeded its allowed request rate.", "retry_after_seconds": 60})

        if api_key.max_requests_per_hour is not None:
            hour_start = now - timedelta(hours=1)
            requests = await self._count_events(api_key.id, hour_start)
            if requests >= api_key.max_requests_per_hour:
                raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": "This API key exceeded its hourly request limit.", "retry_after_seconds": 3600})

        if api_key.max_requests_per_day is not None:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            requests = await self._count_events(api_key.id, day_start)
            if requests >= api_key.max_requests_per_day:
                raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": "This API key exceeded its daily request limit.", "retry_after_seconds": 3600})

        if api_key.max_chars_per_month is not None:
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            chars = await self._sum_chars(api_key.id, month_start)
            if chars + chars_in > api_key.max_chars_per_month:
                raise HTTPException(status_code=429, detail={"error": "RATE_LIMIT_EXCEEDED", "message": "This API key exceeded its monthly character budget.", "retry_after_seconds": 3600})

    async def record(
        self,
        *,
        api_key_id: uuid.UUID,
        request_id: uuid.UUID,
        policy_id: str | None,
        policy_version: str | None,
        policy_hash: str | None,
        chars_in: int,
        chars_out: int,
        entities_count: int,
        entity_types_summary: list[str],
        latency_ms: int,
        status: str,
        error_code: str | None = None,
    ) -> None:
        entry = UsageEvent(
            id=uuid.uuid4(),
            request_id=request_id,
            api_key_id=api_key_id,
            policy_id=policy_id,
            policy_version=policy_version,
            policy_hash=policy_hash,
            chars_in=chars_in,
            chars_out=chars_out,
            entities_count=entities_count,
            entity_types_summary=entity_types_summary,
            latency_ms=latency_ms,
            status=status,
            error_code=error_code,
        )
        self._db.add(entry)
        await self._db.commit()

    async def total_chars_in(self) -> int:
        result = await self._db.execute(select(func.coalesce(func.sum(UsageEvent.chars_in), 0)))
        return int(result.scalar_one())

    async def total_events(self) -> int:
        result = await self._db.execute(select(func.count()).select_from(UsageEvent))
        return int(result.scalar_one())

    async def _count_events(self, api_key_id: uuid.UUID, since: datetime) -> int:
        stmt = select(func.count()).select_from(UsageEvent).where(
            UsageEvent.api_key_id == api_key_id,
            UsageEvent.created_at >= since,
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one())

    async def _sum_chars(self, api_key_id: uuid.UUID, since: datetime) -> int:
        stmt = select(func.coalesce(func.sum(UsageEvent.chars_in), 0)).select_from(UsageEvent).where(
            UsageEvent.api_key_id == api_key_id,
            UsageEvent.created_at >= since,
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one())
