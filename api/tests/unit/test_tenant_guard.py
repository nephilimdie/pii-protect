"""Unit tests for tenant guard middleware and self-hosted quota stripping.

Strategy: we build a *minimal* FastAPI app that mirrors the middleware and
routes we care about, instead of importing the production ``app`` from
``app.main`` (which would fire the full lifespan/DB startup).  This lets us
inject settings freely without side-effects.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# ---------------------------------------------------------------------------
# Set required env vars BEFORE any app import so Settings() can initialise
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-chars-padded-00000000")
os.environ.setdefault("ADMIN_INITIAL_KEY", "test-admin-key")

# ---------------------------------------------------------------------------
# Stub out heavy dependencies before any app import
# ---------------------------------------------------------------------------
from types import ModuleType
from sqlalchemy.orm import DeclarativeBase

database_stub = ModuleType("app.database")


class _Base(DeclarativeBase):
    pass


async def _get_db():
    yield None


database_stub.Base = _Base
database_stub.get_db = _get_db
sys.modules["app.database"] = database_stub

# ---------------------------------------------------------------------------
import pytest
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import MutableHeaders
from unittest.mock import AsyncMock

from app.config import Settings, get_settings
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.routers.scoped_config import require_multitenancy, router as scoped_config_router
import app.routers.scoped_config as _scoped_config_module
from app.routers.identity import router as identity_router, _strip_commercial_quota_if_self_hosted, CreateKeyRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app(settings_kwargs: dict) -> FastAPI:
    """Build a minimal FastAPI app with the tenant guard middleware and
    the routers needed for the tests, using the supplied settings."""

    test_settings = Settings(**settings_kwargs)

    def _get_test_settings() -> Settings:
        return test_settings

    app = FastAPI()

    # Replicate the tenant guard middleware from main.py
    @app.middleware("http")
    async def tenant_guard_middleware(request: Request, call_next):
        s = _get_test_settings()
        if not s.multitenancy_enabled:
            headers = MutableHeaders(scope=request.scope)
            # MutableHeaders API varies by Starlette version; use del with guard
            if "x-pii-tenant-id" in headers:
                del headers["x-pii-tenant-id"]
        elif s.accept_tenant_header:
            pass
        else:
            if request.headers.get("x-pii-tenant-id"):
                return JSONResponse({"detail": "tenant_header_not_accepted"}, status_code=403)
        return await call_next(request)

    # A simple probe endpoint that echoes back whether the tenant header arrived
    @app.get("/probe")
    async def probe(request: Request):
        tenant = request.headers.get("x-pii-tenant-id", "__absent__")
        return {"tenant_header": tenant}

    # Mount scoped-config router (uses require_multitenancy dependency)
    app.include_router(scoped_config_router, prefix="/v1/admin")

    # Override get_settings so require_multitenancy picks up our fake settings.
    # Also override get_db so endpoints don't crash with a None session.
    app.dependency_overrides[get_settings] = _get_test_settings
    app.dependency_overrides[_get_db] = _get_db  # maps stub → stub (no-op, DB still None)

    return app


_BASE_SETTINGS = dict(
    database_url="sqlite+aiosqlite:///:memory:",
    encryption_key="test-key-32-chars-padded-00000000",
    admin_initial_key="test-admin-key",
)


# ---------------------------------------------------------------------------
# Test 1 — MULTITENANCY_ENABLED=false → X-Pii-Tenant-Id stripped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_header_stripped_when_self_hosted():
    app = _build_app({**_BASE_SETTINGS, "MULTITENANCY_ENABLED": False})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/probe", headers={"X-Pii-Tenant-Id": "acme"})

    assert resp.status_code == 200
    data = resp.json()
    # The middleware must have stripped the header before it reached the endpoint
    assert data["tenant_header"] == "__absent__", (
        f"Expected header to be stripped in self-hosted mode, got: {data['tenant_header']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 — MULTITENANCY_ENABLED=true, accept_tenant_header=false → 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_header_rejected_when_mt_enabled_and_not_accepted():
    app = _build_app({
        **_BASE_SETTINGS,
        "MULTITENANCY_ENABLED": True,
        "PII_ACCEPT_TENANT_HEADER": False,
    })

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/probe", headers={"X-Pii-Tenant-Id": "acme"})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "tenant_header_not_accepted"


# ---------------------------------------------------------------------------
# Test 3 — MULTITENANCY_ENABLED=true, accept_tenant_header=true → request passes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tenant_header_accepted_when_mt_and_accept_enabled():
    app = _build_app({
        **_BASE_SETTINGS,
        "MULTITENANCY_ENABLED": True,
        "PII_ACCEPT_TENANT_HEADER": True,
    })

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/probe", headers={"X-Pii-Tenant-Id": "acme"})

    # Must NOT be 403 — the middleware lets the request through
    assert resp.status_code != 403, (
        f"Expected request to pass (not 403) when accept_tenant_header=true, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 4 — scoped_config returns 404 when MULTITENANCY_ENABLED=false
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scoped_config_404_when_self_hosted():
    app = _build_app({**_BASE_SETTINGS, "MULTITENANCY_ENABLED": False})

    # require_admin needs an API key — override it to return a fake admin key
    async def fake_admin():
        return ApiKey(name="admin", role="admin")

    app.dependency_overrides[require_admin] = fake_admin

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/admin/scoped-config/regex-patterns",
            headers={"X-Api-Key": "any"},
            params={"scope_type": "tenant", "scope_key": "test"},
        )

    assert resp.status_code == 404, (
        f"Expected 404 from require_multitenancy guard in self-hosted mode, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 5 — scoped_config NOT 404 when MULTITENANCY_ENABLED=true
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scoped_config_not_404_when_multitenancy_enabled():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    app = _build_app({
        **_BASE_SETTINGS,
        "MULTITENANCY_ENABLED": True,
        "PII_ACCEPT_TENANT_HEADER": True,
    })

    # Override require_admin to skip real DB auth
    async def fake_admin():
        return ApiKey(name="admin", role="admin")

    # Provide a minimal fake DB session so the scoped_config service doesn't crash.
    # base_items() does ``await db.execute(text(...))``.
    def _empty_result():
        return MagicMock(fetchall=MagicMock(return_value=[]))

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=_empty_result())

    async def fake_db():
        yield fake_session

    app.dependency_overrides[require_admin] = fake_admin
    # Override the exact get_db reference that scoped_config.py captured at import time
    app.dependency_overrides[_scoped_config_module.get_db] = fake_db

    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        resp = await client.get(
            "/v1/admin/scoped-config/regex-patterns",
            headers={"X-Api-Key": "any"},
            params={"scope_type": "tenant", "scope_key": "test"},
        )

    # The MT guard passes — response should be 2xx/4xx but NOT the MT-guard 404.
    assert resp.status_code != 404 or resp.json().get("detail") != "scoped_config_not_available_in_self_hosted_mode", (
        "Scoped-config returned MT-guard 404 even though multitenancy_enabled=True"
    )


# ---------------------------------------------------------------------------
# Bonus — strip_commercial_quota_if_self_hosted dependency unit test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quota_fields_stripped_in_self_hosted_mode():
    """The _strip_commercial_quota_if_self_hosted dependency must zero out
    quota fields when multitenancy_enabled=False."""
    self_hosted_settings = Settings(**{**_BASE_SETTINGS, "MULTITENANCY_ENABLED": False})

    body = CreateKeyRequest(
        name="mykey",
        role="service",
        max_requests_per_minute=100,
        max_requests_per_hour=1000,
        max_requests_per_day=10000,
        max_chars_per_request=5000,
        max_chars_per_month=9999999,
    )

    result = _strip_commercial_quota_if_self_hosted(body, self_hosted_settings)

    assert result.max_requests_per_minute is None
    assert result.max_requests_per_hour is None
    assert result.max_requests_per_day is None
    assert result.max_chars_per_request is None
    assert result.max_chars_per_month is None


@pytest.mark.asyncio
async def test_quota_fields_preserved_in_multitenancy_mode():
    """Quota fields must be kept intact when multitenancy_enabled=True."""
    mt_settings = Settings(**{**_BASE_SETTINGS, "MULTITENANCY_ENABLED": True})

    body = CreateKeyRequest(
        name="mykey",
        role="service",
        max_requests_per_minute=100,
        max_requests_per_hour=1000,
        max_requests_per_day=10000,
        max_chars_per_request=5000,
        max_chars_per_month=9999999,
    )

    result = _strip_commercial_quota_if_self_hosted(body, mt_settings)

    assert result.max_requests_per_minute == 100
    assert result.max_requests_per_hour == 1000
    assert result.max_requests_per_day == 10000
    assert result.max_chars_per_request == 5000
    assert result.max_chars_per_month == 9999999
