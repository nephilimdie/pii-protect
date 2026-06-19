from __future__ import annotations
from abc import ABC, abstractmethod


class TenantResolverInterface(ABC):
    @abstractmethod
    async def resolve(self, request_headers: dict[str, str]) -> str | None:
        """Return tenant_id, or None for self-hosted single-tenant."""
        ...


class SingleTenantResolver(TenantResolverInterface):
    """Default self-hosted resolver. Always returns None (no multi-tenancy)."""

    async def resolve(self, request_headers: dict[str, str]) -> str | None:
        return None
