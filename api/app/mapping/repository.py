from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.mapping.models import PiiMapping
from app.mapping.encryptor import FieldEncryptor
from app.mapping.key_provider import EnvKekKeyProvider, KeyProvider
from app.detection.entities import MappingEntry
from app.config import settings


class MappingRepository:
    def __init__(self, db: AsyncSession, key_provider: KeyProvider | None = None) -> None:
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
        ttl_hours: int | None = None,
        project_id: str = "default",
    ) -> None:
        if not mappings:
            return
        enc = await self._encryptor(tenant_id)
        expires_at = datetime.utcnow() + timedelta(
            hours=ttl_hours if ttl_hours is not None else settings.mapping_ttl_hours
        )
        rows = [
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant_id,
                "project_id": project_id,
                "context_id": context_id,
                "context_type": context_type,
                "token": entry.token,
                "original_encrypted": enc.encrypt(entry.original),
                "pii_type": entry.pii_type,
                "expires_at": expires_at,
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
        project_id: str = "default",
    ) -> list[MappingEntry]:
        stmt = select(PiiMapping).where(
            PiiMapping.tenant_id == tenant_id,
            PiiMapping.project_id == project_id,
            PiiMapping.context_id == context_id,
            PiiMapping.context_type == context_type,
            (PiiMapping.expires_at.is_(None) | (PiiMapping.expires_at > datetime.utcnow())),
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
        active = PiiMapping.expires_at.is_(None) | (PiiMapping.expires_at > datetime.utcnow())
        base_filter = active
        if tenant_id is not None:
            base_filter = base_filter & (PiiMapping.tenant_id == tenant_id)

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
        project_id: str = "default",
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[list[dict], int]:
        """Return paginated mappings for a context_id across all context_types (Art. 20 export)."""
        active = PiiMapping.expires_at.is_(None) | (PiiMapping.expires_at > datetime.utcnow())
        base = select(PiiMapping).where(
            PiiMapping.context_id == context_id,
            PiiMapping.project_id == project_id,
            active,
        )
        if tenant_id is not None:
            base = base.where(PiiMapping.tenant_id == tenant_id)

        count_stmt = select(func.count()).select_from(PiiMapping).where(
            PiiMapping.context_id == context_id,
            PiiMapping.project_id == project_id,
            active,
        )
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
        stmt = delete(PiiMapping).where(
            (PiiMapping.expires_at.is_not(None) & (PiiMapping.expires_at < datetime.utcnow()))
            | (PiiMapping.expires_at.is_(None) & (PiiMapping.created_at < cutoff))
        )
        if tenant_id is not None:
            stmt = stmt.where(PiiMapping.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        surrogate_tables = ("surrogate_mappings", "surrogate_profiles")
        deleted = result.rowcount or 0
        for table in surrogate_tables:
            scope = " AND tenant_id = :tenant" if tenant_id is not None else ""
            query = text(
                f"DELETE FROM {table} WHERE ("
                "(expires_at IS NOT NULL AND expires_at < :now)"
                " OR (expires_at IS NULL AND created_at < :cutoff)"
                f"){scope}"
            )
            params = {"now": datetime.utcnow(), "cutoff": cutoff}
            if tenant_id is not None:
                params["tenant"] = tenant_id
            surrogate_result = await self._db.execute(query, params)
            deleted += surrogate_result.rowcount or 0
        await self._db.commit()
        return deleted

    async def rotate_tenant_dek(self, tenant_id: str) -> int:
        """Re-encrypt every tenant mapping before replacing its DEK."""
        if not tenant_id or not isinstance(self._key_provider, EnvKekKeyProvider):
            raise ValueError("tenant_dek_rotation_requires_tenant_key_provider")

        old_dek = await self._key_provider.get_dek(tenant_id)
        new_dek = Fernet.generate_key().decode()
        old_encryptor = FieldEncryptor(old_dek)
        new_encryptor = FieldEncryptor(new_dek)
        result = await self._db.execute(
            select(PiiMapping).where(PiiMapping.tenant_id == tenant_id)
        )
        rows = result.scalars().all()
        for row in rows:
            row.original_encrypted = new_encryptor.encrypt(
                old_encryptor.decrypt(row.original_encrypted)
            )
        await self._db.commit()
        await self._key_provider.replace_dek(tenant_id, new_dek)
        return len(rows)
