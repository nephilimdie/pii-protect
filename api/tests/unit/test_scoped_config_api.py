import json
import os
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import DeclarativeBase
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-chars-padded-00000000")
os.environ.setdefault("ADMIN_INITIAL_KEY", "test-admin-key")

database_stub = ModuleType("app.database")


class Base(DeclarativeBase):
    pass


async def get_db():
    yield None


database_stub.Base = Base
database_stub.get_db = get_db
sys.modules["app.database"] = database_stub

from app.config import get_settings, Settings
from app.identity.dependencies import require_admin
from app.identity.models import ApiKey
from app.routers.scoped_config import router
import app.routers.scoped_config as _scoped_config_module


@pytest.mark.asyncio
async def test_same_regex_can_have_different_tenant_overrides():
    app = FastAPI()
    app.include_router(router, prefix="/v1/admin")
    overrides = {}

    async def fake_admin(x_api_key: str = Header(..., alias="X-Api-Key")):
        return ApiKey(name=x_api_key, role="admin", tenant_id=x_api_key)

    async def fake_db():
        yield fake_session(overrides)

    def fake_settings():
        return SimpleNamespace(multitenancy_enabled=True)

    app.dependency_overrides[require_admin] = fake_admin
    app.dependency_overrides[_scoped_config_module.get_db] = fake_db
    app.dependency_overrides[get_settings] = fake_settings

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await put_regex(client, "tenant-a", "Pattern for tenant A")
        await put_regex(client, "tenant-b", "Pattern for tenant B")

        tenant_a = await get_regex(client, "tenant-a")
        tenant_b = await get_regex(client, "tenant-b")
        forbidden = await client.get(
            "/v1/admin/scoped-config/regex-patterns",
            headers={"X-Api-Key": "tenant-a"},
            params={"scope_type": "tenant", "scope_key": "tenant-b"},
        )

    assert tenant_a.status_code == 200
    assert tenant_b.status_code == 200
    assert tenant_a.json()["items"][0]["description"] == "Pattern for tenant A"
    assert tenant_b.json()["items"][0]["description"] == "Pattern for tenant B"
    assert tenant_a.json()["items"][0]["_scope"] == "tenant:tenant-a"
    assert tenant_b.json()["items"][0]["_scope"] == "tenant:tenant-b"
    assert forbidden.status_code == 403


def fake_session(overrides):
    async def execute(query, params=None):
        sql = str(query)
        params = params or {}
        if "FROM regex_patterns" in sql:
            return result_with_rows([
                {
                    "id": "rx_shared",
                    "pii_type": "FISCAL_CODE",
                    "pattern": "[A-Z]{6}[0-9]{2}",
                    "flags": "",
                    "capture_group": 0,
                    "description": "Platform regex",
                    "enabled": True,
                    "created_at": None,
                    "updated_at": None,
                }
            ])

        if "AS detection_layers" in sql:
            return result_with_rows([
                {
                    "code": "regex",
                    "display_name": "Regex",
                    "description": "Deterministic regex layer",
                    "enabled": True,
                },
                {
                    "code": "privacy_filter",
                    "display_name": "Privacy Filter",
                    "description": "ONNX privacy filter",
                    "enabled": True,
                },
            ])

        if "FROM scoped_config_overrides" in sql:
            key = (params["scope_type"], params["scope_key"], params["collection"])
            return result_with_rows(list(overrides.get(key, {}).values()))

        if "INSERT INTO scoped_config_overrides" in sql:
            key = (params["scope_type"], params["scope_key"], params["collection"])
            item = {
                "id": "override-1",
                "scope_type": params["scope_type"],
                "scope_key": params["scope_key"],
                "collection": params["collection"],
                "item_key": params["item_key"],
                "action": params["action"],
                "data": json.loads(params["data"]),
                "created_at": None,
                "updated_at": None,
            }
            overrides.setdefault(key, {})[params["item_key"]] = item
            return result_with_one(item)

        return result_with_rows([])

    return SimpleNamespace(execute=AsyncMock(side_effect=execute), commit=AsyncMock(), add=MagicMock(), flush=AsyncMock(), refresh=AsyncMock())


def result_with_rows(rows):
    return MagicMock(fetchall=MagicMock(return_value=[SimpleNamespace(_mapping=row) for row in rows]))


def result_with_one(row):
    return MagicMock(fetchone=MagicMock(return_value=SimpleNamespace(_mapping=row)))


async def put_regex(client, tenant, description):
    return await client.put(
        "/v1/admin/scoped-config/regex-patterns/rx_shared",
        headers={"X-Api-Key": tenant},
        json={
            "scope_type": "tenant",
            "scope_key": tenant,
            "item_key": "rx_shared",
            "action": "override",
            "data": {
                "pii_type": "FISCAL_CODE",
                "pattern": "[A-Z]{6}[0-9]{2}",
                "flags": "",
                "capture_group": 0,
                "enabled": True,
                "description": description,
            },
        },
    )


async def get_regex(client, tenant):
    return await client.get(
        "/v1/admin/scoped-config/regex-patterns",
        headers={"X-Api-Key": tenant},
        params={"scope_type": "tenant", "scope_key": tenant},
    )


@pytest.mark.asyncio
async def test_detection_layers_can_be_overridden_per_tenant():
    app = FastAPI()
    app.include_router(router, prefix="/v1/admin")
    overrides = {}

    async def fake_admin(x_api_key: str = Header(..., alias="X-Api-Key")):
        return ApiKey(name=x_api_key, role="admin", tenant_id=x_api_key)

    async def fake_db():
        yield fake_session(overrides)

    def fake_settings():
        return SimpleNamespace(multitenancy_enabled=True)

    app.dependency_overrides[require_admin] = fake_admin
    app.dependency_overrides[_scoped_config_module.get_db] = fake_db
    app.dependency_overrides[get_settings] = fake_settings

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        updated = await client.put(
            "/v1/admin/scoped-config/detection-layers/privacy_filter",
            headers={"X-Api-Key": "tenant-a"},
            json={
                "scope_type": "tenant",
                "scope_key": "tenant-a",
                "item_key": "privacy_filter",
                "action": "override",
                "data": {
                    "code": "privacy_filter",
                    "display_name": "Privacy Filter",
                    "enabled": False,
                    "description": "Disable for realtime benchmark",
                },
            },
        )
        listed = await client.get(
            "/v1/admin/scoped-config/detection-layers",
            headers={"X-Api-Key": "tenant-a"},
            params={"scope_type": "tenant", "scope_key": "tenant-a"},
        )

    assert updated.status_code == 200
    assert listed.status_code == 200
    items = {item["_item_key"]: item for item in listed.json()["items"]}
    assert items["regex"]["enabled"] is True
    assert items["privacy_filter"]["enabled"] is False
    assert items["privacy_filter"]["_scope"] == "tenant:tenant-a"
