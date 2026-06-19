from __future__ import annotations
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

    async def create(
        self,
        name: str,
        role: str,
        max_requests_per_minute: int | None = None,
        max_requests_per_hour: int | None = None,
        max_requests_per_day: int | None = None,
        max_chars_per_request: int | None = None,
        max_chars_per_month: int | None = None,
        expires_at: datetime | None = None,
        tenant_id: str | None = None,
    ) -> tuple[ApiKey, str]:
        plain_key = secrets.token_urlsafe(32)
        key = ApiKey(
            id=uuid.uuid4(),
            name=name,
            key_hash=self._hash(plain_key),
            role=role,
            tenant_id=tenant_id,
            max_requests_per_minute=max_requests_per_minute,
            max_requests_per_hour=max_requests_per_hour,
            max_requests_per_day=max_requests_per_day,
            max_chars_per_request=max_chars_per_request,
            max_chars_per_month=max_chars_per_month,
            expires_at=expires_at,
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
        if api_key.expires_at and api_key.expires_at <= datetime.utcnow():
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

    async def list_for_tenant(self, tenant_id: str) -> list[ApiKey]:
        result = await self._db.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke(self, key_id: uuid.UUID) -> None:
        stmt = update(ApiKey).where(ApiKey.id == key_id).values(active=False)
        await self._db.execute(stmt)
        await self._db.commit()

    async def revoke_for_tenant(self, key_id: uuid.UUID, tenant_id: str) -> None:
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
            .values(active=False)
        )
        result = await self._db.execute(stmt)
        await self._db.commit()
        if result.rowcount == 0:
            raise ValueError("key_not_found_for_tenant")

    async def rotate(self, key_id: uuid.UUID, tenant_id: str | None = None) -> tuple[ApiKey, str]:
        """Revoke existing key and return a new one with the same metadata."""
        stmt = select(ApiKey).where(ApiKey.id == key_id)
        if tenant_id is not None:
            stmt = stmt.where(ApiKey.tenant_id == tenant_id)
        result = await self._db.execute(stmt)
        old_key = result.scalar_one_or_none()
        if old_key is None:
            raise ValueError("key_not_found")

        revoke_stmt = update(ApiKey).where(ApiKey.id == key_id).values(active=False)
        await self._db.execute(revoke_stmt)

        new_key, plain = await self.create(
            name=old_key.name,
            role=old_key.role,
            tenant_id=old_key.tenant_id,
            max_requests_per_minute=old_key.max_requests_per_minute,
            max_requests_per_hour=old_key.max_requests_per_hour,
            max_requests_per_day=old_key.max_requests_per_day,
            max_chars_per_request=old_key.max_chars_per_request,
            max_chars_per_month=old_key.max_chars_per_month,
            expires_at=old_key.expires_at,
        )
        return new_key, plain

    async def find_active_for_tenant(self, tenant_id: str, role: str | None = None) -> ApiKey | None:
        stmt = select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.active == True)
        if role:
            stmt = stmt.where(ApiKey.role == role)
        result = await self._db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def count(self) -> int:
        from sqlalchemy import func
        result = await self._db.execute(select(func.count()).select_from(ApiKey))
        return result.scalar_one()

    def _hash(self, plain_key: str) -> str:
        return hashlib.sha256(plain_key.encode()).hexdigest()
