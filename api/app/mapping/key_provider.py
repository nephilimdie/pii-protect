"""DEK/KEK key management for per-tenant encryption.

Architecture (Option A — KEK in env):
  ENCRYPTION_KEY (env) = KEK master key
    └─ encrypts one DEK per tenant stored in the tenant_keys table.

  MappingRepository calls get_dek(tenant_id) before every encrypt/decrypt.
  For tenant_id=None (self-hosted, no multitenancy) the KEK is returned
  directly — no DB lookup, no behavioural change from before.

Swapping to a KMS-backed provider (Option B) requires only a new class that
implements KeyProvider; no changes to MappingRepository or the routers.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Module-level DEK cache — survives across requests within the same worker
# process. Stale entries are impossible: DEKs are immutable once created.
_DEK_CACHE: dict[str, str] = {}
_CACHE_LOCK = asyncio.Lock()


class KeyProvider(ABC):
    """Abstract interface for resolving a per-tenant Data Encryption Key."""

    @abstractmethod
    async def get_dek(self, tenant_id: str | None) -> str:
        """Return the plaintext DEK for *tenant_id*.

        For tenant_id=None (self-hosted) implementors should return the KEK
        so that existing data remains decryptable without migration.
        """


class EnvKekKeyProvider(KeyProvider):
    """KeyProvider backed by an environment-variable KEK and a DB DEK store.

    First call for a tenant_id:
      1. Check in-process cache.
      2. Query tenant_keys table.
      3. If not found → generate Fernet key, encrypt with KEK, persist, cache.

    Subsequent calls: served from in-process cache (no DB round-trip).
    """

    def __init__(self, db: AsyncSession, kek: str) -> None:
        self._db = db
        self._kek = kek
        self._kek_fernet = Fernet(kek.encode() if isinstance(kek, str) else kek)

    async def get_dek(self, tenant_id: str | None) -> str:
        if tenant_id is None:
            # Self-hosted: KEK *is* the DEK — backward-compatible, no DB needed.
            return self._kek

        async with _CACHE_LOCK:
            if tenant_id in _DEK_CACHE:
                return _DEK_CACHE[tenant_id]

        dek = await self._load_or_create(tenant_id)

        async with _CACHE_LOCK:
            _DEK_CACHE[tenant_id] = dek

        return dek

    async def _load_or_create(self, tenant_id: str) -> str:
        from app.mapping.models import TenantKey

        result = await self._db.execute(
            select(TenantKey).where(TenantKey.tenant_id == tenant_id)
        )
        row = result.scalar_one_or_none()

        if row is None:
            dek_bytes = Fernet.generate_key()
            dek_encrypted = self._kek_fernet.encrypt(dek_bytes).decode()
            self._db.add(TenantKey(tenant_id=tenant_id, dek_encrypted=dek_encrypted))
            await self._db.commit()
            return dek_bytes.decode()

        return self._kek_fernet.decrypt(row.dek_encrypted.encode()).decode()
