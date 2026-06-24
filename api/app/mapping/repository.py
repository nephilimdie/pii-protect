from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.mapping.models import PiiMapping
from app.mapping.encryptor import FieldEncryptor
from app.mapping.key_provider import KeyProvider
from app.detection.entities import MappingEntry
from app.config import settings


class MappingRepository:
    def __init__(self, db: AsyncSession, key_provider: KeyProvider) -> None:
        self._db = db
        self._key_provider = key_provider
        # KEK encryptor kept for fallback decryption of pre-migration rows.
        self._kek_encryptor = FieldEncryptor(settings.encryption_key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _encryptor(self, tenant_id: str | None) -> FieldEncryptor:
        dek = await self._key_provider.get_dek(tenant_id)
        return FieldEncryptor(dek)

    async def _decrypt(self, value: str, tenant_id: str | None) -> str:
        """Decrypt *value* using the tenant DEK, falling back to the KEK.

        The fallback covers rows that were encrypted with the global KEK before
        the DEK/KEK migration (042_tenant_dek). Only attempted when tenant_id
        is not None, since for None the DEK *is* the KEK.
        """
        enc = await self._encryptor(tenant_id)
        try:
            return enc.decrypt(value)
        except ValueError:
            if tenant_id is not None:
                return self._kek_encryptor.decrypt(value)
            raise

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save_many(
        self,
        mappings: list[MappingEntry],
        context_id: str,
        context_type: str,
        tenant_id: str | None = None,
    ) -> None:
        if not mappings:
            return
        enc = await self._encryptor(tenant_id)
        rows = [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "context_id": context_id,
                "context_type": context_type,
                "token": entry.token,
                "original_encrypted": enc.encrypt(entry.original),
                "pii_type": entry.pii_type,
            }
            for entry in mappings
        ]
        stmt = pg_insert(PiiMapping).values(rows).on_conflict_do_nothing()
        await self._db.execute(stmt)
        await self._db.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

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
                original = await self._decrypt(row.original_encrypted, tenant_id)
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
                original = await self._decrypt(row.original_encrypted, tenant_id)
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

    async def find_all_by_context_id(
        self,
        context_id: str,
        tenant_id: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[dict], int]:
        """Return paginated mappings for a context_id across all context_types (Art. 20 export)."""
        base = select(PiiMapping).where(PiiMapping.context_id == context_id)
        if tenant_id is not None:
            base = base.where(PiiMapping.tenant_id == tenant_id)

        count_stmt = select(func.count()).select_from(PiiMapping).where(PiiMapping.context_id == context_id)
        if tenant_id is not None:
            count_stmt = count_stmt.where(PiiMapping.tenant_id == tenant_id)
        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = base.order_by(PiiMapping.created_at.asc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        items = []
        for row in rows:
            try:
                original = await self._decrypt(row.original_encrypted, tenant_id)
            except ValueError:
                original = "***"
            items.append({
                "id": str(row.id),
                "context_type": row.context_type,
                "token": row.token,
                "pii_type": row.pii_type,
                "original": original,
                "created_at": row.created_at.isoformat(),
            })
        return items, total

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

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
