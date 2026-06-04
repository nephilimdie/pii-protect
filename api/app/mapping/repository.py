import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.mapping.models import PiiMapping
from app.mapping.encryptor import FieldEncryptor
from app.detection.entities import MappingEntry
from app.config import settings


class MappingRepository:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._encryptor = FieldEncryptor(settings.encryption_key)

    async def save_many(self, mappings: list[MappingEntry], context_id: str, context_type: str) -> None:
        if not mappings:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "context_id": context_id,
                "context_type": context_type,
                "token": entry.token,
                "original_encrypted": self._encryptor.encrypt(entry.original),
                "pii_type": entry.pii_type,
            }
            for entry in mappings
        ]
        stmt = pg_insert(PiiMapping).values(rows).on_conflict_do_nothing(
            index_elements=["context_id", "context_type", "token"]
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def find_by_context(self, context_id: str, context_type: str) -> list[MappingEntry]:
        stmt = select(PiiMapping).where(
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

    async def delete_expired(self, ttl_days: int) -> int:
        cutoff = datetime.utcnow() - timedelta(days=ttl_days)
        stmt = delete(PiiMapping).where(PiiMapping.created_at < cutoff)
        result = await self._db.execute(stmt)
        await self._db.commit()
        return result.rowcount
