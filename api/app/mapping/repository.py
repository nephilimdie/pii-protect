from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.mapping.models import PiiMapping
from app.mapping.encryptor import FieldEncryptor
from app.detection.entities import MappingEntry
from app.config import settings


class MappingRepository:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._encryptor = FieldEncryptor(settings.encryption_key)

    async def save_many(
        self,
        mappings: list[MappingEntry],
        context_id: str,
        context_type: str,
        tenant_id: str | None = None,
    ) -> None:
        if not mappings:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "context_id": context_id,
                "context_type": context_type,
                "token": entry.token,
                "original_encrypted": self._encryptor.encrypt(entry.original),
                "pii_type": entry.pii_type,
            }
            for entry in mappings
        ]
        stmt = pg_insert(PiiMapping).values(rows).on_conflict_do_nothing()
        await self._db.execute(stmt)
        await self._db.commit()

    async def find_by_context(
        self,
        context_id: str,
        context_type: str,
        tenant_id: str | None = None,
    ) -> list[MappingEntry]:
        stmt = select(PiiMapping).where(
            PiiMapping.tenant_id == tenant_id,
            PiiMapping.context_id == context_id,
            PiiMapping.context_type == context_type,
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        entries = []
        for row in rows:
            try:
                original = self._encryptor.decrypt(row.original_encrypted)
            except ValueError:
                continue
            entries.append(MappingEntry(
                token=row.token,
                original=original,
                pii_type=row.pii_type,
            ))
        return entries

    async def list_paginated(
        self,
        page: int,
        per_page: int,
        tenant_id: str | None = None,
    ) -> tuple[list[dict], int]:
        base_filter = PiiMapping.tenant_id == tenant_id if tenant_id is not None else True

        count_stmt = select(func.count()).select_from(PiiMapping).where(base_filter)
        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(PiiMapping)
            .where(base_filter)
            .order_by(PiiMapping.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        items = []
        for row in rows:
            try:
                original = self._encryptor.decrypt(row.original_encrypted)
            except ValueError:
                original = "***"
            items.append({
                "id": str(row.id),
                "context_id": row.context_id,
                "context_type": row.context_type,
                "token": row.token,
                "pii_type": row.pii_type,
                "original": original,
                "created_at": row.created_at,
            })
        return items, total

    async def delete_by_ids(self, ids: list[uuid.UUID], tenant_id: str | None = None) -> int:
        stmt = delete(PiiMapping).where(PiiMapping.id.in_(ids))
        if tenant_id is not None:
            stmt = stmt.where(PiiMapping.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        await self._db.commit()
        return result.rowcount

    async def delete_expired(self, ttl_days: int, tenant_id: str | None = None) -> int:
        cutoff = datetime.utcnow() - timedelta(days=ttl_days)
        stmt = delete(PiiMapping).where(PiiMapping.created_at < cutoff)
        if tenant_id is not None:
            stmt = stmt.where(PiiMapping.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        await self._db.commit()
        return result.rowcount
