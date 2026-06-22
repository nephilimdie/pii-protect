from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.audit.models import AuditLog


def _anonymize_ip(ip: str | None) -> str | None:
    """Truncate last octet of IPv4 / last group of IPv6 for GDPR-safe logging."""
    if not ip:
        return ip
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
    if ":" in ip:
        parts = ip.split(":")
        if len(parts) > 1:
            return ":".join(parts[:-1]) + ":0"
    return ip


class AuditService:
    def __init__(self, db: AsyncSession, ip_anonymization: bool = True):
        self._db = db
        self._ip_anon = ip_anonymization

    async def log(
        self,
        api_key_id: uuid.UUID,
        action: str,
        context_id: str | None = None,
        pii_types_found: list[str] | None = None,
        char_count: int | None = None,
        tenant_id: str | None = None,
        event_category: str = "engine",
        document_hash: str | None = None,
        ip: str | None = None,
        reason: str | None = None,
    ) -> None:
        safe_ip = _anonymize_ip(ip) if self._ip_anon else ip
        entry = AuditLog(
            id=uuid.uuid4(),
            api_key_id=api_key_id,
            action=action,
            context_id=context_id,
            pii_types_found=pii_types_found,
            char_count=char_count,
            tenant_id=tenant_id,
            event_category=event_category,
            document_hash=document_hash,
            ip=safe_ip,
            reason=reason,
        )
        self._db.add(entry)
        await self._db.commit()

    async def list_paginated(
        self,
        page: int,
        per_page: int,
        action_filter: str | None = None,
        tenant_id: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        if tenant_id is not None:
            stmt = stmt.where(AuditLog.tenant_id == tenant_id)
            count_stmt = count_stmt.where(AuditLog.tenant_id == tenant_id)

        if action_filter:
            stmt = stmt.where(AuditLog.action == action_filter)
            count_stmt = count_stmt.where(AuditLog.action == action_filter)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.order_by(AuditLog.created_at.desc())
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def delete_by_ids(self, ids: list[uuid.UUID], tenant_id: str | None = None) -> int:
        stmt = delete(AuditLog).where(AuditLog.id.in_(ids))
        if tenant_id is not None:
            stmt = stmt.where(AuditLog.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        await self._db.commit()
        return result.rowcount

    async def delete_expired(self, ttl_days: int, tenant_id: str | None = None) -> int:
        cutoff = datetime.utcnow() - timedelta(days=ttl_days)
        stmt = delete(AuditLog).where(AuditLog.created_at < cutoff)
        if tenant_id is not None:
            stmt = stmt.where(AuditLog.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        await self._db.commit()
        return result.rowcount

    async def find_by_context(
        self,
        context_id: str,
        tenant_id: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[AuditLog], int]:
        base = select(AuditLog).where(AuditLog.context_id == context_id)
        if tenant_id is not None:
            base = base.where(AuditLog.tenant_id == tenant_id)

        count_stmt = select(func.count()).select_from(AuditLog).where(AuditLog.context_id == context_id)
        if tenant_id is not None:
            count_stmt = count_stmt.where(AuditLog.tenant_id == tenant_id)
        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = base.order_by(AuditLog.created_at.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    _MIN_EVENTS_FOR_SPIKE_DETECTION = 100

    async def get_anomaly_stats(
        self,
        tenant_id: str | None = None,
        threshold: float = 3.0,
    ) -> dict:
        now = datetime.utcnow()
        last_hour_start = now - timedelta(hours=1)
        seven_days_start = now - timedelta(days=7)

        def _count_stmt(start: datetime, end: datetime | None = None):
            s = select(func.count()).select_from(AuditLog).where(AuditLog.created_at >= start)
            if end:
                s = s.where(AuditLog.created_at < end)
            if tenant_id is not None:
                s = s.where(AuditLog.tenant_id == tenant_id)
            return s

        last_hour = (await self._db.execute(_count_stmt(last_hour_start))).scalar_one()
        seven_days_total = (await self._db.execute(_count_stmt(seven_days_start))).scalar_one()
        hourly_avg = (seven_days_total / 7.0) / 24.0

        erasure_stmt = select(func.count()).select_from(AuditLog).where(
            AuditLog.created_at >= last_hour_start,
            AuditLog.action == "erasure_executed",
        )
        if tenant_id is not None:
            erasure_stmt = erasure_stmt.where(AuditLog.tenant_id == tenant_id)
        recent_erasures = (await self._db.execute(erasure_stmt)).scalar_one()

        anomalies = []
        # Guard: skip volume-spike detection when baseline is too thin to be meaningful.
        if seven_days_total >= self._MIN_EVENTS_FOR_SPIKE_DETECTION and hourly_avg > 0 and last_hour > hourly_avg * threshold:
            anomalies.append({
                "type": "volume_spike",
                "description": (
                    f"Last hour: {last_hour} events vs avg {hourly_avg:.1f}/h "
                    f"({last_hour / hourly_avg:.1f}x threshold {threshold}x)"
                ),
            })
        if recent_erasures > 10:
            anomalies.append({
                "type": "bulk_erasure",
                "description": f"{recent_erasures} erasure operations in the last hour",
            })

        return {
            "checked_at": now.isoformat(),
            "last_hour_events": last_hour,
            "hourly_avg_7d": round(hourly_avg, 2),
            "seven_days_total": seven_days_total,
            "threshold": threshold,
            "anomalies_detected": len(anomalies) > 0,
            "anomalies": anomalies,
        }
