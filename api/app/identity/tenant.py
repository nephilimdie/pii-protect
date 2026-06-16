"""Tenant context resolution for multi-tenancy support.

When multitenancy_enabled=False (self-hosted default), get_tenant_id() always
returns None and every caller behaves exactly as before — no filtering occurs.

When multitenancy_enabled=True (cloud managed), get_tenant_id() extracts the
tenant_id from the already-resolved ApiKey. Routers and services pass this
value down to repositories which add a WHERE tenant_id = :tid clause.
"""

from __future__ import annotations

from fastapi import Depends

from app.config import settings
from app.identity.dependencies import get_api_key
from app.identity.models import ApiKey


async def get_tenant_id(
    api_key: ApiKey = Depends(get_api_key),
) -> str | None:
    """Return the tenant_id scoped to this request, or None in self-hosted mode."""
    if not settings.multitenancy_enabled:
        return None
    return api_key.tenant_id
