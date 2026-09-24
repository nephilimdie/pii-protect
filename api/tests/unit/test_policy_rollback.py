from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.identity.models import ApiKey
from app.routers import context_types_router, domain_policies_router


class Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class Session:
    def __init__(self, history, current):
        self.history = history
        self.current = current
        self.commits = 0

    async def execute(self, query, _params=None):
        sql = str(query)
        if "SELECT snapshot FROM" in sql:
            return Result(SimpleNamespace(_mapping={"snapshot": self.history}))
        if "UPDATE domain_policies" in sql or "UPDATE context_types" in sql:
            return Result(SimpleNamespace(_mapping=self.current))
        return Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_domain_policy_rollback_creates_a_new_version(monkeypatch):
    now = datetime.utcnow()
    session = Session(
        {"domain": "legal", "version": 1, "protect_types": ["PERSON"]},
        {
            "domain": "legal", "display_name": "Legal", "default_mode": "tag", "version": 3,
            "protect_types": ["PERSON"], "keep_types": [], "surrogate_types": [], "remove_types": [],
            "block_types": [], "confidence_thresholds": {}, "allowlist": {}, "visible_to_clients": None,
            "description": None, "enabled": True, "updated_at": now,
        },
    )
    audit = SimpleNamespace(log=AsyncMock())
    monkeypatch.setattr(domain_policies_router, "AuditService", lambda _db: audit)

    result = await domain_policies_router.rollback_policy(
        "legal", 1, SimpleNamespace(client=SimpleNamespace(host="127.0.0.1")),
        ApiKey(name="admin", role="admin", tenant_id="tenant-a"), session,
    )

    assert result["version"] == 3
    assert result["protect_types"] == ["PERSON"]
    assert session.commits == 1
    audit.log.assert_awaited_once()
    assert audit.log.call_args.kwargs["action"] == "policy_rollback"


@pytest.mark.asyncio
async def test_context_type_rollback_reuses_snapshot_without_overwriting_history(monkeypatch):
    session = Session(
        {"code": "support", "version": 2, "display_name": "Support", "default_mode": "surrogate"},
        {
            "code": "support", "display_name": "Support", "domain": "legal", "default_mode": "surrogate",
            "description": "Support tickets", "visible_to_clients": [], "enabled": True,
            "version": 4, "created_at": datetime.utcnow(),
        },
    )

    result = await context_types_router.rollback_context_type(
        "support", 2, ApiKey(name="admin", role="admin", tenant_id="tenant-a"), session,
    )

    assert result["default_mode"] == "surrogate"
    assert result["version"] == 4
    assert session.commits == 1
