from __future__ import annotations
from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from app.detection.config_resolver import ResolvedDetectionConfig


class ConfigResolverInterface(ABC):
    @abstractmethod
    async def resolve(self, db: AsyncSession, tenant_id: str | None) -> ResolvedDetectionConfig:
        """Return merged detection config for the given tenant (or global if None)."""
        ...
