from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.mapping.key_provider import EnvKekKeyProvider, KeyProvider


async def get_key_provider(
    db: AsyncSession = Depends(get_db),
) -> KeyProvider:
    """FastAPI dependency that resolves the active KeyProvider implementation."""
    return EnvKekKeyProvider(db, settings.encryption_key)
