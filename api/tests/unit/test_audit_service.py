from __future__ import annotations

import os
import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.orm import DeclarativeBase

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

import pytest

from app.audit.audit_service import AuditService


@pytest.mark.asyncio
async def test_log_persists_metadata_without_plaintext_document():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    api_key_id = uuid.uuid4()
    await AuditService(session, ip_anonymization=False).log(
        api_key_id=api_key_id,
        action="deanonymize",
        context_id="ctx-1",
        char_count=42,
        tenant_id="tenant-a",
        document_hash="a" * 64,
        ip="127.0.0.1",
        reason="support request",
    )

    entry = session.add.call_args.args[0]
    assert entry.api_key_id == api_key_id
    assert entry.action == "deanonymize"
    assert entry.context_id == "ctx-1"
    assert entry.char_count == 42
    assert entry.tenant_id == "tenant-a"
    assert entry.document_hash == "a" * 64
    assert entry.ip == "127.0.0.1"
    assert entry.reason == "support request"
    session.commit.assert_awaited_once()
