import hashlib
import secrets
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.identity.models import ApiKey


class ApiKeyService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(self, name: str, role: str) -> tuple[ApiKey, str]:
        plain_key = secrets.token_urlsafe(32)
        key = ApiKey(
            id=uuid.uuid4(),
            name=name,
            key_hash=self._hash(plain_key),
            role=role,
        )
        self._db.add(key)
        await self._db.commit()
        await self._db.refresh(key)
        return key, plain_key

    async def verify(self, plain_key: str) -> ApiKey | None:
        key_hash = self._hash(plain_key)
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active == True)
        result = await self._db.execute(stmt)
        api_key = result.scalar_one_or_none()
        if api_key is None:
            return None
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == api_key.id)
            .values(last_used_at=datetime.utcnow())
        )
        await self._db.execute(stmt)
        await self._db.commit()
        return api_key

    async def list_all(self) -> list[ApiKey]:
        result = await self._db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
        return list(result.scalars().all())

    async def revoke(self, key_id: uuid.UUID) -> None:
        stmt = update(ApiKey).where(ApiKey.id == key_id).values(active=False)
        await self._db.execute(stmt)
        await self._db.commit()

    async def count(self) -> int:
        from sqlalchemy import func
        result = await self._db.execute(select(func.count()).select_from(ApiKey))
        return result.scalar_one()

    def _hash(self, plain_key: str) -> str:
        return hashlib.sha256(plain_key.encode()).hexdigest()
